"""Measure baked target behavior without claiming visual approval."""
import math
import bpy

def diagnose(profile,action):
    rig=bpy.data.objects[profile['target']]; mapping=profile['mapping']
    first,last=action.frame_range; scene=bpy.context.scene; current=scene.frame_current
    maximum_stretch=1.; maximum_location=0.; positions={}; errors=[]
    chains=[(part+'_'+side,child+'_'+side) for side in ('l','r') for part,child in
            [('upperarm','lowerarm'),('lowerarm','hand'),('thigh','calf'),('calf','foot'),('foot','ball')]]
    for i in range(9):
        f=first+(last-first)*i/8; scene.frame_set(math.floor(f),subframe=f%1)
        evaluated=rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
        for source,name in mapping.items():
            pose=evaluated.pose.bones[name]
            if any(not math.isfinite(v) for row in pose.matrix for v in row): errors.append('Nonfinite baked pose '+source)
            positions.setdefault(source,[]).append(pose.matrix.translation.copy())
            if source not in {'Root','pelvis'}: maximum_location=max(maximum_location,rig.pose.bones[name].location.length)
        for a,b in chains:
            if a not in mapping or b not in mapping: continue
            rest=(rig.data.bones[mapping[a]].head_local-rig.data.bones[mapping[b]].head_local).length
            actual=(evaluated.pose.bones[mapping[a]].matrix.translation-evaluated.pose.bones[mapping[b]].matrix.translation).length
            if rest>1e-7: maximum_stretch=max(maximum_stretch,actual/rest,rest/max(actual,1e-8))
    scene.frame_set(current)
    height=profile.get('calibration',{}).get('target_hip_height',1.)
    root_positions=positions.get('Root',positions.get('pelvis',[]))
    root_travel=max(((p-root_positions[0]).length for p in root_positions),default=0.)
    if maximum_stretch>1.5: errors.append('Excessive limb segment stretch')
    if maximum_location>height*.1: errors.append('Excessive non-root joint position drift')
    if root_travel>height*10: errors.append('Extreme root travel')
    result=dict(passed=not errors,errors=errors,sampled_frames=9,max_segment_length_ratio=maximum_stretch,
        max_nonroot_local_displacement=maximum_location,root_travel=root_travel,
        foot_travel={s:max((p-positions[s][0]).length for p in positions[s]) for s in ('foot_l','foot_r') if s in positions},
        note='Foot travel includes intentional dance movement; no automatic contact/visual-quality assertion.')
    if errors: raise ValueError('Baked motion validation failed: '+'; '.join(errors))
    return result
