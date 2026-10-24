import json
import sys
from pathlib import Path
import bpy

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studio_core.integrity import action_hash

rows={}
for label in ('before','after','retained'):
    metadata=json.loads((ROOT/'Reports/BlenderPerformance'/(label+'.json')).read_text())['metadata']
    with bpy.data.libraries.load(metadata['action_library'],link=False) as (available,requested):
        requested.actions=[metadata['action']]
    rows[label]=action_hash(requested.actions[0])
    bpy.data.actions.remove(requested.actions[0])
assert len(set(rows.values()))==1,rows
(ROOT/'Reports/BlenderPerformance/action_equivalence.json').write_text(json.dumps(rows,indent=2))
print('All three isolated conversions have identical keyframe and handle hashes',flush=True)
