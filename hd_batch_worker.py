"""Background Blender batch adapter; uses the existing checked library pipeline."""
import json,sys,time,traceback,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import bpy
from studio_core.storage import atomic_json,locked
from studio_core.catalog import LIBRARY
from studio_core.library import store
from studio_core.cache import valid_output

request=json.loads(Path(sys.argv[sys.argv.index('--')+1]).read_text())
with locked(LIBRARY/'conversion.lock'):
    for job in request['jobs']:
        if shutil.disk_usage(LIBRARY).free<20*1024**3:
            raise RuntimeError('HD batch paused: less than 20 GiB free; completed jobs are preserved')
        report=Path(job['report'])
        if report.exists():
            old=json.loads(report.read_text())
            if old.get('ok') and valid_output(old['metadata']):continue
        started=time.time()
        try:
            bpy.ops.wm.open_mainfile(filepath=request['scene'])
            metadata=store(job['emote'],job['variant'],request['profile'],job['cache_request'])
            result=dict(ok=True,metadata=metadata,seconds=time.time()-started)
        except Exception as error:
            result=dict(ok=False,error=str(error),traceback=traceback.format_exc(),seconds=time.time()-started)
        atomic_json(report,result)
        print('HD_BATCH '+json.dumps(dict(target=request['target'],emote=job['emote'],ok=result['ok'],seconds=round(result['seconds'],2),error=result.get('error'))),flush=True)
