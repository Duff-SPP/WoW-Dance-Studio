"""Blender-only adapters for the locally inspected Elune API."""
import hashlib
import importlib
import json
import uuid
from pathlib import Path
import bpy
from .analysis import inventory,signature
from .catalog import ROOT,digest
from .models import model_files,publish
from .storage import atomic_json

def skeleton(rig):
    data=next(r for r in inventory()['armatures'] if r['name']==rig.name)
    weights={b.name:0.0 for b in rig.data.bones}
    for obj in bpy.data.objects:
        if obj.type!='MESH' or not any(m.type=='ARMATURE' and m.object==rig for m in obj.modifiers): continue
        groups={g.index:g.name for g in obj.vertex_groups}
        for vertex in obj.data.vertices:
            for group in vertex.groups:
                name=groups.get(group.group)
                if name in weights: weights[name]+=group.weight
    for bone in data['bones']: bone['skin_weight']=weights[bone['name']]
    data['signature']=signature(rig)
    return data

def enrich_animation_evidence(record):
    """Read actual Elune track metadata; update inventory only, never scene/rest data.

    The bone_%03d association is the installed builder's verified import contract,
    not an anatomical correspondence or a race-specific bone table.
    """
    if record.get('animation_evidence')==1: return record
    from .models import checked_model
    checked_model(record['id'],bpy.data.filepath)
    rig=bpy.data.objects[record['target']]
    if signature(rig)!=record['signature']: raise ValueError('Cannot enrich a different skeleton')
    factory=importlib.import_module('bl_ext.user_default.elune_m2.m2_import.factory')
    parsed=factory.load_model(record['path'])
    if len(parsed.bones)!=len(rig.data.bones): raise ValueError('Raw/imported bone metadata count differs')
    imported={b['name']:b for b in record['inventory']['bones']}
    for index,bone in enumerate(parsed.bones):
        name='bone_%03d'%index
        if name not in imported: raise ValueError('Elune bone-index naming contract differs')
        cached=imported[name]
        expected='bone_%03d'%bone.parent if bone.parent>=0 else None
        if cached['parent']!=expected: raise ValueError('Raw/imported hierarchy differs: '+name)
        if max(abs(cached['head'][i]-bone.pivot[i]) for i in range(3))>1e-5: raise ValueError('Raw/imported pivot differs: '+name)
        cached['m2_has_animation']=bool(bone.is_animated())
        cached['m2_track_samples']={channel:sum(len(t) for t in track.timelines) if (track:=getattr(bone,channel)) else 0 for channel in ('translation','rotation','scale')}
    record['animation_evidence']=1
    record['animation_evidence_parser_sha256']=digest(factory.__file__)
    publish(record)
    return record

