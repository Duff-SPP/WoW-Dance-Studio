"""Assemble immutable, checksum-verified client/server deployment folders."""
import json
import shutil
import uuid
from pathlib import Path, PureWindowsPath
from .catalog import ROOT, digest
from .storage import atomic_json, locked
from .dbc_binary import DBC
from .m2_binary import Model,UNIT_SOUND_EVENT
from .client_compatibility import check_animation_ids

OUTPUT = ROOT / 'Output' / 'Packs'
MODELS = ROOT / 'Output' / 'M2'
SERVER_TABLES = ('Emotes', 'EmotesText', 'SoundEntries')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def deployment_files(manifest):
    """Omit byte-identical baseline companions, retaining required changes."""
    baseline={Path(name).name.casefold():sha for name,sha in manifest.get('input_checksums',{}).items()}
    checks=manifest['output_checksums']
    stem=Path(next(n for n in checks if n.lower().endswith('.m2'))).stem
    new_anims={(stem+('%04d-00.anim'%d['animation_id'])).casefold() for d in manifest['dances']}
    included={};dependencies={}
    for name,sha in checks.items():
        companion=Path(name).suffix.lower() in ('.anim','.skin')
        if companion and name.casefold() not in new_anims and baseline.get(name.casefold())==sha:
            dependencies[name]=sha
        else:included[name]=sha
    return included,dependencies


def safe_file(folder, name):
    if not name or Path(name).name != name or '/' in name or '\\' in name:
        raise ValueError('Invalid package filename: ' + str(name))
    path = folder / name
    if path.is_symlink() or not path.resolve().is_relative_to(folder.resolve()):
        raise ValueError('Package file escapes its folder')
    return path


