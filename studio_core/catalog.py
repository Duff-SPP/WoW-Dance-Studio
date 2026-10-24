"""Emote-aware catalog, immutable action versions and atomic library metadata."""
import hashlib
import json
import re
import os
from datetime import datetime,timezone
from pathlib import Path
from functools import wraps
from .storage import atomic_json,locked
from .audio import normalized, build_audio_index, match_soundtrack

ROOT = Path(__file__).resolve().parents[1]
LIBRARY = Path(os.environ.get('WDS_LIBRARY_ROOT',ROOT/'Output'/'Library')).resolve()
if not LIBRARY.is_relative_to(ROOT/'Output'): raise ValueError('Library must stay inside Output')
CATALOG = LIBRARY/'emotes.json'


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def write_json(path, value):
    atomic_json(path,value)


def transaction(function):
    @wraps(function)
    def wrapped(*args,**kwargs):
        with locked(CATALOG.with_suffix('.lock'),timeout=3): return function(*args,**kwargs)
    return wrapped


def read_catalog():
    return json.loads(CATALOG.read_text(encoding='utf-8')) if CATALOG.exists() else dict(version=2,emotes=[])


@transaction
def scan_emotes(folder,checkpoint=None):
    checkpoint=checkpoint or (lambda:None)
    checkpoint()
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise ValueError('Fortnite asset directory does not exist: '+str(folder))
    old = {e['id']:e for e in read_catalog()['emotes']}
    from .fortnite_paths import asset_roots
    found=set()
    for source in asset_roots(folder):
        for p in source.rglob('*'):
            checkpoint()
            if p.is_file(): found.add(p)
    all_files = sorted(found)
    skeletons = [p for p in all_files if p.suffix.lower()=='.uemodel' and 'skeleton' in p.stem.lower()]
    families = {}
    audio_index = build_audio_index(folder)
    checkpoint()
    from .export_manifest import load_index,records_for,referenced_audio
    export_index=load_index(ROOT/'Reports/FortniteBatch/exports.json')
    for manifest in ('TagCorrection/exports.json','verified_manual_exports.json'):
        for sha,records in load_index(ROOT/'Reports/FortniteBatch'/manifest).items():
            export_index.setdefault(sha,{}).update(records)
    for path in all_files:
        checkpoint()
        if path.suffix.lower() != '.ueanim':
            continue
        parts = path.parts
        sha=digest(path)
        if 'Emotes' not in parts:
            # Some verified exports live under BacklogEmotes rather than Emotes.
            match=re.search(r'_(?:CMM|CMF|CLM|CLF)(?:_|$)',path.stem,re.I)
            if not match or not records_for(export_index,[sha]):continue
            family=re.sub(r'^Emote_','',path.stem[:match.start()],flags=re.I)
        else:family = parts[parts.index('Emotes')+1]
        identifier = normalized(family)
        e = families.setdefault(identifier,dict(id=identifier,name=re.sub(r'(?<=[a-z])(?=[A-Z])',' ',family),
                   target='Human2 Male',variants=[],props=[],audio={},versions=old.get(identifier,{}).get('versions',[])))
        row = dict(path=str(path),sha256=sha)
        if re.search(r'(?:prop|gadget)',path.stem,re.I):
            e['props'].append(row)
            continue
        match = re.search(r'(?:^|_)(CMM|CMF|CLM|CLF)(?:_|$)',path.stem,re.I)
        variant = match[1].upper() if match else 'UNKNOWN'
        from .variants import source_candidate
        candidate=source_candidate(skeletons,variant)
        row.update(variant=variant,source_skeleton=str(candidate) if candidate else None,
                   source_compatibility='Checked against profile and animation tracks during Blender import',
                   missing_dependencies=[] if candidate else ['Source skeleton not provided' if not skeletons else 'Source skeleton selection is ambiguous'])
        if row['source_skeleton']:
            row['skeleton_sha256']=digest(row['source_skeleton'])
        if not any(v['variant']==row['variant'] and v['sha256']==row['sha256'] for v in e['variants']):
            e['variants'].append(row)
    for e in families.values():
        checkpoint()
        for path in all_files:
            if path.suffix.lower()=='.uemodel' and e['id'] in normalized(path.stem) and 'gadget' in path.stem.lower():
                e['props'].append(dict(path=str(path),sha256=digest(path)))
        files,warnings,e['audio_match'] = match_soundtrack(audio_index,e['id'])
        exported=records_for(export_index,[v['sha256'] for v in e['variants']])
        if len(exported)>1:
            identities={(r.get('Name'),tuple(sorted({f['Sha256'] for v in r['Variants'] for f in v['Files'] if f['Kind']=='audio'}))) for r in exported}
            if len(identities)==1:
                e['export_ids']=[r['Id'] for r in exported]
                exported=exported[:1]  # Identical favorite aliases share one dance.
        if len(exported)==1:
            e['internal_name']=e['name'];e['name']=exported[0].get('Name') or e['name'];e['export_id']=exported[0]['Id']
            if not files:
                files,warnings,e['audio_match']=referenced_audio(exported[0],folder,digest)
        e['audio']={role:dict(path=str(path),sha256=digest(path)) for role,path in files.items()}
        e['audio_warnings']=warnings
        e['approvals']=old.get(e['id'],{}).get('approvals',{})
        e['export_authorizations']=old.get(e['id'],{}).get('export_authorizations',{})
        e['selected_versions']=old.get(e['id'],{}).get('selected_versions',{})
        e['prop_status']='Body-only; prop omitted / Prop Incomplete' if e['props'] else 'No prop exports'
        e['status']='Converted – Review Needed' if e['versions'] else ('Missing Dependencies' if not any(not v['missing_dependencies'] for v in e['variants']) else 'Not Converted')
        selected=e['selected_versions'].get('human2_male:CMM',e['versions'][-1]['version'] if e['versions'] else None)
        if selected in e['approvals']:
            e['status']='Approved'
        e['last_error']=old.get(e['id'],{}).get('last_error')
        if e['last_error'] and not e['versions']:
            e['status']='Failed'
    catalog=dict(version=2,asset_root=str(folder),emotes=sorted(families.values(),key=lambda e:e['name']))
    checkpoint()
    write_json(CATALOG,catalog)
    return catalog


