import json
import hashlib
import bpy


def matrix(value):
    return [list(row) for row in value]


def signature(rig):
    value = [(b.name, b.parent.name if b.parent else None, matrix(b.matrix_local)) for b in rig.data.bones]
    return hashlib.sha256(json.dumps(value).encode()).hexdigest()


def inventory():
    rigs = []
    for obj in bpy.data.objects:
        if obj.type != 'ARMATURE':
            continue
        bones = []
        for index, bone in enumerate(obj.data.bones):
            bones.append(dict(index=index, name=bone.name,
                              parent=bone.parent.name if bone.parent else None,
                              children=[b.name for b in bone.children],
                              head=list(bone.head_local), tail=list(bone.tail_local),
                              length=bone.length, rest=matrix(bone.matrix_local),
                              properties={k: str(bone[k]) for k in bone.keys()},
                              constraints=[dict(type=c.type, target=getattr(getattr(c, 'target', None), 'name', None),
                                                subtarget=getattr(c, 'subtarget', None)) for c in obj.pose.bones[bone.name].constraints]))
        rigs.append(dict(name=obj.name, world=matrix(obj.matrix_world), bones=bones,
                         action=obj.animation_data.action.name if obj.animation_data and obj.animation_data.action else None))
    return dict(scene=bpy.data.filepath, fps=bpy.context.scene.render.fps,
                fps_base=bpy.context.scene.render.fps_base, armatures=rigs,
                actions=[dict(name=a.name, frames=list(a.frame_range), slots=[s.identifier for s in a.slots]) for a in bpy.data.actions],
                attachments=[dict(name=o.name, parent=o.parent.name if o.parent else None,
                                  bone=o.parent_bone, location=list(o.location))
                             for o in bpy.data.objects if 'attach' in o.name])

