"""Resolve exported names and sound references by exact animation content identity."""
import json
from pathlib import Path,PureWindowsPath
from .audio import tokens,EFFECTS,AUDIO_EXTENSIONS


def load_index(path):
    path=Path(path)
    if not path.is_file():return {}
    try:records=json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError,ValueError):return {}
    index={}
    for record in records:
        if record.get('Status')!='complete':continue
        for variant in record.get('Variants',[]):
            for file in variant.get('Files',[]):
                if file.get('Kind')=='animation':
                    matches=index.setdefault(file.get('Sha256'),{})
                    matches[record['Id']]=record
    return index


def records_for(index,hashes):
    result={}
    for sha in hashes:result.update(index.get(sha,{}))
    return list(result.values())


def referenced_audio(record,root,digest):
    from .fortnite_paths import asset_roots
    root=Path(root).resolve();selected={};candidates=[]
    for variant in record.get('Variants',[]):
        for file in variant.get('Files',[]):
            if file.get('Kind')!='audio':continue
            parts=PureWindowsPath(file['Path']).parts
            if 'Assets' not in parts:continue
            path=None
            for source in asset_roots(root):
                base=source if source.name.casefold()=='assets' else source/'Assets'
                candidate=base.joinpath(*parts[parts.index('Assets')+1:]).resolve()
                if candidate.is_relative_to(source) and candidate.is_file() and digest(candidate)==file.get('Sha256'):
                    path=candidate;break
            if path is None or path.suffix.lower() not in AUDIO_EXTENSIONS:continue
            labels=set(tokens(path.stem))
            if labels & EFFECTS:continue
            if not path.is_file() or digest(path)!=file.get('Sha256'):continue
            role='intro' if 'intro' in labels else 'loop' if labels & {'loop','lp'} else 'track'
            selected.setdefault(role,{})[file['Sha256']]=path
            candidates.append(dict(path=str(path),role=role,reason='verified exporter sound reference'))
    if 'intro' in selected or 'loop' in selected:selected.pop('track',None)
    if not selected:return {},['No verified exported soundtrack files found'],dict(status='missing',candidates=candidates)
    if any(len(values)!=1 for values in selected.values()):
        return {},['Exporter references multiple soundtrack alternatives; review required'],dict(status='ambiguous',candidates=candidates)
    files={role:next(iter(values.values())) for role,values in selected.items()}
    warnings=[] if 'track' in files else [role.capitalize()+' audio is missing.' for role in ('intro','loop') if role not in files]
    return files,warnings,dict(status='matched',reason='verified exporter sound references',export_id=record['Id'],candidates=candidates)