def select_emote(identifier,variant='CMM',catalog=None):
    if catalog is None: catalog=read_catalog()
    matches=[e for e in catalog['emotes'] if e['id']==identifier]
    if len(matches)!=1:
        raise ValueError('Scan catalog and select a valid emote ID: '+str(identifier))
    e=matches[0]
    variants=[v for v in e['variants'] if v['variant']==variant]
    if os.environ.get('WDS_MONTAGE_PREVIEW')=='1':
        from .montage_runtime import playback
        from .montage_assets import resolve,flat_compatible
        plan=playback(e,variant)
        if plan:
            resolved=resolve(e,plan)
            if resolved.get('routing_notifies'):raise ValueError('Dynamic montage section routing requires notify rules')
            if flat_compatible(resolved):
                selected=dict(next(iter(resolved['assets'].values()))['asset'])
            else:
                selected=dict(next(iter(resolved['assets'].values()))['asset'])
                selected['montage']={k:v for k,v in resolved.items() if k!='sound_notifies'}
            if selected['missing_dependencies']:raise ValueError('; '.join(selected['missing_dependencies']))
            return e,selected
        raise ValueError('Missing verified montage evidence for this emote variant; inspect its Fortnite montage before using intro / loop mode')
    from .variants import main_performance
    selected=main_performance(variants)
    if selected['missing_dependencies']:
        raise ValueError('; '.join(selected['missing_dependencies']))
    return e,selected


@transaction
def record_version(identifier,metadata):
    catalog=read_catalog()
    e=next(e for e in catalog['emotes'] if e['id']==identifier)
    if not any(m['version']==metadata['version'] for m in e['versions']): e['versions'].append(metadata)
    e.setdefault('selected_versions',{})[metadata.get('target_id','human2_male')+':'+metadata.get('variant','CMM')]=metadata['version']
    e.update(status='Converted – Review Needed',last_error=None)
    write_json(CATALOG,catalog)


@transaction
def record_failure(identifier,error):
    catalog=read_catalog()
    for e in catalog['emotes']:
        if e['id']==identifier:
            e['last_error']=str(error)
            e['status']='Failed' if not e['versions'] else 'Converted – Review Needed'
    write_json(CATALOG,catalog)


@transaction
def approve_version(identifier,variant,target='human2_male'):
    emote,_=select_emote(identifier,variant)
    versions=[v for v in emote['versions'] if v.get('variant')==variant and v.get('target_id','human2_male')==target]
    if not versions:
        raise ValueError('Convert this variant before marking it approved')
    selected=emote.get('selected_versions',{}).get(target+':'+variant)
    version=next((v['version'] for v in versions if v['version']==selected),versions[-1]['version'])
    catalog=read_catalog()
    e=next(e for e in catalog['emotes'] if e['id']==identifier)
    e.setdefault('approvals',{})[version]=dict(status='Approved',manual=True,
                                             recorded_at=datetime.now(timezone.utc).isoformat())
    e['status']='Approved'
    write_json(CATALOG,catalog)
    return version


@transaction
def select_version(identifier,variant,version,target='human2_male'):
    catalog=read_catalog(); e=next(e for e in catalog['emotes'] if e['id']==identifier)
    if not any(m['version']==version and m['variant']==variant and m.get('target_id','human2_male')==target for m in e['versions']): raise ValueError('Version is not in this target library')
    e.setdefault('selected_versions',{})[target+':'+variant]=version
    e['status']='Approved' if version in e.get('approvals',{}) else 'Converted – Review Needed'
    write_json(CATALOG,catalog)
