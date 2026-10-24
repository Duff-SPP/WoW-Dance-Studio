"""Adapter to the installed Fortnite Porting UEFormat importer (verified locally)."""
import math
import sys
from pathlib import Path
import bpy
from .analysis import signature
from .catalog import digest


def prepare(variant, profile):
    from fortnite_porting.ueformat.importer.import_context import UEFormatImport
    from fortnite_porting.ueformat.options import UEModelOptions, UEAnimOptions
    reference=bpy.data.objects[profile['source']]
    if signature(reference)!=profile['source_signature']:
        raise ValueError('Reference source rig no longer matches the checked profile')
    original_actions=list(bpy.data.actions)
    for action in original_actions:
        action.use_fake_user=True
    rig=UEFormatImport(UEModelOptions(reorient_bones=False,import_sockets=True)).import_file(variant['source_skeleton'])
    if not isinstance(rig,bpy.types.Object) or rig.type!='ARMATURE':
        raise ValueError('Source model importer did not return an armature')
    # Verify every bone needed by the existing anatomical mapping, not an
    # invented new mapping or a blind acceptance of a different skeleton.
    for name in profile['mapping']:
        actual,expected=rig.data.bones.get(name),reference.data.bones.get(name)
        if actual is None or expected is None:
            raise ValueError('Imported skeleton is missing mapped bone '+name)
        if (actual.parent.name if actual.parent else None)!=(expected.parent.name if expected.parent else None):
            raise ValueError('Imported skeleton parent mismatch: '+name)
        if max(abs(actual.matrix_local[r][c]-expected.matrix_local[r][c]) for r in range(4) for c in range(4))>1e-5:
            raise ValueError('Imported source rest pose differs from the checked profile: '+name)
    action,dto=UEFormatImport(UEAnimOptions(override_skeleton=rig,import_curves=False)).import_file_with_dto(variant['path'])
    if not isinstance(action,bpy.types.Action) or dto.metadata is None:
        raise ValueError('Animation importer returned no action/timing metadata')
    if int(dto.metadata.additive_anim_type)!=0:
        raise ValueError('Additive animation requires a reference-pose policy; unsupported')
    tracks={t.name.casefold() for t in dto.tracks}
    missing=[name for name in profile['mapping'] if name.casefold() not in tracks]
    if missing:
        raise ValueError('Animation is missing mapped body tracks: '+', '.join(missing))
    fps=dto.metadata.frames_per_second
    if not math.isfinite(fps) or fps<=0:
        raise ValueError('Invalid exported frame rate')
    bpy.context.scene.render.fps=round(fps)
    bpy.context.scene.render.fps_base=round(fps)/fps
    if len(action.slots)!=1:
        raise ValueError('Imported action has no unique object slot')
    rig.animation_data.action_slot=action.slots[0]
    adjusted=dict(profile,source=rig.name,source_signature=signature(rig),action=action.name)
    importer_files={name:digest(module.__file__) for name,module in list(sys.modules.items())
                    if name.startswith('fortnite_porting.ueformat') and getattr(module,'__file__',None)
                    and Path(module.__file__).is_file()}
    return adjusted,dict(source_action=Path(variant['path']).stem,imported_action=action.name,
                         fps=fps,num_frames=dto.metadata.num_frames,tracks=len(dto.tracks),
                         imported_bones=len(rig.data.bones),rest_compatibility='mapped matrices and parents checked',
                         animation_compatibility='all mapped body tracks present; non-additive animation',
                         importer_files=importer_files)
