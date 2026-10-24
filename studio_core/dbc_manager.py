"""Previewed, cumulative DBC additions with persistent global dance allocations."""
import copy
import hashlib
import json
import os
import re
import shutil
import struct
import uuid
import wave
from pathlib import Path,PureWindowsPath
from .catalog import ROOT,read_catalog,digest
from .storage import atomic_json,locked
from .dbc_binary import DBC,DBCError,load_tables,reference_errors
from .dbc_schema import PRIMARY,SCHEMAS

INPUT=ROOT/'Input'/'DBC'
OUTPUT=ROOT/'Output'/'DBC'


def hashed(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def registry():
    path=OUTPUT/'registry.json'
    state=json.loads(path.read_text(encoding='utf-8')) if path.exists() else dict(schema=1,dances={},latest_export=None)
    if state.get('schema')!=1 or not isinstance(state.get('dances'),dict): raise DBCError('Invalid DBC allocation registry')
    return state


def inputs():
    tables,status=load_tables(INPUT)
    problems=[r for r in status if r.get('valid') is False and r.get('status')!='Missing optional']
    if problems: raise DBCError('Invalid/missing baseline DBCs: '+json.dumps(problems))
    return tables,status


def model_constraints():
    """Flat MD20 264: sequence ID uint16, 64-byte sequences, int16 lookup.

    Verified against the installed Elune 264 parser and CoA M2Header.
    Reserve observed sequence and occupied lookup IDs, not a guessed custom range.
    """
    used={0,65535}; hashes={}
    for path in sorted((ROOT/'Input'/'WoW').rglob('*')):
        if not path.is_file() or path.suffix.lower()!='.m2': continue
        data=path.read_bytes()
        if len(data)<44 or data[:4]!=b'MD20' or struct.unpack_from('<I',data,4)[0]!=264:
            raise DBCError('Cannot safely inspect animation IDs in '+str(path))
        count,offset,lookups,lookup_offset=struct.unpack_from('<4I',data,28)
        if offset+count*64>len(data) or lookup_offset+lookups*2>len(data): raise DBCError('Invalid M2 animation table: '+str(path))
        used.update(struct.unpack_from('<H',data,offset+i*64)[0] for i in range(count))
        used.update(i for i in range(lookups) if struct.unpack_from('<h',data,lookup_offset+i*2)[0]>=0)
        hashes[str(path)]=hashlib.sha256(data).hexdigest()
    return used,hashes


def eligible_versions(emote):
    from .cache import valid_output
    from .models import checked_profile
    good=[]; errors=[]
    for version in emote.get('versions',[]):
        try:
            if version.get('id')!=emote['id']: raise DBCError('Library metadata belongs to another emote')
            authorization=emote.get('export_authorizations',{}).get(version['version'],{})
            batch_authorized=(authorization.get('kind')=='user_requested_batch_export' and
                              authorization.get('sha256')==version.get('action_library_sha256') and
                              authorization.get('profile_sha256')==version.get('profile_sha256'))
            if version['version'] not in emote.get('approvals',{}) and not batch_authorized:
                raise DBCError('Animation visual review/Mark Approved required')
            if not valid_output(version): raise DBCError('Stored action or metadata is missing/changed')
            if not Path(version['profile_path']).is_file() or digest(version['profile_path'])!=version['profile_sha256']:
                raise DBCError('Converted bone profile is missing/changed')
            profile=checked_profile(version['profile_path'],version.get('target_id','human2_male'),_scene(version))
            validation=version['validation']
            if not validation.get('finite_transforms') or not validation.get('changing_sampled_transforms'):
                raise DBCError('Animation technical validation missing')
            if not validation.get('preservation',{}).get('rest_hierarchy_preserved'): raise DBCError('Original-data preservation check missing')
            if profile.get('generator') and not validation.get('motion',{}).get('passed'): raise DBCError('Model motion validation missing')
            if profile['target_signature']!=version['target_signature']: raise DBCError('Converted target/profile identity differs')
            good.append(version)
        except (ValueError,OSError,KeyError,TypeError) as error:
            errors.append(dict(version=version.get('version'),target=version.get('target_id'),reason=str(error)))
    # One most recently stored approved version per target/variant; explicit
    # selected_versions wins when it is eligible.
    selected={}
    for version in good:
        key=version.get('target_id','human2_male')+':'+version['variant']
        preferred=emote.get('selected_versions',{}).get(key)
        if key not in selected or selected[key]['version']!=preferred: selected[key]=version
    return list(selected.values()),errors


def _scene(version):
    from .models import get_model,checked_digest
    if version.get('target_id','human2_male')=='human2_male' and not version.get('profile_revision'):
        path=ROOT/'Blender'/'Human2_AutumnTea_Retarget.blend'
        if checked_digest(path)!=version['baseline_sha256']: raise DBCError('Converted baseline scene changed')
        return str(path)
    model=get_model(version['target_id'])
    if checked_digest(model['scene'])!=version['baseline_sha256']: raise DBCError('Converted model scene changed')
    return model['scene']


def scan():
    tables,status=load_tables(INPUT)
    library=[]
    for emote in read_catalog()['emotes']:
        if not emote.get('versions'): continue
        versions,errors=eligible_versions(emote)
        library.append(dict(id=emote['id'],name=emote['name'],eligible=bool(versions),has_audio=bool(emote.get('audio')),
                            versions=[dict(version=v['version'],target=v.get('target_id'),variant=v['variant']) for v in versions],errors=errors))
    state=registry()
    return dict(files=status,original_reference_diagnostics=reference_errors(tables),library=library,
                custom_ids=state['dances'],latest_export=state.get('latest_export'),
                sound_templates=[dict(id=r[0],name=tables['SoundEntries'].text(r[2]),sound_type=r[1],flags=r[25],native_cycle_compatible=r[25]==0 and r[29]==0)
                                 for r in tables.get('SoundEntries',_Empty()).rows if r[0] in {e[6] for e in tables.get('Emotes',_Empty()).rows if e[6]}],
                text_sound_targets=[dict(race_id=r[0],name=tables['ChrRaces'].text(r[14])) for r in tables.get('ChrRaces',_Empty()).rows],
                experimental_dance_moves='Read-only. CoA dance-studio CMSG handlers are STATUS_NEVER / Handle_NULL.')


class _Empty:
    rows=()


def allocate(used,limit):
    value=max(used,default=0)+1
    if value>=limit:
        value=next((i for i in range(1,limit) if i not in used),None)
    if value is None: raise DBCError('No available IDs within the verified field limit')
    used.add(value); return value


def sound_asset(media,role,identifier):
    from .fortnite_paths import allowed_audio
    if role not in {'intro','loop','track'}: raise DBCError('Unsupported soundtrack role: '+str(role))
    path=Path(media['path'])
    if not allowed_audio(path) or not path.is_file() or digest(path)!=media['sha256']:
        raise DBCError('Audio missing/changed or outside Fortnite inputs: '+str(path))
    if path.suffix.lower()!='.wav': raise DBCError('Sound export currently requires inspected PCM WAV; no unchecked MP3/OGG passthrough')
    try:
        with wave.open(str(path),'rb') as stream:
            if stream.getcomptype()!='NONE' or stream.getsampwidth()!=2 or stream.getnchannels() not in (1,2) or stream.getframerate() not in (22050,44100,48000):
                raise DBCError('Unsupported PCM encoding: '+str(path))
            encoding=dict(codec='PCM_S16LE',channels=stream.getnchannels(),sample_rate=stream.getframerate(),samples=stream.getnframes())
    except (wave.Error,EOFError) as error: raise DBCError('Unreadable PCM WAV: '+str(path)) from error
    name=role+'.wav'; directory='Sound\\WoWDanceStudio\\'+identifier+'\\'
    return dict(source=str(path),sha256=media['sha256'],client_directory=directory,client_file=name,
                encoding=encoding,client_playback_verified=False,packaging_required=True)


def build_plan(request):
    tables,status=inputs(); state=registry(); next_state=copy.deepcopy(state)
    request=copy.deepcopy(request)
    requested=sorted(set(request.get('emotes',[])))
    if any(not re.fullmatch('[a-z0-9]+',i) for i in requested): raise DBCError('Invalid emote identity')
    request['emotes']=requested
    all_ids=sorted(set(requested)|set(state['dances']))
    if request.get('include_text') and any(n not in tables for n in ('EmotesText','EmotesTextData')):
        raise DBCError('Text export requires original EmotesText and EmotesTextData')
    if request.get('text_sound_target') and (not request.get('include_text') or not request.get('include_sound') or 'EmotesTextSound' not in tables or 'ChrRaces' not in tables):
        raise DBCError('Text sound mapping requires text, sound, original EmotesTextSound and ChrRaces')
    anims=tables['AnimationData']; emotes=tables['Emotes']
    dance=[r for r in anims.rows if anims.text(r[1]).casefold()=='emotedance']
    if len(dance)!=1: raise DBCError('Need one verified EmoteDance baseline AnimationData row')
    continuous=[r for r in emotes.rows if emotes.text(r[1])=='STATE_DANCE' and r[2]==dance[0][0] and r[4]==2 and r[5]==0]
    if len(continuous)!=1: raise DBCError('Need a unique continuous STATE_DANCE baseline linked to EmoteDance')
    animation_base=anims.values(dance[0]); emote_base=emotes.values(continuous[0])
    occupied,m2_hashes=model_constraints()
    used={name:set(table.ids) for name,table in tables.items()}
    used['AnimationData'].update(occupied)
    reserved={name:{} for name in tables}
    for owner,entry in state['dances'].items():
        for name,rows in entry['records'].items():
            if name not in tables: raise DBCError('A previous allocation requires missing baseline '+name)
            for row in rows:
                identifier=row[0]
                if name=='AnimationData' and not 0<identifier<65535: raise DBCError('Allocated animation ID exceeds uint16 constraints')
                if identifier in reserved[name] and reserved[name][identifier]!=owner: raise DBCError('Allocation registry ID collision')
                reserved[name][identifier]=owner; used[name].add(identifier)
                if name=='AnimationData' and identifier in occupied: raise DBCError('Previously allocated animation ID now occupied by supplied M2s')
    additions={name:[] for name in tables}; manifest=[]; library={e['id']:e for e in read_catalog()['emotes']}
    for identifier in all_ids:
        if identifier not in library: raise DBCError('Previously allocated emote is absent from the library: '+identifier)
        emote=library[identifier]; versions,errors=eligible_versions(emote)
        if not versions: raise DBCError('No approved technically validated library version for '+identifier+': '+json.dumps(errors))
        entry=copy.deepcopy(state['dances'].get(identifier,{}))
        if entry.get('sound_assets'):
            assets={role:sound_asset(media,role,identifier) for role,media in sorted(emote.get('audio',{}).items())}
            if assets!=entry['sound_assets']: raise DBCError('Previously exported audio changed: '+identifier)
        records=entry.setdefault('records',{})
        if 'AnimationData' not in records:
            animation=allocate(used['AnimationData'],65535)
            row=list(animation_base); row[0]=animation; row[1]='WDS_'+identifier; row[5]=animation_base[0]; row[6]=animation
            records['AnimationData']=[row]
            row=list(emote_base); row[0]=allocate(used['Emotes'],0x100000000); row[1]='WDS_'+identifier.upper(); row[2]=animation; row[6]=0
            records['Emotes']=[row]
            entry['templates']=dict(animation=animation_base,emote=emote_base,reason='Documented continuous STATE_DANCE / EmoteSpecProc 2; existing dance behavior/flags retained, fallback to original dance')
        if identifier in requested and request.get('include_sound') and (emote.get('audio') or not request.get('include_client_audio')):
            audio=emote.get('audio',{})
            if not audio: raise DBCError('No soundtrack for '+identifier+'; uncheck Include Sound Records')
            sound_table=tables['SoundEntries']; template_id=request.get('sound_template')
            if template_id not in sound_table.ids: raise DBCError('Select an existing reviewed SoundEntries template ID')
            template=sound_table.values(sound_table.ids[template_id])
            if DBC.f32(template[24])<0 or DBC.f32(template[24])>1: raise DBCError('Invalid sound template volume')
            if template[29]: raise DBCError('Select a sound template without AdvancedID; reusing another sound entry\'s advanced chain is unsupported')
            assets={role:sound_asset(media,role,identifier) for role,media in sorted(audio.items())}
            if entry.get('sound_assets') and entry['sound_assets']!=assets: raise DBCError('Previously exported audio changed; append-only audio revisions require a new explicit identity')
            entry['sound_assets']=assets
            if 'SoundEntries' not in records:
                rows=[]
                for role,asset in (assets.items() if not request.get('include_client_audio') else ()):
                    row=list(template); row[0]=allocate(used['SoundEntries'],0x100000000); row[2]='WDS_'+identifier+'_'+role
                    row[3:13]=[asset['client_file']]+['']*9; row[13:23]=[1]+[0]*9; row[23]=asset['client_directory']
                    rows.append(row); asset['sound_id']=row[0]
                # IDs belong to records; omit them from content identity comparisons.
                for asset in assets.values(): asset.pop('sound_id',None)
                records['SoundEntries']=rows; entry['sound_template']=template
            if request.get('full_soundtrack'):
                full=entry.setdefault('full_soundtrack',{})
                for role,asset in assets.items():
                    if role in full:continue
                    row=list(template);row[0]=allocate(used['SoundEntries'],0x100000000);row[2]='WDS_'+identifier+'_full_'+role
                    filename='full_'+role+'.wav';directory='Sound\\WoWDanceStudio\\'+identifier+'\\'
                    row[3:13]=[filename]+['']*9;row[13:23]=[1]+[0]*9;row[23]=directory
                    records.setdefault('SoundEntries',[]).append(row)
                    encoding=asset['encoding']
                    full[role]=dict(source=asset['source'],sha256=asset['sha256'],sound_id=row[0],client_directory=directory,
                                    client_file=filename,duration_ms=round(encoding['samples']*1000/encoding['sample_rate']))
            elif request.get('include_client_audio'):
                from .client_audio import duration_ms
                if template[25]!=0: raise DBCError('Native soundtrack cycles require a non-looping SoundEntries template with Flags 0')
                cycles=entry.setdefault('client_audio',{})
                for cycle in cycles.values():cycle['trigger']='M2 $CSD character event each animation cycle'
                for version in versions:
                    duration=duration_ms(version);key=str(duration)
                    if key in cycles:continue
                    filename='cycle_'+key+'ms.wav'
                    row=list(template);row[0]=allocate(used['SoundEntries'],0x100000000);row[2]='WDS_'+identifier+'_cycle_'+key
                    row[3:13]=[filename]+['']*9;row[13:23]=[1]+[0]*9;row[23]='Sound\\WoWDanceStudio\\'+identifier+'\\'
                    records['SoundEntries'].append(row)
                    cycles[key]=dict(duration_ms=duration,sound_id=row[0],client_directory=row[23],client_file=filename,parts=assets,
                                     trigger='M2 $CSD character event each animation cycle',client_playback_verified=False)
        if identifier in requested and request.get('include_text') and 'EmotesText' not in records:
            text_id=allocate(used['EmotesTextData'],0x100000000)
            records['EmotesTextData']=[[text_id,'performs '+emote['name']+'.']+['']*15+[0]]
            records['EmotesText']=[[allocate(used['EmotesText'],0x100000000),'WDS_'+identifier,records['Emotes'][0][0],text_id]+[0]*15]
        target=request.get('text_sound_target') if identifier in requested else None
        if target:
            race,sex=target['race_id'],target['sex_id']
            if race not in tables['ChrRaces'].ids or sex not in (0,1): raise DBCError('Invalid explicit text sound race/sex')
            sounds=records.get('SoundEntries',[])
            # Explicit trigger only: intro, then track, then loop. No scheduling claim.
            chosen=next((r for role in ('intro','track','loop') for r in sounds if r[2].endswith('_'+role)),None)
            if chosen is None: raise DBCError('Text sound mapping requires generated sound records')
            links=records.setdefault('EmotesTextSound',[])
            if not any(r[2]==race and r[3]==sex for r in links):
                links.append([allocate(used['EmotesTextSound'],0x100000000),records['EmotesText'][0][0],race,sex,chosen[0]])
        for name,rows in records.items():
            if name not in tables: raise DBCError('Missing required original '+name)
            for row in rows:
                if row[0] in tables[name].ids:
                    if tables[name].values(tables[name].ids[row[0]])!=row: raise DBCError(f'{name} ID {row[0]} collides with an original entry')
                else: additions[name].append(row)
        entry['versions']=[dict(target=v.get('target_id','human2_male'),variant=v['variant'],version=v['version'],
                                profile_sha256=v['profile_sha256'],action_library=v['action_library'],sha256=v['action_library_sha256'],metadata_sha256=digest(Path(v['action_library']).parent/'metadata.json')) for v in versions]
        entry['status']='DBC records staged; M2/ANIM/client packaging and trigger testing still required'
        next_state['dances'][identifier]=entry
        manifest.append(dict(emote=identifier,animation_id=records['AnimationData'][0][0],emote_id=records['Emotes'][0][0],
                             sound_ids=[r[0] for r in records.get('SoundEntries',[])],text_ids=[r[0] for r in records.get('EmotesText',[])],
                              client_audio=entry.get('client_audio',{}),full_soundtrack=entry.get('full_soundtrack',{}),
                             models=entry['versions'],audio=entry.get('sound_assets',{}),prop_status=emote.get('prop_status'),
                             audio_schedule='Native M2 $CSD starts one rendered soundtrack per animation cycle; EventSoundID remains 0.' if entry.get('client_audio') else 'Intro and loop kept separate. EventSoundID remains 0; synchronized scheduling is not implemented.',
                             audio_timing={v['version']:v.get('audio_timing',{}) for v in versions},
                             client_playable=False,slash_command_verified=False,templates=entry['templates'],sound_template=entry.get('sound_template')))
    rebuilt={name:DBC(table.append(additions[name]),name) for name,table in tables.items()}
    new_refs=reference_errors(rebuilt,{name:{r[0] for r in rows} for name,rows in additions.items()})
    if new_refs: raise DBCError('New records contain broken references: '+json.dumps(new_refs))
    return dict(schema=1,request=request,registry_hash=hashed(state),next_registry=next_state,
                baselines={name:table.sha256 for name,table in tables.items()},m2_inputs=m2_hashes,
                additions=additions,counts={n:len(r) for n,r in additions.items()},manifest=manifest,
                baseline_reference_diagnostics=reference_errors(tables),
                constraints='Animation IDs exclude original DBC IDs, supplied M2 sequences/lookups and registry reservations; uint16, 65535 sentinel reserved. Client acceptance unverified.')


def preview(request):
    plan=build_plan(request); identifier=uuid.uuid4().hex
    path=OUTPUT/'plans'/(identifier+'.json')
    atomic_json(path,dict(plan=plan,sha256=hashed(plan)))
    proposed={name:[{field:(DBC.f32(value) if i in SCHEMAS[name].floats else value) for i,(field,value) in enumerate(zip(SCHEMAS[name].fields,row))} for row in rows] for name,rows in plan['additions'].items()}
    result=dict(plan_path=str(path),counts=plan['counts'],manifest=plan['manifest'],proposed_records=proposed)
    atomic_json(OUTPUT/'preview.json',result)
    return result


def validate_plan(path):
    path=Path(path).resolve()
    if not path.is_relative_to((OUTPUT/'plans').resolve()): raise DBCError('Select a preview plan inside Output/DBC/plans')
    stored=json.loads(path.read_text(encoding='utf-8')); plan=stored['plan']
    if hashed(plan)!=stored['sha256']: raise DBCError('Preview plan changed')
    fresh=build_plan(plan['request'])
    if fresh!=plan: raise DBCError('Baseline, registry, M2 constraints or library state changed; preview again')
    return plan


def recover():
    journal=OUTPUT/'transaction.json'
    if not journal.exists(): return
    change=json.loads(journal.read_text()); current=OUTPUT/'DBFilesClient'
    archive=OUTPUT/change['archive']; version=change['version']
    if Path(change['archive']).name!=change['archive'] or not archive.resolve().is_relative_to(OUTPUT.resolve()) or not re.fullmatch('[a-zA-Z0-9_]+',version):
        raise DBCError('Invalid export recovery paths; refusing to move files')
    marker=current/'studio_export.json'
    if registry().get('latest_export')==version:
        if not marker.exists() or json.loads(marker.read_text()).get('version')!=version:
            raise DBCError('Committed export directory missing; recover from immutable export bundle '+version)
    else:
        if current.exists() and marker.exists() and json.loads(marker.read_text()).get('version')==version:
            current.rename(OUTPUT/('interrupted_'+version))
        if archive.exists() and not current.exists(): archive.rename(current)
        if change['old_exists']: atomic_json(OUTPUT/'registry.json',change['old_registry'])
        elif (OUTPUT/'registry.json').exists(): (OUTPUT/'registry.json').unlink()
    journal.unlink()


def export(path):
    OUTPUT.mkdir(parents=True,exist_ok=True)
    with locked(OUTPUT/'export.lock',timeout=3):
        recover(); plan=validate_plan(path); old=registry(); version=uuid.uuid4().hex
        bundle=OUTPUT/'exports'/version; stage=OUTPUT/('.stage_'+version); current=OUTPUT/'DBFilesClient'
        if current.exists() and not (current/'studio_export.json').is_file(): raise DBCError('Output DBFilesClient is not a managed export; refusing to overwrite')
        stage.mkdir(); tables,_=inputs(); checks=[]
        try:
            for name,table in tables.items():
                data=table.append(plan['additions'][name]); destination=stage/(name+'.dbc')
                with destination.open('xb') as stream: stream.write(data); stream.flush(); os.fsync(stream.fileno())
                reopened=DBC.read(destination)
                if reopened.records[:len(table.records)]!=table.records or reopened.strings[:len(table.strings)]!=table.strings:
                    raise DBCError('Original bytes changed after disk reopen')
                checks.append(dict(table=name,original_records=table.count,new_records=len(plan['additions'][name]),sha256=reopened.sha256,original_records_and_offsets_preserved=True))
            atomic_json(stage/'studio_export.json',dict(version=version,manifest=plan['manifest'],checks=checks,
                        baseline_reference_diagnostics=plan['baseline_reference_diagnostics'],client_playable=False))
            bundle.parent.mkdir(parents=True,exist_ok=True)
            shutil.copytree(stage,bundle/'DBFilesClient')
            new=plan['next_registry']; new['latest_export']=version
            for entry in new['dances'].values(): entry.update(export_version=version,export_status='exported_dbc_only_client_integration_pending')
            atomic_json(bundle/'registry.json',new)
            archive='history_'+version
            atomic_json(OUTPUT/'transaction.json',dict(version=version,archive=archive,old_registry=old,old_exists=(OUTPUT/'registry.json').exists()))
            try:
                if current.exists(): current.rename(OUTPUT/archive)
                stage.rename(current)
                atomic_json(OUTPUT/'registry.json',new)
            except Exception:
                recover(); raise
            (OUTPUT/'transaction.json').unlink()
            result=dict(version=version,output=str(current),immutable_copy=str(bundle/'DBFilesClient'),counts=plan['counts'],checks=checks)
            atomic_json(OUTPUT/'last_export.json',result)
            return result
        finally:
            # Unpublished temporary data only; immutable exports/history remain.
            if stage.exists():
                if not stage.resolve().is_relative_to(OUTPUT.resolve()) or stage.name!='.stage_'+version:
                    raise DBCError('Refusing cleanup outside this export staging folder')
                shutil.rmtree(stage)
