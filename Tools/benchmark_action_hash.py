import hashlib
import json
import sys
import time
from pathlib import Path
import bpy
import struct
from array import array

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studio_core.integrity import action_hash


def candidate(action):
    h=hashlib.sha256()
    for layer in action.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for curve in bag.fcurves:
                    h.update(f'{curve.data_path}:{curve.array_index}'.encode())
                    if len(curve.keyframe_points)==1:
                        point=curve.keyframe_points[0]
                        h.update(struct.pack('=6f',*point.co,*point.handle_left,*point.handle_right))
                        continue
                    values=array('f',[0])*(len(curve.keyframe_points)*2)
                    for prop in ('co','handle_left','handle_right'):
                        curve.keyframe_points.foreach_get(prop,values)
                        h.update(values)
    return h.hexdigest()


start=time.perf_counter();old={a.name:action_hash(a) for a in bpy.data.actions};old_time=time.perf_counter()-start
start=time.perf_counter();new={a.name:candidate(a) for a in bpy.data.actions};new_time=time.perf_counter()-start
assert old==new
result=dict(original_seconds=old_time,candidate_seconds=new_time,identical_actions=len(old))
print(result,flush=True)
(ROOT/'Reports/BlenderPerformance/hash_comparison.json').write_text(json.dumps(result,indent=2))
