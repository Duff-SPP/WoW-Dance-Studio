"""Bootstrap a local source reference without shipping or overwriting assets."""
import json
import os
from pathlib import Path
import subprocess
import uuid
from .catalog import ROOT, digest
from .fortnite_paths import asset_roots
from .storage import atomic_json, locked


def managed_scene(path):
    path = Path(path).resolve()
    if path.suffix.casefold() != '.blend':
        raise ValueError('Prepared source scene must use the .blend extension')
    if not any(path.is_relative_to((ROOT/folder).resolve()) for folder in ('Blender','Output')):
        raise ValueError('New source scenes must be inside this Studio folder\'s Blender or Output directory')
    return path


def choose_source(folder, explicit=None):
    if explicit:
        path = Path(explicit).resolve()
        if path.suffix.casefold() != '.uemodel' or not path.is_file():
            raise ValueError('Choose an existing exported source skeleton .uemodel')
        return path
    candidates = {}
    for root in asset_roots(folder):
        if not root.is_dir():
            continue
        for path in sorted(root.rglob('*')):
            if path.is_file() and path.suffix.casefold() == '.uemodel' and 'skeleton' in path.stem.casefold():
                candidates.setdefault(digest(path),path.resolve())
    if len(candidates) > 1:
        raise ValueError('Multiple different source skeletons found. Use Prepare Source in Studio to select the matching .uemodel, or pass --source-skeleton.')
    return next(iter(candidates.values()),None)


def ensure_source_scene(blender, scene, emotes, source_name='Fortnite_M_Avg_Player_Skeleton',
                        source_skeleton=None, if_available=False, emit=print):
    scene = Path(scene).resolve()
    if scene.is_file():
        emit('STUDIO: Reusing existing source scene; its contents are unchanged: '+str(scene))
        return dict(scene=str(scene),created=False)
    scene = managed_scene(scene)
    source = choose_source(emotes,source_skeleton)
    if source is None:
        if if_available:
            emit('STUDIO: No exported source skeleton yet. Register Folder will prepare the reference after you supply the Fortnite exports.')
            return dict(scene=str(scene),created=False,pending=True)
        raise ValueError('No exported source skeleton found. Download/import Fortnite files first, or use Prepare Source to choose a .uemodel.')
    scene.parent.mkdir(parents=True,exist_ok=True)
    reports = ROOT/'Reports'
    reports.mkdir(exist_ok=True)
    with locked(scene.with_suffix('.prepare.lock'),timeout=3):
        if scene.is_file():
            return dict(scene=str(scene),created=False)
        report = reports/('prepare_source_'+uuid.uuid4().hex+'.json')
        log = report.with_suffix('.log')
        command = [str(blender),'-b','--python-exit-code','1','--python',str(ROOT/'blender_worker.py'),
                   '--','prepare-source','--report',str(report),'--output',str(scene),
                   '--source-skeleton',str(source),'--source-rig',source_name]
        emit('STUDIO: Creating the source reference automatically from '+source.name)
        with log.open('w',encoding='utf-8') as stream:
            result = subprocess.run(command,stdout=stream,stderr=subprocess.STDOUT,
                                    creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        if result.returncode:
            raise RuntimeError('Source preparation failed; existing files were preserved. See '+str(log))
        payload = json.loads(report.read_text(encoding='utf-8'))
        if payload.get('scene') != str(scene) or not scene.is_file() or digest(scene) != payload.get('scene_sha256'):
            raise ValueError('Prepared source scene did not pass its output integrity check')
        emit('STUDIO: Source reference ready: '+str(scene))
        return payload


def create_source_scene(source, output, source_name):
    """Blender-only worker. Preserve imported bones/rest matrices and input files."""
    import bpy
    from fortnite_porting.ueformat.importer.import_context import UEFormatImport
    from fortnite_porting.ueformat.options import UEModelOptions
    from .analysis import signature

    output = managed_scene(output)
    if output.exists():
        raise ValueError('Source scene already exists; choose a new filename')
    source = choose_source(ROOT/'Input/Fortnite',source)
    if source is None:
        raise ValueError('Missing exported source skeleton')
    before = digest(source)
    # Clear the startup scene only in this background process; no startup file is saved.
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj,do_unlink=True)
    rig = UEFormatImport(UEModelOptions(reorient_bones=False,import_sockets=True)).import_file(str(source))
    if not isinstance(rig,bpy.types.Object) or rig.type != 'ARMATURE' or not rig.data.bones:
        raise ValueError('Source importer did not return a nonempty armature')
    if not source_name:
        raise ValueError('Source armature name is empty')
    rig.name = source_name
    if rig.name != source_name:
        raise ValueError('Blender could not retain the requested source object name')
    payload = dict(scene=str(output),created=True,source=str(source),source_sha256=before,
                   source_rig=rig.name,source_signature=signature(rig),bones=len(rig.data.bones))
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary = output.with_name('.'+output.stem+'_'+uuid.uuid4().hex+'.blend')
    try:
        bpy.ops.wm.save_as_mainfile(filepath=str(temporary),check_existing=False)
        if digest(source) != before:
            raise ValueError('Source skeleton changed during preparation')
        # Windows rename refuses existing destinations; POSIX needs a no-replace link.
        if os.name == 'nt':
            os.rename(temporary,output)
        else:
            os.link(temporary,output)
    finally:
        temporary.unlink(missing_ok=True)
    payload['scene_sha256'] = digest(output)
    atomic_json(output.with_suffix('.source.json'),payload)
    return payload
