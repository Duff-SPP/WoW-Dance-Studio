"""Bake a verified static montage route from existing full-pose source clips."""
import math
import bpy
from .catalog import digest
from .import_emote import prepare
from .montage import sample_time


def prepare_montage(asset,profile):
    plan=asset['montage']
    if plan['routing_notifies']:raise ValueError('Dynamic routing cannot be baked as a static route')
    if len(plan['slots'])!=1:raise ValueError('Unresolved montage layers')
    prepared={};importers={}
    for source,row in plan['assets'].items():
        clip=row['asset']
        if digest(clip['path'])!=clip['sha256']:raise ValueError('Montage clip changed')
        adjusted,metadata=prepare(clip,profile)
        prepared[source]=(adjusted,metadata)
        importers.update(metadata['importer_files'])
    adjusted,metadata=next(iter(prepared.values()))
    rig=bpy.data.objects[adjusted['source']]
    spans=[plan['sections'][name]['end']-plan['sections'][name]['start'] for name in plan['route']]
    duration=sum(spans)/plan['montage_rate']
    count=max(2,round(duration*30))
    fps=count/duration
    if not 2<=count<=18000:raise ValueError('Montage bake outside frame bounds')
    loop_start=sum(spans[:plan['loop_from']])/plan['montage_rate'] if plan['loop_from'] is not None else None
    baked=bpy.data.actions.new('Montage_Composed_Source')
    # Sample the original actions first; never key into an imported action.
    samples=[]
    for frame in range(count):
        clock=sample_time(plan,frame/fps,repeat=False)
        if clock is None or len(clock['samples'])!=1:raise ValueError('Montage sample lacks a unique source pose')
        sample=clock['samples'][0];source_profile,source_metadata=prepared[sample['source']]
        source_rig=bpy.data.objects[source_profile['source']]
        action=bpy.data.actions[source_profile['action']]
        source_rig.animation_data.action=action;source_rig.animation_data.action_slot=action.slots[0]
        first,last=action.frame_range
        position=min(last,max(first,first+sample['seconds']*source_metadata['fps']))
        bpy.context.scene.frame_set(math.floor(position),subframe=position%1)
        evaluated=source_rig.evaluated_get(bpy.context.evaluated_depsgraph_get())
        samples.append({b.name:b.matrix_basis.copy() for b in evaluated.pose.bones})
    rig.animation_data.action=baked
    # keyframe_insert creates the unique object slot for this new source action.
    previous={}
    for frame,pose in enumerate(samples):
        for bone in rig.pose.bones:
            bone.rotation_mode='QUATERNION';bone.matrix_basis=pose[bone.name]
            if bone.name in previous and previous[bone.name].dot(bone.rotation_quaternion)<0:
                bone.rotation_quaternion.negate()
            previous[bone.name]=bone.rotation_quaternion.copy()
            bone.keyframe_insert('location',frame=frame,group=bone.name)
            bone.keyframe_insert('rotation_quaternion',frame=frame,group=bone.name)
            bone.keyframe_insert('scale',frame=frame,group=bone.name)
    if len(baked.slots)!=1:raise ValueError('Composed source has no unique slot')
    rig.animation_data.action_slot=baked.slots[0]
    for layer in baked.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    for key in curve.keyframe_points:key.interpolation='LINEAR'
    bpy.context.scene.render.fps=round(fps);bpy.context.scene.render.fps_base=round(fps)/fps
    metadata=dict(metadata,fps=fps,num_frames=count,source_action='Verified montage route',
                  imported_action=baked.name,importer_files=importers,
                  montage=dict(route=plan['route'],duration_seconds=duration,loop_start_ms=round(loop_start*1000) if loop_start is not None else None,
                               source_count=len(prepared),baked_corrective=plan.get('baked_corrective',False)))
    return dict(adjusted,action=baked.name),metadata
