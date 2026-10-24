"""Immutable profile revisions, calibration, technical checks and explicit approval."""
import json
import math
import uuid
from datetime import datetime,timezone
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
from .analysis import signature,matrix
from .anatomy import infer,GENERATOR,ESSENTIAL
from .models import checked_model,publish,profile_content_hash
from .catalog import ROOT
from .storage import atomic_json

def frame(rig,mapping,source=False):
    def at(role): return rig.data.bones[role if source else mapping[role]].head_local
    left=(at('hand_l')-at('hand_r')).normalized()
    up=(at('head')-at('pelvis')).normalized()
    left=(left-up*left.dot(up)).normalized()
    forward=left.cross(up).normalized()
    if min(left.length,up.length,forward.length)<.9: raise ValueError('Degenerate anatomical coordinate frame')
    return Matrix((left,forward,up)).transposed()

def calibrate(profile):
    source=bpy.data.objects[profile['source']]; target=bpy.data.objects[profile['target']]; mapping=profile['mapping']
    needed={'hand_l','hand_r','head','pelvis'}
    if not needed.issubset(mapping):
        profile.update(coordinate_rotation=matrix(Matrix.Identity(4)),scale=1.,rest_corrections={})
        return
    c=(frame(target,mapping) @ frame(source,mapping,True).inverted()).to_4x4()
    source_height=(source.data.bones['pelvis'].head_local-source.data.bones['Root'].head_local).length
    target_height=(target.data.bones[mapping['pelvis']].head_local-target.data.bones[mapping['Root']].head_local).length if 'Root' in mapping else target.data.bones[mapping['pelvis']].head_local.z-min(b.head_local.z for b in target.data.bones)
    profile.update(coordinate_rotation=matrix(c),scale=target_height/source_height,
                   root_motion='scaled_root_and_pelvis_rest_displacement' if 'Root' in mapping else 'scaled_pelvis_world_displacement_once',
                   rest_corrections={s:matrix(c @ source.data.bones[s].matrix_local.to_quaternion().inverted().to_matrix().to_4x4() @ c.inverted() @ target.data.bones[t].matrix_local.to_quaternion().to_matrix().to_4x4()) for s,t in mapping.items()})
    profile['calibration']=dict(method='bilateral hands and pelvis/head orthonormal bases; pelvis/root length ratio',
        source_hip_height=source_height,target_hip_height=target_height,
        limb_lengths={s:(target.data.bones[mapping[s]].head_local-target.data.bones[mapping[p]].head_local).length
                     for s,p in [('lowerarm_l','upperarm_l'),('lowerarm_r','upperarm_r'),('calf_l','thigh_l'),('calf_r','thigh_r')]
                     if s in mapping and p in mapping})

def validate(profile):
    errors=[]; warnings=[]; diagnostics={}
    source=bpy.data.objects.get(profile['source']); target=bpy.data.objects.get(profile['target'])
    mapping=profile['mapping']
    if source is None or target is None: errors.append('Missing source or target rig')
    elif signature(source)!=profile['source_signature'] or signature(target)!=profile['target_signature']: errors.append('Skeleton identity mismatch')
    unsupported={row['source'] for row in profile['evidence'] if row['confidence']=='Unsupported'}
    if unsupported-{'Root','Spine_03','neck_01','neck_02','ball_l','ball_r'}:
        errors.append('A critical limb/body role cannot be waived as unsupported')
    missing=[s for s in ESSENTIAL if s not in mapping and s not in unsupported]
    if missing: errors.append('Missing essential mappings: '+', '.join(missing))
    if len(set(mapping.values()))!=len(mapping): errors.append('Duplicate target assignments')
    if any(row['confidence'] in {'Ambiguous','Missing'} for row in profile['evidence'] if row['source'] in ESSENTIAL): errors.append('Unresolved critical evidence')
    if source and target:
        for s,t in mapping.items():
            if s not in source.data.bones or t not in target.data.bones: errors.append('Unknown bone '+s+' -> '+t)
    if not errors:
        def ancestor(child,parent):
            bone=target.data.bones[mapping[child]].parent
            while bone:
                if bone.name==mapping[parent]: return True
                bone=bone.parent
            return False
        chains=[['Root','pelvis','Spine_01','Spine_03','spine_05','neck_01','neck_02','head']]
        for side in ('l','r'):
            chains.extend([['spine_05']+[p+'_'+side for p in ('clavicle','upperarm','lowerarm','hand')],
                           ['pelvis']+[p+'_'+side for p in ('thigh','calf','foot','ball')]])
        for chain in chains:
            chain=[s for s in chain if s in mapping]
            for parent,child in zip(chain,chain[1:]):
                if not ancestor(child,parent): errors.append('Disconnected or reversed chain '+parent+' -> '+child)
        c=Matrix(profile['coordinate_rotation']); scale=profile['scale']
        if not math.isfinite(scale) or not .0001<scale<100: errors.append('Extreme or invalid scale')
        if abs(c.to_3x3().determinant()-1)>1e-4: errors.append('Mirrored/non-orthonormal coordinate correction')
        lateral=frame(target,mapping).col[0]; center=target.data.bones[mapping['pelvis']].head_local
        asymmetry={}
        for part in ('upperarm','hand','thigh','calf','foot'):
            a=target.data.bones[mapping[part+'_l']].head_local-center; b=target.data.bones[mapping[part+'_r']].head_local-center
            if a.dot(lateral)<=0 or b.dot(lateral)>=0: errors.append('Left/right mismatch: '+part)
            asymmetry[part]=abs(a.dot(lateral)+b.dot(lateral))/max(a.length,b.length,1e-8)
        diagnostics['symmetry_relative_error']=asymmetry
        rest_error=0.
        for s,t in mapping.items():
            correction=Matrix(profile['rest_corrections'][s])
            if any(not math.isfinite(v) for row in correction for v in row) or abs(correction.to_3x3().determinant()-1)>1e-4:
                errors.append('Invalid rest correction: '+s); continue
            restored=c @ source.data.bones[s].matrix_local.to_quaternion().to_matrix().to_4x4() @ c.inverted() @ correction
            rest_error=max(rest_error,restored.to_quaternion().rotation_difference(target.data.bones[t].matrix_local.to_quaternion()).angle)
        diagnostics['max_rest_rotation_error_radians']=rest_error
        if rest_error>1e-3: errors.append('Rest alignment residual exceeds tolerance')
        action=source.animation_data.action if source.animation_data else None
        if action:
            first,last=action.frame_range; samples=[]; max_motion=0.; current=bpy.context.scene.frame_current
            for i in range(7):
                f=first+(last-first)*i/6; bpy.context.scene.frame_set(math.floor(f),subframe=f%1)
                evaluated=source.evaluated_get(bpy.context.evaluated_depsgraph_get())
                for s in mapping:
                    pose=evaluated.pose.bones[s].matrix
                    if any(not math.isfinite(v) for row in pose for v in row): errors.append('Nonfinite sampled source pose: '+s)
                for s in ('Root','pelvis'):
                    motion=(evaluated.pose.bones[s].matrix.translation-source.data.bones[s].matrix_local.translation).length*scale
                    max_motion=max(max_motion,motion)
                samples.append(float(f))
            bpy.context.scene.frame_set(current)
            diagnostics.update(sampled_frames=samples,max_root_pelvis_displacement=max_motion)
            if max_motion>profile['calibration']['target_hip_height']*5: errors.append('Unexpected extreme sampled root motion')
        else: warnings.append('No source animation available for representative pose diagnostics')
    warnings.extend(['Technical checks do not establish visual quality.','No foot contact IK; fingers, twist and face follow parents.'])
    if unsupported: warnings.append('Structurally omitted source roles: '+', '.join(sorted(unsupported)))
    result=dict(passed=not errors,errors=errors,warnings=warnings,diagnostics=diagnostics)
    profile['validation']=result; profile['status']='Validated Technically' if not errors else 'Validation Failed'
    profile['visual_quality']='unverified'
    return result

