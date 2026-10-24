"""Run with Blender -b <scene>; isolated action output and timing evidence only."""
import cProfile
import json
import os
import pstats
import shutil
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
label=sys.argv[sys.argv.index('--')+1]
if not label.replace('_','').isalnum():raise ValueError('Invalid label')
folder=ROOT/'Output'/'PerformanceConversions'/label
folder.mkdir(parents=True,exist_ok=False)
os.environ['WDS_LIBRARY_ROOT']=str(folder/'Library')
os.environ['WDS_MONTAGE_PREVIEW']='1'
(folder/'Library').mkdir()
shutil.copyfile(ROOT/'Output/Library/emotes.json',folder/'Library/emotes.json')
from studio_core import models,library
model=models.get_model('humanfemale_4a9a8b72')
profile=cProfile.Profile();start=time.perf_counter();profile.enable()
result=library.store('bighugs','CMF',model['profile'])
profile.disable()
elapsed=time.perf_counter()-start
report=ROOT/'Reports'/'BlenderPerformance';report.mkdir(exist_ok=True)
profile.dump_stats(str(report/(label+'.prof')))
with (report/(label+'.txt')).open('w') as stream:
    pstats.Stats(profile,stream=stream).sort_stats('cumtime').print_stats(35)
(report/(label+'.json')).write_text(json.dumps(dict(seconds=elapsed,metadata=result),indent=2),encoding='utf-8')
print('PROFILE_CONVERSION_SECONDS',elapsed,flush=True)
