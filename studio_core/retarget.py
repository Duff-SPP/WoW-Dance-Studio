import math
from pathlib import Path
import bpy
from mathutils import Matrix
from .analysis import inventory, signature


def convert(profile, output, before, audio_folder=None, include_audio=True, action_name=None, save_scene=True):
    source = bpy.data.objects[profile['source']]
    target = bpy.data.objects[profile['target']]
    if signature(source) != profile['source_signature'] or signature(target) != profile['target_signature']:
        raise ValueError('Skeleton signature differs from profile; regenerate/review mapping.')
    mapping = profile['mapping']
    if not math.isfinite(profile['scale']) or profile['scale'] <= 0:
        raise ValueError('Scale must be finite and positive')
    if not mapping or len(set(mapping.values())) != len(mapping):
        raise ValueError('Empty or duplicate target mapping')
    for s,t in mapping.items():
        if s not in source.pose.bones or t not in target.pose.bones:
            raise ValueError('Missing mapped bone: '+s+' -> '+t)
    if any(p.constraints for p in target.pose.bones):
        raise ValueError('Target has existing pose constraints; resolve before baking.')
    action = bpy.data.actions[profile['action']]
    source.animation_data_create()
    source.animation_data.action = action
    if len(action.slots) != 1:
        raise ValueError('Source action must have one unambiguous slot')
    source.animation_data.action_slot = action.slots[0]
    if source.animation_data.nla_tracks or (target.animation_data and target.animation_data.nla_tracks):
        raise ValueError('NLA tracks require an explicit isolation policy before conversion')
    original_actions = list(bpy.data.actions)
    for a in original_actions:
        a.use_fake_user = True
    target.animation_data_create()
    baked = bpy.data.actions.new(action_name or 'Human2_AutumnTea_Converted')
    baked.use_fake_user = True
    target.animation_data.action = baked
    c = Matrix(profile['coordinate_rotation']).to_quaternion()
    reverse = {t:s for s,t in mapping.items()}
    first, last = action.frame_range
    frames = [float(f) for f in range(math.ceil(first), math.floor(last)+1)]
    if not frames or frames[0] != first:
        frames.insert(0,float(first))
    if frames[-1] != last:
        frames.append(float(last))
    rest = {b.name:b.matrix_local.copy() for b in target.data.bones}
    samples = []
    previous_rotations = {}
    for frame in frames:
        bpy.context.scene.frame_set(math.floor(frame), subframe=frame-math.floor(frame))
        evaluated = source.evaluated_get(bpy.context.evaluated_depsgraph_get())
        poses = {}
        for bone in target.data.bones:
            parent = bone.parent
            natural = poses[parent.name] @ rest[parent.name].inverted() @ rest[bone.name] if parent else rest[bone.name].copy()
            desired = natural.copy()
            s = reverse.get(bone.name)
            if s:
                sp = evaluated.pose.bones[s]
                sr = source.data.bones[s].matrix_local
                rotation = c @ sp.matrix.to_quaternion() @ c.inverted() @ Matrix(profile['rest_corrections'][s]).to_quaternion()
                desired = rotation.to_matrix().to_4x4()
                desired.translation = natural.translation
                if s in ['Root','pelvis']:
                    # Absolute source rest displacement includes root movement once.
                    desired.translation = rest[bone.name].translation + (c @ (sp.matrix.translation-sr.translation))*profile['scale']
            poses[bone.name] = desired
            pb = target.pose.bones[bone.name]
            kwargs = dict(parent_matrix=poses[parent.name], parent_matrix_local=rest[parent.name]) if parent else {}
            pb.matrix_basis = bone.convert_local_to_pose(desired, rest[bone.name], invert=True, **kwargs)
            pb.rotation_mode = 'QUATERNION'
            if not all(math.isfinite(v) for row in pb.matrix_basis for v in row):
                raise ValueError('Invalid transform: '+bone.name)
            if s:
                previous = previous_rotations.get(bone.name)
                if previous is not None and previous.dot(pb.rotation_quaternion) < 0:
                    pb.rotation_quaternion.negate()
                previous_rotations[bone.name] = pb.rotation_quaternion.copy()
                for channel in ['location','rotation_quaternion','scale']:
                    pb.keyframe_insert(channel, frame=frame, group=bone.name)
        if frame in [frames[0], frames[len(frames)//2], frames[-1]]:
            samples.append([list(poses[t].to_quaternion()) for t in reverse])
        if int(frame)%60 == 0:
            print('STUDIO: baked frame',frame,flush=True)
    if samples[0] == samples[1] == samples[2]:
        raise ValueError('Bake has no changing sampled transforms')
    after = inventory()
    before_target = next(r for r in before['armatures'] if r['name'] == target.name)
    after_target = next(r for r in after['armatures'] if r['name'] == target.name)
    if before_target['bones'] != after_target['bones']:
        raise ValueError('Target skeleton changed')
    if any(bpy.data.actions.get(a.name) != a for a in original_actions):
        raise ValueError('Original action missing')
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end = math.floor(first), math.ceil(last)
    scene.frame_set(math.floor(first))
    path = Path(output).resolve()
    if path.exists() or path == Path(bpy.data.filepath).resolve() or path.suffix.lower() != '.blend':
        raise ValueError('Output must be a new .blend file')
    path.parent.mkdir(parents=True, exist_ok=True)
    if not save_scene:
        return dict(status='Converted – Review Needed',action=baked.name,frames=[first,last],
                    fps=scene.render.fps/scene.render.fps_base,mapped_bones=len(mapping),
                    original_actions_preserved=len(original_actions),hierarchy_unchanged=True,
                    changing_sampled_transforms=True,finite_transforms=True,limitations=profile['limitations'])
    from .blender_audio import add_soundtrack
    audio = add_soundtrack(scene, audio_folder or Path(__file__).resolve().parents[1]/'Input'/'Fortnite',
                           action.name, include_audio, path)
    print('STUDIO: audio '+audio['status'], flush=True)
    for warning in audio['warnings']:
        print('STUDIO: audio warning: '+warning, flush=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(path), check_existing=False)
    return dict(status='baked_visual_review_required', output=str(path), action=baked.name,
                frames=[first,last], sampled_frames=len(frames), fps=before['fps']/before['fps_base'],
                original_actions_preserved=len(original_actions), hierarchy_unchanged=True,
                changing_sampled_transforms=True, finite_transforms=True,
                mapped_bones=len(mapping), limitations=profile['limitations'], audio=audio)

