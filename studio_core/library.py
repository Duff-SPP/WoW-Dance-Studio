"""Action-only persistence and selected-dance assembly on the canonical target."""
import hashlib
import json
import uuid
import time
from pathlib import Path
import bpy
from .catalog import ROOT, LIBRARY, digest, write_json, read_catalog, select_emote, record_version
from .analysis import inventory, signature
from .retarget import convert
from .import_emote import prepare
from .blender_audio import add_soundtrack


def store(identifier,variant,profile_path,cache_request=None):
    phase=None
    phase_start=time.perf_counter()
    def stage(name):
        nonlocal phase,phase_start
        now=time.perf_counter()
        if phase: print('STUDIO: '+phase+' finished in '+format(now-phase_start,'.2f')+' s',flush=True)
        phase=name;phase_start=now
        if name: print('STUDIO: '+name,flush=True)
    stage('Checking source and profile')
    emote,asset=select_emote(identifier,variant)
    for key,hash_key in [('path','sha256'),('source_skeleton','skeleton_sha256')]:
        if digest(asset[key])!=asset[hash_key]:
            raise ValueError('Asset changed since scan: '+asset[key])
    profile=json.loads(Path(profile_path).read_text(encoding='utf-8'))
    if cache_request:
        from .models import checked_profile
        checked_profile(profile_path,cache_request['target'],bpy.data.filepath)
    elif profile.get('generator'):
        from .models import checked_profile
        checked_profile(profile_path,profile['model_id'],bpy.data.filepath)
    from .integrity import snapshot,verify,action_hash
    stage('Checking original animations and geometry before import')
    preserved=snapshot(profile['target'])
    stage('Importing dance and verifying dependencies')
    code={p.name:digest(p) for p in sorted((ROOT/'studio_core').glob('*.py'))}
    baseline_hash=digest(bpy.data.filepath)
    if asset.get('montage'):
        from .compose_emote import prepare_montage
        adjusted,imported=prepare_montage(asset,profile)
    else:
        adjusted,imported=prepare(asset,profile)
    fingerprint=hashlib.sha256(json.dumps(dict(asset=asset,profile=digest(profile_path),code=code,
                                             baseline=baseline_hash,importer=imported['importer_files']),sort_keys=True).encode()).hexdigest()
    if cache_request:
        from .cache import Context
        actual,payload=Context(cache_request['blender'],cache_request['scene']).fingerprint(identifier,variant,profile_path,cache_request['target'])
        if actual!=cache_request['fingerprint']: raise ValueError('Dependencies changed after this job was queued; rescan/retry')
        if any(value not in payload['importer'].values() for value in imported['importer_files'].values()):
            raise ValueError('Loaded importer does not match the selected runtime dependency manifest')
        fingerprint=actual
    print('STUDIO: Imported '+identifier+' '+variant,flush=True)
    version=fingerprint[:12]+'_'+uuid.uuid4().hex[:8]
    target_id=cache_request['target'] if cache_request else profile.get('model_id','human2_male')
    directory=LIBRARY/'actions'/target_id/identifier/variant/version
    directory.mkdir(parents=True,exist_ok=False)
    action_path=directory/'action.blend'
    name=f'{target_id}_{identifier}_{variant}_{version}'
    stage('Retargeting and baking dance')
    validation=convert(adjusted,action_path,inventory(),include_audio=False,action_name=name,save_scene=False)
    stage('Checking baked motion')
    action=bpy.data.actions[validation['action']]
    if profile.get('generator'):
        from .motion_validation import diagnose
        validation['motion']=diagnose(profile,action)
    action['studio_emote_id']=identifier
    action['studio_variant']=variant
    stage('Verifying original animations and geometry after bake')
    validation['preservation']=verify(preserved,profile['target'],action)
    stage('Saving and verifying action roundtrip')
    pending=directory/'action.pending.blend'
    bpy.data.libraries.write(str(pending),{action},fake_user=True)
    with bpy.data.libraries.load(str(pending),link=False) as (available,requested):
        if available.objects or available.meshes or action.name not in available.actions: raise ValueError('Invalid action-only output')
        requested.actions=[action.name]
    loaded=requested.actions[0]
    if loaded is None or action_hash(loaded)!=action_hash(action): raise ValueError('Stored action failed roundtrip validation')
    bpy.data.actions.remove(loaded)
    import os
    os.replace(pending,action_path)
    stage('Reading soundtrack timing and publishing conversion')
    import aud, wave
    audio_timing={}
    audio_warnings=[]
    for role,media in emote['audio'].items():
        try:
            sound=aud.Sound(media['path'])
            rate,channels=sound.specs
            samples=sound.length
            if Path(media['path']).suffix.lower()=='.wav':
                try:
                    with wave.open(media['path'],'rb') as wav:
                        samples,rate,channels=wav.getnframes(),wav.getframerate(),wav.getnchannels()
                except (wave.Error,EOFError):
                    pass
            audio_timing[role]=dict(samples=samples,sample_rate=rate,channels=channels,duration_seconds=samples/rate)
        except Exception as error:
            audio_warnings.append(role+': '+str(error))
    metadata=dict(id=identifier,variant=variant,version=version,fingerprint=fingerprint,
                  target_id=target_id,profile_revision=profile.get('revision'),model_identity=profile.get('model_identity'),
                  action=action.name,action_library=str(action_path),action_library_sha256=digest(action_path),
                  target=profile['target'],target_signature=profile['target_signature'],
                  profile_path=str(Path(profile_path).resolve()),profile_sha256=digest(profile_path),
                  baseline_sha256=baseline_hash,conversion_code=code,
                  source=asset,imported=imported,validation=validation,audio=emote['audio'],
                  audio_root=read_catalog()['asset_root'],prop_status=emote['prop_status'],
                  audio_timing=audio_timing,audio_warnings=audio_warnings,
                  audio_policy='intro at preview start, repeat loop after intro, trim at exclusive end',
                  status='Converted – Review Needed',visual_quality='unverified')
    if cache_request:
        metadata.update(cache_schema=3,target_id=cache_request['target'],animation_dependencies=payload,
                        queue_job_id=cache_request.get('job_id'))
    write_json(directory/'metadata.json',metadata)
    record_version(identifier,metadata)
    stage(None)
    print('STUDIO: Stored '+str(action_path),flush=True)
    return metadata