def register(path,baseline=False,source_name='Fortnite_M_Avg_Player_Skeleton'):
    path=Path(path).resolve(); files=model_files(path)
    from .models import asset_provenance
    provenance=asset_provenance(path,files)
    from .models import read_models,checked_model
    for previous in read_models()['models']:
        if previous['path']==str(path) and previous['files']==files and previous.get('registration_schema')==4 and previous['source']['name']==source_name:
            try:
                checked_model(previous['id'])
                if baseline or previous['id']=='human2_male':
                    if Path(bpy.data.filepath).resolve()!=Path(previous['scene']).resolve(): bpy.ops.wm.open_mainfile(filepath=previous['scene'])
                    return previous
                # Reuse inventories only with the same importer implementation.
                module=importlib.import_module('bl_ext.user_default.elune_m2.m2_import.factory')
                current={p.name:digest(p) for p in sorted(Path(module.__file__).parent.glob('*.py'))}
                if previous['importer']==current:
                    if Path(bpy.data.filepath).resolve()!=Path(previous['scene']).resolve(): bpy.ops.wm.open_mainfile(filepath=previous['scene'])
                    return previous
            except (ValueError,OSError): pass
    source=next((o for o in bpy.data.objects if o.type=='ARMATURE' and o.name==source_name),None)
    if source is None: raise ValueError('Prepared scene must contain the registered Fortnite source reference')
    importer={}; sequences=[]; missing=[]
    if baseline:
        target=bpy.data.objects['humanmale2_Armature']; identifier='human2_male'; scene=Path(bpy.data.filepath)
        factory=importlib.import_module('bl_ext.user_default.elune_m2.m2_import.factory')
        parsed=factory.load_model(str(path))
        sequences=[{k:getattr(s,k) for k in ('id','variation_index','duration','flags')} for s in parsed.sequences]
        missing=[str(path.with_name(path.stem+('%04d-%02d.anim'%(s.id,s.variation_index)))) for s in parsed.sequences
                 if not s.flags & (0x20|0x40) and not path.with_name(path.stem+('%04d-%02d.anim'%(s.id,s.variation_index))).is_file()]
    else:
        # Load from the real extension package; do not guess operators.
        factory=importlib.import_module('bl_ext.user_default.elune_m2.m2_import.factory')
        builder=importlib.import_module('bl_ext.user_default.elune_m2.m2_import.builder')
        addon=Path(factory.__file__).parent
        importer={p.name:digest(p) for p in sorted(addon.glob('*.py'))}
        model=factory.load_model(str(path))
        if model.version!=264 or not model.bones or not model.vertices or model.skin is None or not model.skin.triangles:
            raise ValueError('Incomplete or incompatible Wrath model (bones, geometry or SKIN missing)')
        for i,bone in enumerate(model.bones):
            if bone.parent < -1 or bone.parent>=len(model.bones) or bone.parent==i: raise ValueError('Invalid M2 parent index')
            visited={i}; parent=bone.parent
            while parent>=0:
                if parent in visited: raise ValueError('Cyclic M2 bone hierarchy')
                visited.add(parent); parent=model.bones[parent].parent
        sequences=[{k:getattr(s,k) for k in ('id','variation_index','duration','flags')} for s in model.sequences]
        missing=[str(path.with_name(path.stem+('%04d-%02d.anim'%(s.id,s.variation_index)))) for s in model.sequences
                 if not s.flags & (0x20|0x40) and not path.with_name(path.stem+('%04d-%02d.anim'%(s.id,s.variation_index))).is_file()]
        if missing: print('STUDIO: Missing external animation files: '+str(len(missing))+'; recorded in model registration; supplied files stay untouched',flush=True)
        # Keep the canonical source reference; remove prepared target objects only in memory.
        for obj in list(bpy.data.objects):
            if obj!=source: bpy.data.objects.remove(obj,do_unlink=True)
        before=set(bpy.data.objects)
        builder.build(model,import_cameras=False,import_bounds=False,repair_weights=False,normalize_uvs=False)
        targets=[o for o in bpy.data.objects if o not in before and o.type=='ARMATURE']
        if len(targets)!=1: raise ValueError('Elune did not produce one unambiguous target armature')
        target=targets[0]
        slug=''.join(c.lower() if c.isalnum() else '_' for c in path.stem).strip('_')
        identifier=slug+'_'+hashlib.sha256(str(path).casefold().encode()).hexdigest()[:8]
        scene=ROOT/'Output'/'Models'/identifier/(uuid.uuid4().hex[:12]+'.blend'); scene.parent.mkdir(parents=True,exist_ok=True)
        for action in bpy.data.actions: action.use_fake_user=True
        bpy.ops.wm.save_as_mainfile(filepath=str(scene),check_existing=False)
    target_data=skeleton(target); source_data=skeleton(source)
    attachments=[a for a in inventory()['attachments'] if a['parent']==target.name]
    identity=hashlib.sha256(json.dumps(dict(files=files,skeleton=target_data['signature']),sort_keys=True).encode()).hexdigest()
    from .models import read_models
    old=next((m for m in read_models()['models'] if m['id']==identifier),None)
    record=dict(id=identifier,registration_schema=4,name=path.stem if not baseline else 'Human2 Male',path=str(path),files=files,identity=identity,
                scene=str(scene),scene_sha256=digest(scene),target=target.name,signature=target_data['signature'],
                inventory=target_data,attachments=attachments,source=source_data,animations=sequences,
                importer=importer,profile=None,compatibility='Wrath MD20 264',status='Registered' if not missing else 'Registered - Incomplete original animation assets',
                missing_external_animations=missing,prepared_scene_original_actions=len(bpy.data.actions))
    if provenance:
        record['asset_source']=provenance; record['display_name']=provenance['display_name']
    if old and old['identity']==identity and old['scene_sha256']==record['scene_sha256']: record['profile']=old.get('profile')
    publish(record,dict(name=source.name,signature=source_data['signature'],scene=str(scene),bones=len(source.data.bones)))
    return record
