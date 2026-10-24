"""Animation and soundtrack dependencies are intentionally separate."""
import hashlib
import json
import os
import ast
from pathlib import Path
from .catalog import ROOT, LIBRARY, digest, read_catalog, select_emote
from .audio import build_audio_index,match_soundtrack
from .storage import ContentChecks

SCHEMA=3
TARGETS={'human2_male':'humanmale2_Armature'}


def hashed(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


class Context:
    def __init__(self,blender,scene):
        self.checks=ContentChecks(digest)
        self.blender=Path(blender).resolve(); self.scene=Path(scene).resolve()
        if not self.blender.is_file() or not self.scene.is_file(): raise ValueError('Missing Blender executable or target scene')
        versions=[p.name for p in self.blender.parent.iterdir() if p.is_dir() and (p/'python').is_dir()]
        if len(versions)!=1: raise ValueError('Cannot identify selected Blender runtime version')
        addon=Path(os.environ.get('APPDATA',Path.home()/'AppData'/'Roaming'))/'Blender Foundation'/'Blender'/versions[0]/'scripts'/'startup'/'fortnite_porting'/'ueformat'
        if not addon.is_dir(): raise ValueError('Fortnite Porting UEFormat importer is missing for this Blender runtime')
        self.dependencies=dict(schema=SCHEMA,blender_sha256=digest(self.blender),baseline_sha256=digest(self.scene),
             implementation={name:digest(ROOT/'studio_core'/name) for name in ['retarget.py','import_emote.py','analysis.py','integrity.py']},
             importer={str(p.relative_to(addon)):digest(p) for p in sorted(addon.rglob('*.py'))})

    def catalog_snapshot(self):
        from .catalog import CATALOG
        stat=CATALOG.stat()
        stamp=(str(CATALOG),stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns)
        if getattr(self,'_catalog_stamp',None)!=stamp:
            self._catalog=read_catalog()
            self._catalog_stamp=stamp
        return self._catalog

    def fingerprint(self,identifier,variant,profile_path,target='human2_male'):
        emote,asset=select_emote(identifier,variant,catalog=self.catalog_snapshot())
        profile_path=Path(profile_path).resolve()
        if not profile_path.is_relative_to(ROOT/'Profiles') or not profile_path.is_file(): raise ValueError('Missing profile inside Profiles')
        from .models import checked_profile
        profile=checked_profile(profile_path,target,self.scene)
        payload=dict(self.dependencies,emote=identifier,variant=variant,target=target,
                     source_sha256=self.checks.digest(asset['path']),skeleton_sha256=self.checks.digest(asset['source_skeleton']),
                     profile_sha256=self.checks.digest(profile_path),settings=dict(body_only=True,profile=profile))
        if asset.get('montage'):
            payload['montage']=asset['montage']
            payload['montage_implementation']={name:self.checks.digest(ROOT/'studio_core'/name) for name in ('montage.py','compose_emote.py')}
        return hashed(payload),payload


def valid_output(metadata):
    try:
        path=Path(metadata['action_library'])
        sidecar=path.parent/'metadata.json'
        return bool(path.is_relative_to(LIBRARY) and path.is_file() and digest(path)==metadata['action_library_sha256']
                and sidecar.is_file() and json.loads(sidecar.read_text(encoding='utf-8'))==metadata
                and metadata['validation']['changing_sampled_transforms'] and metadata.get('action'))
    except (OSError,KeyError,TypeError,ValueError): return False


def find_current(identifier,variant,fingerprint,target='human2_male',emote=None):
    if emote is None: emote,_=select_emote(identifier,variant)
    selected=emote.get('selected_versions',{}).get(target+':'+variant)
    ordered=sorted(emote['versions'],key=lambda m:m['version']==selected)
    for metadata in reversed(ordered):
        if (metadata.get('cache_schema')==SCHEMA and metadata.get('target_id')==target and
            metadata['variant']==variant and metadata['fingerprint']==fingerprint and valid_output(metadata)):
            return metadata
    return None


def reuse_profile_revision(identifier,variant,fingerprint,payload,target,profile_path):
    """Reuse baked curves when only profile review/revision bookkeeping changed.

    Publish a new immutable metadata binding; never edit an old action or profile.
    All animation inputs, implementation hashes and actual bone settings must match.
    """
    import copy,shutil,uuid
    from .catalog import record_version
    from .storage import atomic_json
    administrative={'approval','status','revision','parent_revision','visual_quality'}
    def effective(value):
        value=copy.deepcopy(value);value.pop('profile_sha256',None)
        # Sound notify timing does not alter the baked source pose. Early
        # montage previews retained it; allow immutable reuse after separation.
        value.get('montage',{}).pop('sound_notifies',None)
        # Resolution is fully captured in the plan/source hashes. A resolver
        # change yielding the identical plan does not alter source baking.
        value.get('montage_implementation',{}).pop('montage_assets.py',None)
        profile=value.get('settings',{}).get('profile',{})
        for key in administrative:profile.pop(key,None)
        return value
    emote,_=select_emote(identifier,variant)
    for old in reversed(emote['versions']):
        if old.get('target_id')!=target or old.get('variant')!=variant or old.get('cache_schema')!=SCHEMA:continue
        previous=old.get('animation_dependencies')
        if previous is None or effective(previous)!=effective(payload) or not valid_output(old):continue
        old_profile=Path(old['profile_path'])
        if not old_profile.is_file() or digest(old_profile)!=old['profile_sha256']:continue
        version=fingerprint[:12]+'_'+uuid.uuid4().hex[:8]
        directory=LIBRARY/'actions'/target/identifier/variant/version;directory.mkdir(parents=True)
        action=directory/'action.blend';shutil.copyfile(old['action_library'],action)
        metadata=copy.deepcopy(old)
        metadata.update(version=version,fingerprint=fingerprint,action_library=str(action),animation_dependencies=payload,
                        profile_path=str(Path(profile_path).resolve()),
                        profile_sha256=payload['profile_sha256'],profile_revision=payload['settings']['profile'].get('revision'),
                        reused_from_version=old['version'],visual_quality='unverified',status='Converted – Review Needed')
        if digest(action)!=old['action_library_sha256']:raise ValueError('Reused action checksum changed')
        atomic_json(directory/'metadata.json',metadata);record_version(identifier,metadata)
        return metadata
    return None


def audio_fingerprint(identifier,root):
    files,warnings,details=match_soundtrack(build_audio_index(root),identifier)
    return hashed(dict(files={role:digest(path) for role,path in files.items()},warnings=warnings,
                       code={n:digest(ROOT/'studio_core'/n) for n in ['audio.py','blender_audio.py']}))


def inspect_cache(context,profile,target='human2_male',variant='CMM',identifiers=None):
    rows={}
    for emote in read_catalog()['emotes']:
        if identifiers is not None and emote['id'] not in identifiers: continue
        try:
            from .variants import resolve_variant
            selected=resolve_variant(emote,target,variant)
            fingerprint,_=context.fingerprint(emote['id'],selected,profile,target)
            current=find_current(emote['id'],selected,fingerprint,target,emote=emote)
            target_versions=[m for m in emote['versions'] if m.get('target_id','human2_male')==target and m['variant']==selected]
            state='Cached / Up to Date' if current else 'Outdated' if target_versions else 'Not Converted'
            if current and current['version'] in emote.get('approvals',{}): state='Approved'
            rows[emote['id']]=dict(status=state,variant=selected,fingerprint=fingerprint,version=current['version'] if current else None)
        except (ValueError,OSError,KeyError) as error:
            from .models import requirement_status
            rows[emote['id']]=dict(status=requirement_status(error),error=str(error))
    return rows


def preview_dependencies(identifier,variant,scene,blender,include_audio,target='human2_male'):
    emote,_=select_emote(identifier,variant)
    versions=[m for m in emote['versions'] if m['variant']==variant and m.get('target_id','human2_male')==target]
    if not versions: raise ValueError('Convert the selected variant before previewing')
    selected_id=emote.get('selected_versions',{}).get(target+':'+variant)
    metadata=next((m for m in versions if m['version']==selected_id),versions[-1])
    if not valid_output(metadata): raise ValueError('Selected action output is missing or corrupted; convert missing to repair')
    if digest(scene)!=metadata['baseline_sha256']: raise ValueError('Preview scene differs from the converted target scene')
    key=target+':'+identifier+':'+variant+':'+str(bool(include_audio))
    code=(ROOT/'studio_core'/'library.py').read_text(encoding='utf-8')
    assembly=[ast.get_source_segment(code,node) for node in ast.parse(code).body if isinstance(node,ast.FunctionDef) and node.name in {'load_actions','activate','preview'}]
    fingerprint=hashed(dict(action=metadata['action_library_sha256'],baseline=digest(scene),blender=digest(blender),
                            audio=audio_fingerprint(identifier,read_catalog().get('asset_root',metadata['audio_root'])) if include_audio else None,
                            assembly=hashed(assembly)))
    return key,fingerprint


def cached_preview(key,fingerprint):
    path=LIBRARY/'previews.json'
    rows=json.loads(path.read_text()) if path.exists() else {}
    record=rows.get(key)
    if record and record['fingerprint']==fingerprint:
        try:
            output=Path(record['output'])
            if output.is_relative_to(ROOT/'Output') and digest(output)==record['sha256']: return record
        except OSError: pass
    return None


def remember_preview(key,fingerprint,output):
    from .storage import locked,atomic_json
    path=LIBRARY/'previews.json'
    with locked(path.with_suffix('.lock')):
        rows=json.loads(path.read_text()) if path.exists() else {}
        rows[key]=dict(fingerprint=fingerprint,output=str(output),sha256=digest(output))
        atomic_json(path,rows)
