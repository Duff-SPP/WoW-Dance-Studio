"""Versioned model packages linked to committed DBC allocations and library actions."""
import json
import os
import shutil
import struct
import subprocess
import uuid
from pathlib import Path,PureWindowsPath
from .catalog import ROOT,read_catalog,digest
from .storage import atomic_json,locked
from .models import checked_model,model_files
from .variants import model_sex
from . import dbc_manager as dbc
from .m2_binary import Model,M2Error
from .client_compatibility import check_animation_ids

OUTPUT=ROOT/'Output'/'M2'


def options(target):
    model=checked_model(target); native=Model(Path(model['path']).read_bytes()); state=dbc.registry()
    rows=[]
    for emote in read_catalog()['emotes']:
        if not emote.get('versions'): continue
        good,errors=dbc.eligible_versions(emote)
        matches=[v for v in good if v.get('target_id','human2_male')==target]
        entry=state['dances'].get(emote['id'])
        sex=model_sex(model)
        order=['CM'+sex,'CL'+sex] if sex else []
        chosen=next((v for kind in order for v in matches if v['variant']==kind),None)
        registered=bool(chosen and entry and any(v['version']==chosen['version'] and v['target']==target for v in entry['versions']))
        compatibility_error=None
        if registered:
            try: check_animation_ids([entry['records']['AnimationData'][0][0]])
            except ValueError as error: registered=False; compatibility_error=str(error)
        rows.append(dict(id=emote['id'],name=emote['name'],eligible=registered,
                         reason=compatibility_error or ('Ready for DBC-linked model export' if registered else 'Export DBC registration for the selected version first' if chosen else 'Approve an intact, technically validated matching variant for this model'),
                         animation_id=entry['records']['AnimationData'][0][0] if entry else None,
                         errors=errors,versions=[dict(version=v['version'],variant=v['variant']) for v in matches]))
    return dict(target=target,source=model['path'],original_sequences=native.count,bones=native.bone_count,dances=rows,
                missing_original_anims=model.get('missing_external_animations',[]),layout='Flat Wrath MD20 264; original external references retained')


def build_plan(request):
    target=request['target']; model=checked_model(target); raw=Path(model['path']).read_bytes(); native=Model(raw)
    files=model_files(model['path']); names={Path(p).name.casefold() for p in files}; stem=Path(model['path']).stem
    missing_skins=[stem+('%02d.skin'%i) for i in range(struct.unpack_from('<I',raw,68)[0]) if (stem+('%02d.skin'%i)).casefold() not in names]
    missing=[]
    for offset in range(0,len(native.sequences),64):
        identifier,variation,_,_,flags=struct.unpack_from('<HHIfI',native.sequences,offset)
        name=stem+('%04d-%02d.anim'%(identifier,variation))
        if not flags&(0x130|0x40) and name.casefold() not in names: missing.append(name)
    state=dbc.registry(); dbc_directory=dbc.OUTPUT/'DBFilesClient'
    marker=dbc_directory/'studio_export.json'
    if not state.get('latest_export') or not marker.is_file() or json.loads(marker.read_text())['version']!=state['latest_export']:
        raise M2Error('Commit a DBC export first; proposed IDs alone cannot be used for model export')
    from .dbc_binary import DBC
    animations=DBC.read(dbc_directory/'AnimationData.dbc'); emotes=DBC.read(dbc_directory/'Emotes.dbc')
    catalog={e['id']:e for e in read_catalog()['emotes']}; dances=[]
    ids=sorted(set(request.get('emotes',[])))
    if not ids: raise M2Error('Select at least one approved dance')
    for identifier in ids:
        if identifier not in catalog or identifier not in state['dances']: raise M2Error('Missing committed DBC identity: '+identifier)
        entry=state['dances'][identifier]; expected=entry['records']['AnimationData'][0]; expected_emote=entry['records']['Emotes'][0]
        if expected[0] not in animations.ids or animations.values(animations.ids[expected[0]])!=expected or expected_emote[0] not in emotes.ids or emotes.values(emotes.ids[expected_emote[0]])!=expected_emote:
            raise M2Error('Committed DBC records differ from allocation registry')
        variants,_=dbc.eligible_versions(catalog[identifier])
        variants=[v for v in variants if v.get('target_id','human2_male')==target]
        sex=model_sex(model)
        preferred=request.get('variant')
        order=[preferred] if preferred else ['CM'+sex,'CL'+sex] if sex else []
        chosen=next((v for kind in order for v in variants if v['variant']==kind),None)
        if chosen is None: raise M2Error('No approved matching source variant for '+identifier+' on '+target)
        if chosen.get('imported',{}).get('montage') and os.environ.get('WDS_MONTAGE_PREVIEW')!='1':
            raise M2Error('This action contains montage sections; enable Fortnite intro / loop sections in Convert & Build Pack')
        if not any(v['version']==chosen['version'] and v['target']==target and v['sha256']==chosen['action_library_sha256'] for v in entry['versions']):
            raise M2Error('Selected conversion is not in the committed DBC manifest; export DBCs again: '+identifier)
        existing={int.from_bytes(native.sequences[i:i+2],'little') for i in range(0,len(native.sequences),64)}
        if expected[0] in existing or expected[0]<len(native.lookup) and native.lookup[expected[0]]>=0: raise M2Error('Allocated animation ID collides with original model')
        if (stem+('%04d-00.anim'%expected[0])).casefold() in names: raise M2Error('New ANIM filename collides with an existing companion file')
        from .client_audio import duration_ms
        loop_region=None
        if os.environ.get('WDS_MONTAGE_PREVIEW')=='1':
            from .montage_runtime import playback
            from .montage_assets import resolve,loop_region as get_region
            playback_plan=playback(catalog[identifier],chosen['variant'])
            if not playback_plan:raise M2Error('Missing verified montage evidence for this emote variant')
            if playback_plan:
                playback_plan=resolve(catalog[identifier],playback_plan)
                if playback_plan['routing_notifies']:raise M2Error('Dynamic montage routing is not supported')
                loop_region=get_region(playback_plan)
                if abs(loop_region['duration_ms']-duration_ms(chosen))>2:raise M2Error('Converted action does not match the montage route duration; convert its missing sections first')
        full=entry.get('full_soundtrack',{})
        client_audio=entry.get('client_audio',{}).get(str(duration_ms(chosen))) if entry.get('client_audio') and not full else None
        if entry.get('client_audio') and not full and not client_audio:raise M2Error('Export DBC soundtrack records for this animation duration first')
        if client_audio:
            sounds=DBC.read(dbc_directory/'SoundEntries.dbc');sound_id=client_audio['sound_id']
            if sound_id not in sounds.ids:raise M2Error('Missing committed soundtrack SoundEntries record')
            sound=sounds.values(sounds.ids[sound_id])
            if sound[3]!=client_audio['client_file'] or sound[23]!=client_audio['client_directory']:raise M2Error('Soundtrack DBC path differs')
        dances.append(dict(emote=identifier,animation_id=expected[0],emote_id=expected_emote[0],metadata=chosen,client_audio=client_audio,full_soundtrack=full,native_loop_region=loop_region,
                           sound_ids=[r[0] for r in entry['records'].get('SoundEntries',[])],audio_assets=entry.get('sound_assets',{}),
                           metadata_sha256=digest(Path(chosen['action_library']).parent/'metadata.json')))
    client_compatibility=check_animation_ids([d['animation_id'] for d in dances])
    candidates=[]
    path=ROOT/'Input'/'DBC'/'CreatureModelData.dbc'
    if model.get('asset_source'):
        candidates=[model['asset_source']['virtual_model_path']]
    elif path.is_file():
        table=DBC.read(path)
        candidates=sorted({table.text(r[2]) for r in table.rows if PureWindowsPath(table.text(r[2])).stem.casefold()==Path(model['path']).stem.casefold()})
    return dict(schema=1,client_compatibility=client_compatibility,request=request,model=model,source_sha256=digest(model['path']),dances=dances,
                implementation={name:digest(ROOT/name) for name in ('m2_worker.py','studio_core/m2_binary.py','studio_core/m2_manager.py','studio_core/client_compatibility.py','studio_core/client_audio.py')},
                dbc_registry_hash=dbc.hashed(state),dbc_registry_path=str(dbc.OUTPUT/'registry.json'),
                dbc_export=state['latest_export'],dbc_checksums=dict(AnimationData=animations.sha256,Emotes=emotes.sha256),
                files=files,client_model_path_candidates=candidates,
                original_sequences=native.count,original_bones=native.bone_count,
                missing_original_anims=missing,
                missing_original_skins=missing_skins,
                status='Preview only. Original references retained; client archives must supply missing original ANIMs. Packaging, triggers and playback unverified.')