def load_actions(only_versions=None):
    loaded={}
    for emote in read_catalog()['emotes']:
        for metadata in emote['versions']:
            if only_versions is not None and metadata['version'] not in only_versions: continue
            path=Path(metadata['action_library'])
            if not path.is_file() or digest(path)!=metadata['action_library_sha256']:
                raise ValueError('Stored action missing or changed: '+str(path))
            with bpy.data.libraries.load(str(path),link=False) as (available,requested):
                if metadata['action'] not in available.actions:
                    raise ValueError('Action not found in its library')
                requested.actions=[metadata['action']]
            action=requested.actions[0]
            if action is None or len(action.slots)!=1:
                raise ValueError('Loaded action has no unique slot')
            action.use_fake_user=True
            loaded[metadata['version']]=(metadata,action)
    return loaded


def activate(metadata,action,output,include_audio=True):
    target=bpy.data.objects.get(metadata['target'])
    if target is None or signature(target)!=metadata['target_signature']:
        raise ValueError('Preview target differs from converted skeleton')
    for original in bpy.data.actions:
        original.use_fake_user=True
    for bone in target.pose.bones:
        bone.matrix_basis.identity()
        bone.rotation_mode='QUATERNION'
    target.animation_data_create()
    target.animation_data.action=action
    target.animation_data.action_slot=action.slots[0]
    scene=bpy.context.scene
    first,last=metadata['validation']['frames']
    import math
    scene.frame_start,scene.frame_end=math.floor(first),math.ceil(last)
    fps=metadata['validation']['fps']
    scene.render.fps=round(fps)
    scene.render.fps_base=round(fps)/fps
    if scene.sequence_editor:
        for name in json.loads(scene.get('studio_audio_strips','[]')):
            strip=scene.sequence_editor.strips.get(name)
            if strip:
                scene.sequence_editor.strips.remove(strip)
    audio_root=read_catalog().get('asset_root',metadata['audio_root'])
    audio=add_soundtrack(scene,audio_root,metadata['id'],include_audio,output)
    scene['studio_audio_strips']=json.dumps([s['name'] for s in audio['strips']])
    scene['studio_selected_emote']=metadata['id']
    scene['studio_selected_version']=metadata['version']
    for obj in bpy.data.objects:
        if obj.type in {'ARMATURE','EMPTY'}:
            obj.hide_set(True)
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D':
                area.spaces.active.overlay.show_overlays=False
    scene.frame_set(scene.frame_start)
    return audio


def preview(identifier,variant,output,include_audio=True,target_id='human2_male'):
    emote,_=select_emote(identifier,variant)
    versions=[m for m in emote['versions'] if m['variant']==variant and m.get('target_id','human2_male')==target_id]
    if not versions:
        raise ValueError('Convert this emote/variant before previewing')
    selected_id=emote.get('selected_versions',{}).get(target_id+':'+variant)
    selected=next((m for m in versions if m['version']==selected_id),versions[-1])
    if digest(bpy.data.filepath)!=selected['baseline_sha256']: raise ValueError('Preview must use the exact registered target scene')
    loaded=load_actions({selected['version']})
    metadata,action=loaded[selected['version']]
    audio=activate(metadata,action,output,include_audio)
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(output).resolve()),check_existing=False)
    return dict(status='preview_ready',output=str(Path(output).resolve()),emote=identifier,
                action=action.name,library_actions=len(loaded),audio=audio)
