"""Blender background entry point; source scenes are never saved."""
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from studio_core.analysis import inventory
from studio_core.profiles import generate_profile
from studio_core.retarget import convert


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['prepare-source','scan', 'profile', 'convert','library-convert','preview','model-register','profile-generate','profile-validate','profile-approve'])
    parser.add_argument('--report', required=True)
    parser.add_argument('--profile')
    parser.add_argument('--output')
    parser.add_argument('--audio-dir')
    parser.add_argument('--include-audio', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--emote')
    parser.add_argument('--variant',default='CMM')
    parser.add_argument('--job-request')
    parser.add_argument('--target',default='human2_male')
    parser.add_argument('--model-file')
    parser.add_argument('--source-rig',default='Fortnite_M_Avg_Player_Skeleton')
    parser.add_argument('--source-skeleton')
    parser.add_argument('--baseline',action='store_true')
    parser.add_argument('--previous-profile')
    parser.add_argument('--overrides')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    report = Path(args.report)
    root = Path(__file__).resolve().parent
    if not report.resolve().is_relative_to(root / 'Reports'):
        raise ValueError('Reports must be inside Reports.')
    if args.profile and not Path(args.profile).resolve().is_relative_to(root / 'Profiles'):
        raise ValueError('Profiles must be inside Profiles.')
    if args.command != 'prepare-source' and args.output and not Path(args.output).resolve().is_relative_to(root / 'Output'):
        raise ValueError('Outputs must be inside Output.')
    if args.command in {'convert','preview'} and (not args.output or Path(args.output).exists()):
        raise ValueError('Choose a new output filename; overwriting is prohibited.')
    report.parent.mkdir(parents=True, exist_ok=True)
    if args.command=='prepare-source':
        if not args.output or not args.source_skeleton:
            raise ValueError('Source preparation requires a skeleton and a new output filename')
        from studio_core.source_scene import create_source_scene
        from studio_core.storage import atomic_json
        atomic_json(report,create_source_scene(args.source_skeleton,args.output,args.source_rig))
        return
    if args.command=='model-register':
        from studio_core.model_worker import register
        result=register(args.model_file,args.baseline,args.source_rig)
        report.write_text(json.dumps(result,indent=2),encoding='utf-8'); return
    if args.command.startswith('profile-'):
        from studio_core.profile_manager import revise
        overrides=json.loads(Path(args.overrides).read_text(encoding='utf-8')) if args.overrides else None
        result=revise(args.target,args.command.split('-')[1].replace('generate','generate'),args.previous_profile,overrides)
        report.write_text(json.dumps(result,indent=2),encoding='utf-8'); return
    if args.command in {'library-convert','preview'}:
        from studio_core.library import store, preview
        from studio_core.catalog import record_failure
        try:
            request=json.loads(Path(args.job_request).read_text()) if args.job_request else None
            if args.command=='library-convert':
                from studio_core.storage import locked
                from studio_core.catalog import LIBRARY
                with locked(LIBRARY/'conversion.lock'):
                    result=store(args.emote,args.variant,args.profile,request)
            else: result=preview(args.emote,args.variant,args.output,args.include_audio,args.target)
        except Exception as error:
            record_failure(args.emote,error)
            raise
        report.write_text(json.dumps(result,indent=2),encoding='utf-8')
        return
    before = inventory()
    report.write_text(json.dumps(before, indent=2), encoding='utf-8')
    if args.command == 'scan':
        print('STUDIO: inventory saved', flush=True)
        return
    if args.command == 'profile':
        path = Path(args.profile)
        if path.exists():
            raise ValueError('Profile already exists; use a new filename to preserve manual corrections.')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(generate_profile(before), indent=2), encoding='utf-8')
        print('STUDIO: body profile generated', flush=True)
        return
    profile = json.loads(Path(args.profile).read_text(encoding='utf-8'))
    result = convert(profile, args.output, before, args.audio_dir, args.include_audio)
    report.write_text(json.dumps(result, indent=2), encoding='utf-8')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        if '--report' in sys.argv:
            path = Path(sys.argv[sys.argv.index('--report')+1]).resolve()
            if path.is_relative_to(Path(__file__).resolve().parent/'Reports'):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(dict(status='failed',error=str(error)),indent=2),encoding='utf-8')
        raise