def preview(request):
    plan=build_plan(request); path=OUTPUT/'plans'/(uuid.uuid4().hex+'.json')
    atomic_json(path,dict(plan=plan,sha256=dbc.hashed(plan)))
    return dict(plan_path=str(path),target=plan['model']['id'],original_sequences=plan['original_sequences'],
                additions=[dict(emote=e['emote'],variant=e['metadata']['variant'],animation_id=e['animation_id'],version=e['metadata']['version']) for e in plan['dances']],
                missing_original_anim_count=len(plan['missing_original_anims']),status=plan['status'])


def validate_plan(path):
    path=Path(path).resolve()
    if not path.is_relative_to((OUTPUT/'plans').resolve()): raise M2Error('Select a plan inside Output/M2/plans')
    stored=json.loads(path.read_text()); plan=stored['plan']
    if dbc.hashed(plan)!=stored['sha256'] or build_plan(plan['request'])!=plan: raise M2Error('Model, library or DBC state changed; preview again')
    return plan


def export(path,blender,emit=print):
    OUTPUT.mkdir(parents=True,exist_ok=True)
    with locked(OUTPUT/'export.lock',timeout=3):
        plan=validate_plan(path); identifier=uuid.uuid4().hex
        stage=OUTPUT/('.stage_'+identifier); final=OUTPUT/plan['model']['id']/identifier
        stage.mkdir(); report=ROOT/'Reports'/('m2_'+identifier+'.log')
        command=[str(blender),'-b',plan['model']['scene'],'--python-exit-code','1','--python',str(ROOT/'m2_worker.py'),
                 '--','--plan',str(Path(path).resolve()),'--stage',str(stage)]
        try:
            with report.open('w',encoding='utf-8') as log:
                process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
                for line in process.stdout:
                    log.write(line)
                    if line.startswith('STUDIO:'): emit(line.rstrip())
                code=process.wait()
            if code: raise M2Error('M2 worker failed; inspect '+str(report))
            validate_plan(path)
            result=json.loads((stage/'manifest.json').read_text())
            for filename,sha in result['output_checksums'].items():
                if digest(stage/filename)!=sha: raise M2Error('Staged output changed')
            final.parent.mkdir(parents=True,exist_ok=True); stage.rename(final)
            result=dict(output=str(final),model=plan['model']['id'],animations=len(plan['dances']),
                        client_playback_verified=False,missing_original_anims=len(plan['missing_original_anims']),log=str(report))
            atomic_json(OUTPUT/'last_export.json',result); return result
        finally:
            if stage.exists():
                if not stage.resolve().is_relative_to(OUTPUT.resolve()) or stage.name!='.stage_'+identifier: raise M2Error('Invalid staging cleanup path')
                shutil.rmtree(stage)
