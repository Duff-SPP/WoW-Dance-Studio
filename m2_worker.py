"""Background sampler and independent Elune reopen checks for append-only M2s."""
import argparse,copy,itertools,json,math,shutil,struct,sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector,Quaternion
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from studio_core.m2_binary import Model,export_model,M2Error,verify_preservation
from studio_core.catalog import digest
from studio_core.analysis import signature
from studio_core.integrity import snapshot,verify
from studio_core.storage import atomic_json
from studio_core.dbc_manager import hashed


def run(plan,stage):
    if any(digest(ROOT/name)!=sha for name,sha in plan['implementation'].items()): raise M2Error('Exporter implementation changed after preview')
    model=plan['model']; source=Path(model['path']); original=source.read_bytes(); native=Model(original)
    if digest(source)!=plan['source_sha256']: raise M2Error('Original M2 changed')
    rig=bpy.data.objects[model['target']]
    if signature(rig)!=model['signature']: raise M2Error('Prepared target signature differs')
    before=snapshot(rig.name); bones=[rig.data.bones.get('bone_%03d'%i) for i in range(native.bone_count)]
    if any(b is None for b in bones) or len(rig.data.bones)!=native.bone_count: raise M2Error('Raw M2 indices and Blender bone names differ')
    errors={False:0.,True:0.}
    for i,bone in enumerate(bones):
        pivot=struct.unpack_from('<3f',native.bones,i*88+76)
        if (bone.parent.name if bone.parent else None)!=('bone_%03d'%native.parents[i] if native.parents[i]>=0 else None): raise M2Error('Raw parent differs from prepared target')
        for mirror in errors:
            position=Vector((-pivot[0] if mirror else pivot[0],pivot[1],pivot[2]))
            errors[mirror]=max(errors[mirror],(position-bone.head_local).length)
    mirror=min(errors,key=errors.get)
    if errors[mirror]>2e-5: raise M2Error('Raw pivot coordinates differ from prepared target')
    if any(p.constraints for p in rig.pose.bones) or rig.animation_data and rig.animation_data.nla_tracks: raise M2Error('Unbaked constraints/NLA tracks unsupported')
    # Bounds conservatively enclose every weighted bone's transform of the
    # original vertex AABB, over every sampled frame (not just joint heads).
    vertices=native.array(60,48)
    positions=[struct.unpack_from('<3f',vertices,i) for i in range(0,len(vertices),48)]
    weighted=set()
    for i in range(0,len(vertices),48):
        for weight,index in zip(vertices[i+12:i+16],vertices[i+16:i+20]):
            if weight:
                if index>=len(bones): raise M2Error('Invalid vertex bone index')
                weighted.add(index)
    lo=[min(p[i] for p in positions) for i in range(3)]; hi=[max(p[i] for p in positions) for i in range(3)]
    corners=[Vector((-x if mirror else x,y,z)) for x,y,z in itertools.product((lo[0],hi[0]),(lo[1],hi[1]),(lo[2],hi[2]))]
    clips=[]; validation=[]
    for dance in plan['dances']:
        metadata=dance['metadata']; library=Path(metadata['action_library'])
        if digest(library)!=metadata['action_library_sha256'] or digest(library.parent/'metadata.json')!=dance['metadata_sha256']: raise M2Error('Stored action changed')
        with bpy.data.libraries.load(str(library),link=False) as (available,requested): requested.actions=[metadata['action']]
        action=requested.actions[0]
        if not action or len(action.slots)!=1: raise M2Error('Missing action slot')
        for pose in rig.pose.bones: pose.matrix_basis.identity(); pose.rotation_mode='QUATERNION'
        rig.animation_data_create(); rig.animation_data.action=action; rig.animation_data.action_slot=action.slots[0]
        first,last=action.frame_range; fps=metadata['validation']['fps']
        if not math.isfinite(fps) or fps<=0 or last<=first or last-first>36000 or (last-first)/fps>600: raise M2Error('Invalid/unsupported sampling range (maximum ten minutes / 36,000 frames)')
        frames=[first]+[float(i) for i in range(math.floor(first)+1,math.ceil(last)) if first<i<last]+[last]
        region=dance.get('native_loop_region')
        if region and region['start_ms']:
            loop_frame=first+region['start_ms']/1000*fps
            if not first<loop_frame<last:raise M2Error('Loop region outside the sampled animation')
            frames=sorted(set(frames+[loop_frame]))
        times=[round((f-first)/fps*1000) for f in frames]
        values=[[[],[],[]] for _ in bones]; expected=[]
        sampled={round(i*(len(frames)-1)/8) for i in range(9)}
        minimum=Vector((float('inf'),)*3); maximum=Vector((-float('inf'),)*3)
        rests=[b.matrix_local.to_quaternion().normalized() for b in bones]
        inverse_rests=[b.matrix_local.inverted() for b in bones]
        previous={}
        for frame_index,frame in enumerate(frames):
            bpy.context.scene.frame_set(math.floor(frame),subframe=frame%1)
            evaluated=rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
            for i,bone in enumerate(bones):
                loc,rot,scale=evaluated.pose.bones[bone.name].matrix_basis.decompose(); rest=rests[i]
                loc=rest@loc; rot=(rest@rot@rest.inverted()).normalized()
                loc=(-loc.x if mirror else loc.x,loc.y,loc.z)
                q=(rot.x,-rot.y if mirror else rot.y,-rot.z if mirror else rot.z,rot.w)
                if i in previous and sum(a*b for a,b in zip(previous[i],q))<0: q=tuple(-v for v in q)
                previous[i]=q
                for channel,value in enumerate((loc,q,tuple(scale))):
                    keys=values[i][channel]; value=list(value)
                    if not keys: keys.append(value)
                    elif len(keys)==1 and max(abs(a-b) for a,b in zip(value,keys[0]))<1e-7: pass
                    elif len(keys)==1: keys[:]=[keys[0]]*frame_index+[value]
                    else: keys.append(value)
            skins=[evaluated.pose.bones[bones[i].name].matrix@inverse_rests[i] for i in range(len(bones))]
            for i in weighted:
                for corner in corners:
                    point=skins[i]@corner; point=Vector((-point.x if mirror else point.x,point.y,point.z))
                    for k in range(3): minimum[k]=min(minimum[k],point[k]); maximum[k]=max(maximum[k],point[k])
            if frame_index in sampled: expected.append(dict(index=frame_index,skin=[[list(row) for row in skin] for skin in skins]))
            if frame_index%60==0: print('STUDIO: sampling '+dance['emote']+' '+str(frame_index)+'/'+str(len(frames)),flush=True)
        for channels in values:
            for i,keys in enumerate(channels):
                if all(max(abs(a-b) for a,b in zip(key,keys[0]))<1e-7 for key in keys): channels[i]=[keys[0]]
        from studio_core.client_audio import duration_ms
        duration=duration_ms(metadata)
        closure=None
        if duration>times[-1]:
            # The source stores N samples at [0,N-1]; its cycle is N/fps.
            # Retain every baked sample and use the final interval to return
            # to the first pose. Original action libraries remain untouched.
            closing_index=times.index(region['start_ms']) if region and region['start_ms'] else 0
            closure=dict(interval_ms=duration-times[-1],max_translation_delta=max(
                max(abs(a-b) for a,b in zip(c[0][-1],c[0][closing_index] if len(c[0])>1 else c[0][0])) for c in values))
            for channels in values:
                for channel,keys in enumerate(channels):
                    if len(keys)>1:
                        first_key=list(keys[closing_index])
                        if channel==1 and sum(a*b for a,b in zip(keys[-1],first_key))<0:first_key=[-v for v in first_key]
                        keys.append(first_key)
            times.append(duration)
        radius=max(Vector(point).length for point in itertools.product(*[(minimum[i],maximum[i]) for i in range(3)]))
        clip=dict(animation_id=dance['animation_id'],duration=times[-1],times=times,bones=values,bounds=list(minimum)+list(maximum)+[radius],expected=expected,loop=True,loop_closure=closure)
        if dance.get('client_audio'):
            if dance['client_audio']['duration_ms']!=times[-1]:raise M2Error('Soundtrack cycle differs from animation duration')
            clip['sound_id']=dance['client_audio']['sound_id']
        clips.append(clip); validation.append(verify(before,rig.name,action))
    output,anims,preserved=export_model(original,clips)
    destination=stage/source.name; destination.write_bytes(output)
    for identifier,data in anims.items(): (stage/(source.stem+('%04d-00.anim'%identifier))).write_bytes(data)
    copied=[]
    for name,sha in plan['files'].items():
        path=Path(name)
        if path==source: continue
        if digest(path)!=sha: raise M2Error('Original companion file changed')
        target=stage/path.name
        if target.exists(): raise M2Error('Output companion filename collision')
        shutil.copyfile(path,target)
        if digest(target)!=sha: raise M2Error('Original companion bytes changed during copy')
        copied.append(path.name)
    # Reopen through the independently installed Elune parser. It resolves the
    # new external ANIM files itself; no exporter decoder is used here.
    from bl_ext.user_default.elune_m2.m2_import import factory
    parsed=factory.load_model(str(destination))
    if len(parsed.sequences)!=native.count+len(clips) or len(parsed.bones)!=native.bone_count: raise M2Error('Independent reader rejected new tables')
    # Original global accessory tracks must keep running, rather than being
    # overwritten by identity keys from a body-only baked action. Their raw
    # headers/data are preserved. Body pose comparisons exclude their subtrees.
    global_bones={i for i,b in enumerate(parsed.bones) if any(t and t.global_sequence>=0 and any(t.timelines) for t in (b.translation,b.rotation,b.scale))}
    excluded=set(global_bones)
    for i in range(len(bones)):
        parent=native.parents[i]
        while parent>=0:
            if parent in global_bones: excluded.add(i); break
            parent=native.parents[parent]
    comparisons=[]
    for extra,clip in enumerate(clips):
        index=native.count+extra; seq=parsed.sequences[index]
        if seq.id!=clip['animation_id'] or seq.flags&0x130 or seq.flags&0x40 or seq.duration!=clip['duration']: raise M2Error('Wrong exported external sequence')
        maximum_error=0.
        profile=json.loads(Path(plan['dances'][extra]['metadata']['profile_path']).read_text())
        if any(bones[i].name in profile['mapping'].values() for i in excluded): raise M2Error('Original global tracks affect a mapped body role; needs dedicated export policy')
        key_error=0.
        for i,raw in enumerate(parsed.bones):
            for channel,track in enumerate((raw.translation,raw.rotation,raw.scale)):
                if track and track.global_sequence>=0: continue
                timeline=track.timelines[index] if track and index<len(track.timelines) else []
                expected_keys=clip['bones'][i][channel]
                expected_times=[0] if len(expected_keys)==1 else clip['times']
                if [t for t,_ in timeline]!=expected_times: raise M2Error('Independent reader found wrong external timestamps')
                key_error=max(key_error,max(abs(a-b) for (_,value),expected in zip(timeline,expected_keys) for a,b in zip(value,expected)))
        if key_error>0.0001: raise M2Error('Independent external key values differ: '+str(key_error))
        for sample in clip['expected']:
            timestamp=clip['times'][sample['index']]; final_matrices={}
            def final(bi):
                if bi in final_matrices: return final_matrices[bi]
                raw=parsed.bones[bi]; decoded=[]
                for track,default in ((raw.translation,(0.,0.,0.)),(raw.rotation,(0.,0.,0.,1.)),(raw.scale,(1.,1.,1.))):
                    timeline=track.timelines[index] if track and index<len(track.timelines) else []
                    value=next((v for t,v in timeline if t==timestamp),timeline[0][1] if len(timeline)==1 else default)
                    decoded.append(value)
                loc,q,scale=decoded; rest=rests[bi]
                loc=rest.inverted()@Vector((-loc[0] if mirror else loc[0],loc[1],loc[2]))
                q=rest.inverted()@Quaternion((q[3],q[0],-q[1] if mirror else q[1],-q[2] if mirror else q[2]))@rest; q.normalize()
                basis=Matrix.LocRotScale(loc,q,Vector(scale)); parent=native.parents[bi]
                matrix=(final(parent)@bones[parent].matrix_local.inverted()@bones[bi].matrix_local@basis) if parent>=0 else bones[bi].matrix_local@basis
                final_matrices[bi]=matrix; return matrix
            for i in range(len(bones)):
                if i in excluded: continue
                skin=final(i)@inverse_rests[i]; expected=sample['skin'][i]
                maximum_error=max(maximum_error,max(abs(skin[r][c]-expected[r][c]) for r in range(4) for c in range(4)))
        if maximum_error>0.003: raise M2Error('Independent replay differs from Blender motion: '+str(maximum_error))
        comparisons.append(dict(animation_id=clip['animation_id'],sampled_poses=len(clip['expected']),max_skin_matrix_error=maximum_error,duration_ms=seq.duration,
            max_external_key_error=key_error,compared_skin_bones=len(bones)-len(excluded),preserved_global_accessory_subtrees=sorted(excluded)))
    verify_preservation(original,destination.read_bytes())
    atomic_json(stage/'manifest.json',dict(model=model['id'],implementation=plan['implementation'],dbc_export=plan['dbc_export'],dbc_registry_path=plan['dbc_registry_path'],dbc_checksums=plan['dbc_checksums'],
        dances=[dict(emote=d['emote'],animation_id=d['animation_id'],emote_id=d['emote_id'],version=d['metadata']['version'],variant=d['metadata']['variant'],
                       sound_ids=d['sound_ids'],audio_assets=d['audio_assets'],client_audio=d.get('client_audio'),full_soundtrack=d.get('full_soundtrack',{}),native_loop=True,native_loop_region=d.get('native_loop_region'),loop_closure=clips[i].get('loop_closure'),prop_status=d['metadata'].get('prop_status'),profile_sha256=d['metadata']['profile_sha256']) for i,d in enumerate(plan['dances'])],
        output_checksums={p.name:digest(p) for p in stage.iterdir() if p.is_file()},preservation=preserved,blender_originals=validation,
        independent_reader='Installed Elune Wrath parser; external key decoding plus hierarchical skin-matrix replay',motion=comparisons,
        client_model_path_candidates=plan['client_model_path_candidates'],input_checksums=plan['files'],missing_original_anims=plan['missing_original_anims'],missing_original_skins=plan.get('missing_original_skins',[]),copied_companions=copied,
        acceptance_fixture=plan['request'].get('acceptance_fixture',False),client_playback_verified=False,packaging_and_triggers_implemented=False,status='Structurally validated; test against client archives, especially missing original ANIMs.'))


if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--plan',required=True); parser.add_argument('--stage',required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:]); path=Path(args.plan).resolve(); stage=Path(args.stage).resolve()
    if not path.is_relative_to(ROOT/'Output') or not stage.is_relative_to(ROOT/'Output'/'M2') or not stage.name.startswith('.stage_'): raise M2Error('Invalid worker paths')
    stored=json.loads(path.read_text()); plan=stored['plan']
    if hashed(plan)!=stored['sha256']: raise M2Error('Plan hash differs')
    run(plan,stage)
    print('STUDIO: M2/ANIM package and independent replay verified',flush=True)
