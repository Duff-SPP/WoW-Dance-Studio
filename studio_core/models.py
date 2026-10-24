"""Persistent content-checked model registrations. Source assets are read-only."""
import json
import re
import os
import hashlib
from pathlib import Path
from contextlib import contextmanager
from contextvars import ContextVar
from .catalog import ROOT,digest
from .storage import atomic_json,locked,ContentChecks

_directory=Path(os.environ.get('WDS_MODELS_ROOT',ROOT/'Output'/'Models')).resolve()
if not _directory.is_relative_to(ROOT/'Output'): raise ValueError('Model registry must be inside Output')
REGISTRY=_directory/'models.json'
_validation_session=ContextVar('model_validation_session',default=None)


@contextmanager
def validation_session():
    if _validation_session.get() is not None:
        yield
        return
    token=_validation_session.set({})
    try:
        yield
    finally:
        _validation_session.reset(token)


def file_stamp(path):
    stat=Path(path).stat()
    return stat.st_size,stat.st_mtime_ns,stat.st_ctime_ns


def checked_digest(path):
    session=_validation_session.get()
    if session is None: return digest(path)
    key=('content_checks',)
    if key not in session: session[key]=ContentChecks(digest)
    return session[key].digest(path)

class ProfileApprovalRequired(ValueError):
    pass

def requirement_status(error):
    return 'Profile approval required' if isinstance(error,ProfileApprovalRequired) else 'Missing Dependencies'

def read_models():
    return json.loads(REGISTRY.read_text(encoding='utf-8')) if REGISTRY.exists() else {'schema':4,'models':[],'sources':[]}

def get_model(identifier):
    session=_validation_session.get()
    if session is None:
        rows=read_models()['models']
    else:
        key=('registry',str(REGISTRY),file_stamp(REGISTRY))
        if key not in session:
            session.clear()
            session[key]=read_models()['models']
        rows=session[key]
    result=next((m for m in rows if m['id']==identifier),None)
    if result is None: raise ValueError('Register the target model first: '+identifier)
    return result

def model_files(path,hash_file=None):
    path=Path(path).resolve()
    if path.suffix.lower()!='.m2' or not path.is_file(): raise ValueError('Missing M2 file')
    # Exact basename + numeric LOD/animation suffix; never take another character's skin.
    pattern=re.compile(re.escape(path.stem)+r'(?:\d+(?:-\d+)?|[-_]\d+[-_]\d+)?\.(skin|anim)$',re.I)
    hash_file=hash_file or digest
    return {str(p.resolve()):hash_file(p) for p in sorted(path.parent.iterdir()) if p==path or p.is_file() and pattern.fullmatch(p.name)}

def asset_provenance(path,files):
    """Verify an optional coherent client-baseline sidecar without changing asset identity."""
    path=Path(path).resolve();sidecar=path.parent/'studio_asset_provenance.json'
    if not sidecar.is_file(): return None
    data=json.loads(sidecar.read_text(encoding='utf-8'))
    if data.get('schema')!=1 or data.get('kind')!='client_hd': raise ValueError('Invalid client asset provenance')
    from pathlib import PureWindowsPath
    virtual=PureWindowsPath(data['virtual_model_path'])
    if virtual.is_absolute() or virtual.drive or '..' in virtual.parts or virtual.parts[0].lower()!='character' or virtual.name.casefold()!=path.name.casefold():
        raise ValueError('Client provenance model path differs')
    expected={name.casefold():sha for name,sha in data['files'].items()}
    actual={Path(name).name.casefold():sha for name,sha in files.items()}
    if expected!=actual: raise ValueError('Client provenance asset checksums differ; import a coherent model set again')
    return dict(kind='client_hd',archive=data['archive'],archive_sha256=data['archive_sha256'],virtual_model_path=str(virtual),
                manifest=str(sidecar),manifest_sha256=digest(sidecar),display_name=data['display_name'])


def discover_models(folder):
    folder=Path(folder).resolve()
    if not folder.is_dir(): raise ValueError('Missing model folder')
    rows=[]
    for path in sorted(folder.rglob('*')):
        if path.suffix.lower()!='.m2' or not path.is_file(): continue
        error=None
        with path.open('rb') as stream: header=stream.read(8)
        version=int.from_bytes(header[4:8],'little')
        if header[:4]!=b'MD20' or version!=264: error='Requires flat Wrath MD20 version 264; found '+repr(header[:4])+' / '+str(version)
        files=model_files(path)
        if not any(p.lower().endswith('.skin') for p in files): error='Missing matching SKIN file'
        rows.append(dict(path=str(path),files=files,version=version,error=error))
    return rows

