"""Verify original model data and animation keyframes around each library bake."""
import hashlib
from array import array
import math
import bpy
from .analysis import signature


def action_hash(action):
    h=hashlib.sha256()
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    h.update(f'{curve.data_path}:{curve.array_index}'.encode())
                    for prop in ['co','handle_left','handle_right']:
                        values=array('f',[0])*(len(curve.keyframe_points)*2)
                        curve.keyframe_points.foreach_get(prop,values); h.update(values.tobytes())
    return h.hexdigest()


def snapshot(target):
    meshes={}
    for mesh in bpy.data.meshes:
        h=hashlib.sha256()
        values=array('f',[0])*(len(mesh.vertices)*3); mesh.vertices.foreach_get('co',values); h.update(values.tobytes())
        values=array('i',[0])*len(mesh.loops); mesh.loops.foreach_get('vertex_index',values); h.update(values.tobytes())
        meshes[mesh.name]=h.hexdigest()
    attachments={o.name:(o.parent.name if o.parent else None,o.parent_bone,[list(r) for r in o.matrix_basis]) for o in bpy.data.objects if 'attach' in o.name}
    return dict(actions={a.name:action_hash(a) for a in bpy.data.actions},meshes=meshes,attachments=attachments,target=signature(bpy.data.objects[target]))


def verify(before,target,action):
    after=snapshot(target)
    assert before['target']==after['target'],'Target rest/hierarchy changed'
    assert before['attachments']==after['attachments'],'Attachment data changed'
    assert all(after['meshes'].get(n)==v for n,v in before['meshes'].items()),'Original geometry changed'
    assert all(after['actions'].get(n)==v for n,v in before['actions'].items()),'Original animations changed'
    changing=0
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    values=[p.co.y for p in curve.keyframe_points]
                    assert all(math.isfinite(v) for v in values),'Nonfinite animation key'
                    if values and max(values)-min(values)>1e-5: changing+=1
    assert changing>0 and len(action.slots)==1,'No changing tracks or unique action slot'
    return dict(original_actions_verified=len(before['actions']),geometry_preserved=True,attachments_preserved=True,
                rest_hierarchy_preserved=True,changing_curves=changing)
