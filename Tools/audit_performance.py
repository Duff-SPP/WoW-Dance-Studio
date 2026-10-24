"""Read-only pipeline workloads; writes measurements under Reports only."""
import argparse
import cProfile
import json
import pstats
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studio_core import batch,cache,models,pack_manager,m2_manager


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--label',required=True)
    parser.add_argument('--target',default='humanfemale_4a9a8b72')
    args=parser.parse_args()
    if not args.label.replace('_','').replace('-','').isalnum(): parser.error('Invalid label')
    folder=ROOT/'Reports'/'PerformanceAudit2';folder.mkdir(exist_ok=True)
    result={}

    def measure(name,operation):
        profiler=cProfile.Profile();start=time.perf_counter();profiler.enable()
        try:
            value=operation()
            result[name]=dict(seconds=round(time.perf_counter()-start,4),status='passed',result=value)
        except Exception as error:
            result[name]=dict(seconds=round(time.perf_counter()-start,4),status='unavailable',error=str(error))
        finally:
            profiler.disable();profiler.dump_stats(str(folder/(args.label+'_'+name+'.prof')))
            with (folder/(args.label+'_'+name+'.txt')).open('w') as stream:
                pstats.Stats(profiler,stream=stream).sort_stats('cumtime').print_stats(18)
        print(name, result[name]['seconds'],result[name]['status'],flush=True)

    def check_cache(sectioned):
        with models.validation_session(),batch.montage_mode(sectioned):
            model=models.get_model(args.target)
            from studio_core.runtime import defaults
            context=cache.Context(defaults()['blender'],model['scene'])
            return cache.inspect_cache(context,model['profile'],args.target,'AUTO')

    measure('ordinary_cache',lambda:check_cache(False))
    measure('section_cache',lambda:check_cache(True))
    manifests=sorted((ROOT/'Output/M2'/args.target).glob('*/manifest.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    if manifests:
        measure('pack_inspection',lambda:pack_manager.inspect([str(manifests[0].parent)]))
    plans=sorted((ROOT/'Output/M2/plans').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    if plans:
        request=json.loads(plans[0].read_text())['plan']['request']
        def plan():
            with batch.montage_mode(True): return m2_manager.build_plan(request)
        measure('model_plan',plan)
    (folder/(args.label+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')


if __name__=='__main__':main()