def relocate_models(rows):
    """Reconnect moved assets only when the full named-file/hash manifest agrees."""
    def manifest(files): return {Path(p).name.casefold():sha for p,sha in files.items()}
    with locked(REGISTRY.with_suffix('.lock'),timeout=3):
        state=read_models(); changed=False
        for model in state['models']:
            if Path(model['path']).exists(): continue
            matches=[r for r in rows if not r['error'] and manifest(r['files'])==manifest(model['files'])]
            if len(matches)!=1: continue
            model.update(path=matches[0]['path'],files=matches[0]['files']); changed=True
        if changed: atomic_json(REGISTRY,state)
    return state

def publish(record,source=None):
    with locked(REGISTRY.with_suffix('.lock'),timeout=3):
        state=read_models(); state['models']=[m for m in state['models'] if m['id']!=record['id']]+[record]
        if source:
            state['sources']=[s for s in state['sources'] if s['signature']!=source['signature']]+[source]
        atomic_json(REGISTRY,state)

def checked_model(identifier,scene=None):
    model=get_model(identifier)
    if scene and Path(scene).resolve()!=Path(model['scene']).resolve(): raise ValueError('Selected scene does not belong to target model')
    session=_validation_session.get()
    key=('checked_model',identifier)
    stamps=None
    if session is not None:
        paths=[*model['files'],model['scene']]
        if model.get('asset_source'): paths.append(model['asset_source']['manifest'])
        stamps=tuple((p,file_stamp(p)) for p in paths)+(('directory',file_stamp(Path(model['path']).parent)),)
        if session.get(key)==stamps: return model
    for path,sha in model['files'].items():
        if not Path(path).is_file() or checked_digest(path)!=sha: raise ValueError('Model assets changed; register again: '+path)
    if model.get('asset_source'):
        checks=ContentChecks(digest) if session is None else None
        provenance=asset_provenance(model['path'],model_files(model['path'],hash_file=checks.digest if checks else checked_digest))
        if provenance!=model['asset_source']: raise ValueError('Client asset provenance changed; register the model again')
    if checked_digest(model['scene'])!=model['scene_sha256']: raise ValueError('Registered scene changed; register again')
    if session is not None: session[key]=stamps
    return model

def checked_profile(path,identifier,scene,require_approval=True):
    profile=json.loads(Path(path).read_text(encoding='utf-8'))
    # Established v0.1-v0.3 baseline is preserved without rewriting its profile.
    if identifier=='human2_male' and profile.get('generator') is None:
        if Path(scene).resolve()!=ROOT/'Blender'/'Human2_AutumnTea_Retarget.blend' or profile['target']!='humanmale2_Armature':
            raise ValueError('Legacy Human2 profile requires the original prepared scene')
        return profile
    model=checked_model(identifier,scene)
    if profile.get('model_id')!=identifier or profile['target_signature']!=model['signature'] or profile.get('model_identity')!=model['identity'] or profile['source_signature']!=model['source']['signature']:
        raise ValueError('Outdated or incompatible model/profile identity')
    batch_authorized=(profile.get('status')=='Batch Export Authorized' and
                      profile.get('approval',{}).get('kind')=='user_requested_batch_export')
    if profile.get('generator') and require_approval and ((profile.get('status')!='Approved' and not batch_authorized) or not profile.get('validation',{}).get('passed')):
        raise ProfileApprovalRequired('Bone profile approval required. Open Models, review this profile, click Approve, then Convert Selected again. Approving an animation with Mark Approved does not approve its bone profile.')
    if require_approval and profile.get('approval',{}).get('content_sha256')!=profile_content_hash(profile):
        raise ProfileApprovalRequired('Profile changed after approval; recalibrate, validate and approve a new revision in Models')
    return profile

def profile_content_hash(profile):
    return hashlib.sha256(json.dumps({k:v for k,v in profile.items() if k!='approval'},sort_keys=True,separators=(',',':')).encode()).hexdigest()