def revise(model_id,operation='generate',previous=None,overrides=None):
    model=checked_model(model_id,bpy.data.filepath)
    old=json.loads(Path(previous).read_text(encoding='utf-8')) if previous else None
    if old and old.get('model_id')!=model_id: raise ValueError('Profile belongs to another target model')
    manual=dict(old.get('manual_corrections',{})) if old else {}
    for role,value in (overrides or {}).items():
        if value is None: manual.pop(role,None)
        else: manual[role]=value
    mapping,evidence=infer(model['inventory'],model['attachments'],manual)
    if not model.get('animation_evidence') and any(row['source'] in {'ball_l','ball_r'} and row['confidence']=='Missing' for row in evidence):
        from .model_worker import enrich_animation_evidence
        model=enrich_animation_evidence(model)
        mapping,evidence=infer(model['inventory'],model['attachments'],manual)
    source=bpy.data.objects[model['source']['name']]; target=bpy.data.objects[model['target']]
    profile=dict(version=4,generator=GENERATOR,model_id=model_id,model_identity=model['identity'],
        revision=uuid.uuid4().hex[:12],parent_revision=old.get('revision') if old else None,
        source=source.name,target=target.name,source_signature=signature(source),target_signature=signature(target),
        action=source.animation_data.action.name if source.animation_data and source.animation_data.action else '',
        status='Generated – Review Needed',mapping=mapping,evidence=evidence,manual_corrections=manual,
        unmapped_source=[b.name for b in source.data.bones if b.name not in mapping],
        unmapped_target=[b.name for b in target.data.bones if b.name not in mapping.values()],
        limitations=['Body landmarks only; fingers, face, twist and accessories follow parents.','No contact IK or foot locking. Visual review required.'])
    try:
        calibrate(profile)
        if operation in {'validate','approve'}: validate(profile)
    except (ValueError,KeyError,ZeroDivisionError) as error:
        profile.update(status='Validation Failed',validation=dict(passed=False,errors=[str(error)],warnings=[],diagnostics={}))
    if operation=='approve':
        if not old or old.get('status') not in {'Validated Technically','Approved'} or old['mapping']!=mapping or old.get('model_identity')!=model['identity']:
            raise ValueError('Validate and review this revision before manual approval')
        if not profile['validation']['passed']: raise ValueError('Critical validation errors block approval')
        profile.update(status='Approved',approval=dict(manual=True,recorded_at=datetime.now(timezone.utc).isoformat()))
        profile['approval']['content_sha256']=profile_content_hash(profile)
    directory=ROOT/'Profiles'/model_id; directory.mkdir(parents=True,exist_ok=True)
    path=directory/(profile['revision']+'.json'); atomic_json(path,profile)
    model['profile']=str(path)
    if operation=='approve':
        model.setdefault('approved_profiles',{})[profile['source_signature']]=str(path)
    publish(model)
    return dict(profile=str(path),status=profile['status'],mapped=len(mapping),validation=profile.get('validation'))