def inspect(paths):
    if not paths:
        raise ValueError('Select at least one model export')
    rows = []; targets = set(); dbc_source = None; export_id = None
    for item in paths:
        folder = Path(item).resolve()
        if not folder.is_relative_to(MODELS.resolve()) or folder.name.startswith('.'):
            raise ValueError('Select a published export inside Output/M2')
        manifest = read(folder / 'manifest.json')
        check_animation_ids([d['animation_id'] for d in manifest['dances']])
        if manifest['model'] in targets:
            raise ValueError('Select only one export per target model')
        targets.add(manifest['model'])
        candidates = manifest['client_model_path_candidates']
        if len(candidates) != 1:
            raise ValueError('Model needs one unambiguous client path: ' + manifest['model'])
        model_path = PureWindowsPath(candidates[0]).with_suffix('.m2')
        if model_path.is_absolute() or model_path.drive or '..' in model_path.parts or model_path.parts[0].lower() != 'character':
            raise ValueError('Unsafe client model path')
        checks = manifest['output_checksums']
        model_files = [n for n in checks if n.lower().endswith('.m2')]
        if len(model_files) != 1 or model_files[0].casefold() != model_path.name.casefold():
            raise ValueError('Model filename disagrees with client path')
        native = Model(safe_file(folder, model_files[0]).read_bytes())
        if not checks or not any(n.lower().endswith('.m2') for n in checks):
            raise ValueError('Export has no model')
        for name, sha in checks.items():
            if digest(safe_file(folder, name)) != sha:
                raise ValueError('Model export changed: ' + name)
        if manifest.get('missing_original_skins'):
            raise ValueError('Missing required original SKIN files: ' + manifest['model'])
        source = Path(manifest['dbc_registry_path']).resolve().parent / 'exports' / manifest['dbc_export'] / 'DBFilesClient'
        if not source.resolve().is_relative_to((ROOT / 'Output').resolve()):
            raise ValueError('DBC snapshot outside project Output')
        marker = read(source / 'studio_export.json')
        if marker['version'] != manifest['dbc_export']:
            raise ValueError('DBC snapshot identity differs')
        if export_id and (export_id != marker['version'] or dbc_source != source):
            raise ValueError('Selected models need the same DBC export; re-export models against one shared DBC snapshot')
        export_id = marker['version']; dbc_source = source
        for name, sha in manifest['dbc_checksums'].items():
            if digest(source / (name + '.dbc')) != sha:
                raise ValueError('DBC and model checksums differ')
        allocations = {d['emote']: d for d in marker['manifest']}
        animation_table = DBC.read(source / 'AnimationData.dbc')
        emote_table = DBC.read(source / 'Emotes.dbc')
        for dance in manifest['dances']:
            aid = dance['animation_id']; eid = dance['emote_id']
            if aid not in animation_table.ids or eid not in emote_table.ids or emote_table.values(emote_table.ids[eid])[2] != aid:
                raise ValueError('DBC tables do not link the selected animation')
            if aid >= len(native.lookup) or native.lookup[aid] < 0:
                raise ValueError('M2 animation lookup is missing')
            index = native.lookup[aid]
            native.validate_load_ring(index)
            if int.from_bytes(native.sequences[index*64:index*64+2], 'little') != aid:
                raise ValueError('M2 animation lookup differs')
            anim_name = Path(model_files[0]).stem + ('%04d-00.anim' % aid)
            if anim_name not in checks:
                raise ValueError('New ANIM file is missing')
            audio=dance.get('client_audio')
            if audio:
                import struct
                events=native.array(256,36);found=False
                for event_index in range(len(events)//36):
                    event=events[event_index*36:(event_index+1)*36]
                    if event[:4]!=UNIT_SOUND_EVENT or struct.unpack_from('<I',event,4)[0]!=audio['sound_id']:continue
                    _,global_sequence,pairs=native.descriptors(event,24,True)
                    if global_sequence!=65535 or index>=len(pairs[0]):continue
                    count,offset=pairs[0][index]
                    raw=safe_file(folder,anim_name).read_bytes()
                    if count==1 and offset+4<=len(raw) and struct.unpack_from('<I',raw,offset)[0]==1:found=True
                if not found:raise ValueError('Missing native M2 soundtrack event')
            allocation = allocations.get(dance['emote'])
            duration=int.from_bytes(native.sequences[index*64+4:index*64+8],'little')
            full=dance.get('full_soundtrack',{})
            if full and (not allocation or full!=allocation.get('full_soundtrack',{})):raise ValueError('Full soundtrack differs from committed DBC snapshot')
            expected_audio=allocation.get('client_audio',{}).get(str(duration)) if allocation and not full else None
            if expected_audio and audio!=expected_audio:raise ValueError('Re-export M2/ANIM with the committed native soundtrack event')
            if audio and (not allocation or allocation.get('client_audio',{}).get(str(audio['duration_ms']))!=audio):
                raise ValueError('Model soundtrack differs from committed DBC snapshot')
            if not allocation or any(allocation[k] != dance[k] for k in ('animation_id', 'emote_id')):
                raise ValueError('Model and DBC animation IDs differ')
            if not any(v['target'] == manifest['model'] and v['version'] == dance['version'] for v in allocation['models']):
                raise ValueError('Model action version is absent from DBC snapshot')
        rows.append(dict(folder=str(folder), model=manifest['model'], client_directory=str(model_path.parent), manifest=manifest,
                         manifest_sha256=digest(folder / 'manifest.json')))
    dbc_files = {}
    for check in marker['checks']:
        name = check['table'] + '.dbc'; path = safe_file(dbc_source, name)
        if digest(path) != check['sha256']:
            raise ValueError('DBC snapshot changed: ' + name)
        DBC.read(path)
        dbc_files[name] = check['sha256']
    if not all(n + '.dbc' in dbc_files for n in ('AnimationData', 'Emotes')):
        raise ValueError('Incomplete DBC snapshot')
    audio_assets=[]
    selected_emotes={dance['emote'] for row in rows for dance in row['manifest']['dances']}
    from .dbc_manager import sound_asset
    sound_table=DBC.read(dbc_source/'SoundEntries.dbc') if any(d.get('sound_ids') for d in marker['manifest']) else None
    for dance in marker['manifest']:
        if dance['emote'] not in selected_emotes:continue
        sound_paths=set()
        for sound_id in dance.get('sound_ids',[]):
            if sound_table is None or sound_id not in sound_table.ids:raise ValueError('Missing soundtrack SoundEntries row')
            sound=sound_table.values(sound_table.ids[sound_id])
            sound_paths.update(str(PureWindowsPath(sound[23])/name).casefold() for name in sound[3:13] if name)
        for role,asset in dance.get('audio',{}).items():
            checked=sound_asset(dict(path=asset['source'],sha256=asset['sha256']),role,dance['emote'])
            if checked!=asset:raise ValueError('Sound source metadata differs')
            if str(PureWindowsPath(asset['client_directory'])/asset['client_file']).casefold() in sound_paths:
                audio_assets.append(dict(kind='source',asset=asset))
        for role,asset in dance.get('full_soundtrack',{}).items():
            original=dance.get('audio',{}).get(role)
            if not original or asset['source']!=original['source'] or asset['sha256']!=original['sha256']:raise ValueError('Full soundtrack source differs')
            sound=sound_table.values(sound_table.ids[asset['sound_id']])
            if sound[3]!=asset['client_file'] or sound[23]!=asset['client_directory']:raise ValueError('Full soundtrack DBC path differs')
            audio_assets.append(dict(kind='full',asset=asset))
        for asset in (dance.get('client_audio',{}).values() if not dance.get('full_soundtrack') else ()):
            if asset['parts']!=dance.get('audio',{}):raise ValueError('Soundtrack cycle sources differ')
            audio_assets.append(dict(kind='cycle',asset=asset))
    compatibility=check_animation_ids([d['animation_id'] for row in rows for d in row['manifest']['dances']])
    return dict(audio_assets=audio_assets,client_compatibility=compatibility,models=rows, dbc_source=str(dbc_source), dbc_export=export_id, dbc_files=dbc_files,
                dbc_marker_sha256=digest(dbc_source / 'studio_export.json'))


def scan():
    rows = []
    for path in sorted(MODELS.glob('*/*/manifest.json'), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            m = read(path); inspect([str(path.parent)])
            rows.append(dict(path=str(path.parent), model=m['model'], eligible=True,
                label=m['model']+' | '+', '.join(d['emote'] for d in m['dances'])+' | '+path.parent.name[:8]+(' | TEST FIXTURE' if m.get('acceptance_fixture') else '')))
        except (ValueError, KeyError, OSError) as exc:
            rows.append(dict(path=str(path.parent), eligible=False, label=path.parent.parent.name+' | unavailable: '+str(exc)))
    result=dict(packages=rows)
    atomic_json(OUTPUT / 'scan.json', result)
    return result


def build(request):
    paths = request.get('packages', [])
    addon_audio=request.get('addon_audio',True)
    if not isinstance(addon_audio,bool):raise ValueError('addon_audio must be true or false')
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with locked(OUTPUT / 'build.lock', timeout=3):
        plan = inspect(paths)
        if not addon_audio and any(d.get('full_soundtrack') for row in plan['models'] for d in row['manifest']['dances']):
            raise ValueError('Full independent soundtracks require addon-managed music')
        identifier = uuid.uuid4().hex
        stage = OUTPUT / ('.stage_' + identifier); final = OUTPUT / ('DancePack_' + identifier)
        stage.mkdir()
        try:
            destinations = set()
            dependencies = {}
            transformations=[]
            def copy(source, relative, sha):
                target = stage / relative
                key = str(relative).casefold()
                if key in destinations: raise ValueError('Client path collision: '+str(relative))
                destinations.add(key); target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                if digest(target) != sha: raise ValueError('File changed while building pack')
            for row in plan['models']:
                folder = Path(row['folder']); base = Path('Client', *PureWindowsPath(row['client_directory']).parts)
                included,omitted=deployment_files(row['manifest'])
                dependencies[row['model']]={str(PureWindowsPath(row['client_directory'])/name):sha for name,sha in omitted.items()}
                for name, sha in included.items():
                    copy(safe_file(folder, name), base / name, sha)
                    if addon_audio and name.lower().endswith('.m2'):
                        from .addon import suppress_native_sound
                        deployed=stage/base/name
                        raw,changes=suppress_native_sound(deployed.read_bytes(),row['manifest'])
                        if changes:
                            deployed.write_bytes(raw)
                            transformations.append(dict(file=str(base/name),source_sha256=sha,deployed_sha256=digest(deployed),suppressed_events=changes))
                copy(folder / 'manifest.json', Path('Metadata', row['model']+'.json'), row['manifest_sha256'])
            for name, sha in plan['dbc_files'].items():
                source = Path(plan['dbc_source']) / name
                copy(source, Path('Client', 'DBFilesClient', name), sha)
                if Path(name).stem in SERVER_TABLES:
                    copy(source, Path('Server', 'dbc', name), sha)
            from .client_audio import render_cycle,render_full
            for media in plan['audio_assets']:
                asset=media['asset'];virtual=PureWindowsPath(asset['client_directory'])/asset['client_file']
                if virtual.is_absolute() or virtual.drive or '..' in virtual.parts or virtual.parts[0].lower()!='sound':raise ValueError('Unsafe soundtrack path')
                relative=Path('Client',*virtual.parts)
                if media['kind']=='source':copy(Path(asset['source']),relative,asset['sha256'])
                else:
                    if str(relative).casefold() in destinations:raise ValueError('Soundtrack path collision')
                    destinations.add(str(relative).casefold())
                    (render_full if media['kind']=='full' else render_cycle)(asset,stage/relative)
            if inspect(paths) != plan: raise ValueError('Source exports changed during assembly')
            warnings = {r['model']: r['manifest']['missing_original_anims'] for r in plan['models'] if r['manifest']['missing_original_anims']}
            text = ('WoW Dance Studio deployment folder\n\n'
                    'Client/: virtual archive paths for your client patch. This folder is not an MPQ.\n'
                    'Server/dbc/: matching Emotes, EmotesText and SoundEntries tables when supplied.\n'
                    'Back up existing files. Verify compatibility with your server/client baseline before installation.\n'
                    'The tool has not installed anything or changed the server. Restart/reload requirements depend on your server.\n'
                    'Use the client DLL required by client_compatibility in manifest.json; DBC/M2 files cannot update that DLL.\n'
                    'Original missing ANIM references must be supplied by existing client archives. See manifest.json.\n'
                    'Minimal pack: unchanged original ANIM and SKIN files are omitted. Existing matching client patches must supply them.\n'
                    'M2 files, new emote ANIMs and changed/unknown SKIN companions are included. Baseline dependency paths/checksums are in manifest.json.\n'
                    'The collection addon is in Interface/AddOns/WoWDanceStudio. Copy Interface/ into your client folder outside the MPQ.\n'
                    'Addon-managed music disables only the added dances native soundtrack events and stops local music on movement.\n'
                    'Native music mode retains M2 sound events and cannot cancel an already playing sound on movement. See audio_mode in manifest.json.\n'
                    'The addon supplies slash aliases for included text emotes. Props and in-game playback verification are not included.\n'
                    'Test fixtures are identified in manifest.json; they do not constitute production review approval.\n')
            (stage / 'INSTALL.txt').write_text(text, encoding='utf-8')
            atomic_json(stage / 'manifest.json', dict(schema=1, dbc_export=plan['dbc_export'], models=[dict(model=r['model'],source=r['folder'],dances=r['manifest']['dances'],test_fixture=r['manifest'].get('acceptance_fixture',False)) for r in plan['models']],
                packaging_mode='changes_only',baseline_dependencies=dependencies,client_compatibility=plan['client_compatibility'],
                audio_mode='addon' if addon_audio else 'native',model_transformations=transformations,
                missing_original_anims=warnings, client_playback_verified=False,
                checksums={str(p.relative_to(stage)):digest(p) for p in stage.rglob('*') if p.is_file()}))
            from .addon import generate
            from .loop_regions import attach
            metadata=read(stage/'manifest.json')
            attach(stage,plan['models'],metadata)
            atomic_json(stage/'manifest.json',metadata)
            generate(stage,'addon' if addon_audio else 'native',include_code=request.get('include_addon_code',True))
            if not request.get('include_addon_code',True):
                with (stage/'INSTALL.txt').open('a',encoding='utf-8') as stream:
                    stream.write('\nThis pack updates Data.lua only. Install the main addon once from the required_runtime folder recorded in manifest.json, then copy this pack Interface folder over it. Later packs update the catalog; they do not replace the addon code.\n')
                metadata=read(stage/'manifest.json');metadata['checksums']['INSTALL.txt']=digest(stage/'INSTALL.txt')
                atomic_json(stage/'manifest.json',metadata)
            stage.rename(final)
            result=dict(output=str(final), models=len(plan['models']), missing_original_anim_count=sum(len(v) for v in warnings.values()), client_playback_verified=False)
            atomic_json(OUTPUT / 'build_result.json',result)
            return result
        finally:
            if stage.exists(): shutil.rmtree(stage)
