import math
import bpy
from mathutils import Matrix
from .analysis import matrix, signature


def generate_profile(before):
    source = bpy.data.objects['Fortnite_M_Avg_Player_Skeleton']
    target = bpy.data.objects['humanmale2_Armature']
    pairs = [('Root','000'), ('pelvis','001'), ('Spine_01','003'), ('Spine_03','009'),
             ('spine_05','016'), ('neck_01','023'), ('neck_02','029'), ('head','039'),
             ('clavicle_l','021'), ('upperarm_l','027'), ('lowerarm_l','035'), ('hand_l','041'),
             ('clavicle_r','022'), ('upperarm_r','028'), ('lowerarm_r','036'), ('hand_r','047'),
             ('thigh_l','006'), ('calf_l','013'), ('foot_l','026'), ('ball_l','032'),
             ('thigh_r','005'), ('calf_r','012'), ('foot_r','025'), ('ball_r','031')]
    mapping = {s:'bone_'+t for s,t in pairs}
    # These are assertions against this imported scene, not numeric-name heuristics.
    anchors = {'ElbowLeft':'bone_027', 'ElbowRight':'bone_028',
               'KneeLeft':'bone_013', 'KneeRight':'bone_012',
               'LeftFoot':'bone_026', 'RightFoot':'bone_025',
               'HandLeft':'bone_041', 'HandRight':'bone_047'}
    evidence = []
    for name, ancestor in anchors.items():
        obj = bpy.data.objects.get('humanmale2_attach_'+name)
        if obj is None or obj.parent != target:
            raise ValueError('Missing attachment evidence: '+name)
        bone = target.data.bones.get(obj.parent_bone)
        chain = []
        while bone:
            chain.append(bone.name)
            bone = bone.parent
        if ancestor not in chain:
            raise ValueError('Attachment ancestry mismatch: '+name)
        evidence.append(dict(attachment=obj.name, chain=chain, landmark=ancestor))
    for side, sign in [('l',1), ('r',-1)]:
        for part in ['upperarm','hand','thigh','calf','foot']:
            s = source.data.bones[part+'_'+side]
            t = target.data.bones[mapping[part+'_'+side]]
            if s.head_local.x*sign <= 0 or t.head_local.y*sign <= 0:
                raise ValueError('Rest-pose side mismatch: '+part+side)
    correction = Matrix.Rotation(math.pi/2, 4, 'Z')
    return dict(version=1, source=source.name, target=target.name,
                source_signature=signature(source), target_signature=signature(target),
                action=source.animation_data.action.name,
                status='body_landmarks_checked_visual_review_required',
                mapping=mapping, evidence=evidence,
                coordinate_rotation=matrix(correction),
                scale=target.data.bones['bone_001'].head_local.z/source.data.bones['pelvis'].head_local.z,
                root_motion='scaled_root_and_pelvis_rest_displacement',
                rest_corrections={s:matrix(correction @ source.data.bones[s].matrix_local.to_quaternion().inverted().to_matrix().to_4x4() @ correction.inverted() @ target.data.bones[t].matrix_local.to_quaternion().to_matrix().to_4x4()) for s,t in mapping.items()},
                unmapped_source=[b.name for b in source.data.bones if b.name not in mapping],
                unmapped_target=[b.name for b in target.data.bones if b.name not in mapping.values()],
                limitations=['Fingers, face, twist and accessory bones follow their parents; not retargeted.',
                             'No contact IK or foot locking. Visual quality requires inspection.'],
                manual_corrections=[])

