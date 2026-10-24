import json
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from studio_core import client_audio
from studio_core.catalog import read_catalog

assets=[];seen=set()
for emote in read_catalog()['emotes']:
    for row in emote['audio'].values():
        if row['path'] not in seen:
            seen.add(row['path']);assets.append(dict(source=row['path'],sha256=row['sha256']))
assets=assets[:20]
rows=[]
with tempfile.TemporaryDirectory(dir=ROOT/'Reports',prefix='audio_perf_') as folder:
    folder=Path(folder)
    for i,asset in enumerate(assets):
        start=time.perf_counter()
        with patch.object(client_audio,'resample',side_effect=client_audio.resample_reference):
            before=client_audio.render_full(asset,folder/'before.wav')
        before_seconds=time.perf_counter()-start
        start=time.perf_counter();after=client_audio.render_full(asset,folder/'after.wav');after_seconds=time.perf_counter()-start
        assert before==after,(asset,before,after)
        rows.append(dict(source=asset['source'],before_seconds=before_seconds,after_seconds=after_seconds,sha256=after['sha256']))
        print('Audio',i+1,'/ 20 identical',round(before_seconds,3),'->',round(after_seconds,3),flush=True)
result=dict(tracks=len(rows),before_seconds=sum(r['before_seconds'] for r in rows),after_seconds=sum(r['after_seconds'] for r in rows),rows=rows)
(ROOT/'Reports/PackPerformance/audio_twenty.json').write_text(json.dumps(result,indent=2))
print('TOTAL',result['before_seconds'],result['after_seconds'],flush=True)
