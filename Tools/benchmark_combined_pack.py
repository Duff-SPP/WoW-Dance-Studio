"""Twenty structural model exports; temporary files never deploy to the game."""
import copy
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import test_pack
from studio_core import pack_manager as packs,client_audio
from studio_core.storage import atomic_json
from studio_core.catalog import digest

test_pack.PackTests.setUpClass()
try:
    with tempfile.TemporaryDirectory(dir=ROOT/'Output/M2',prefix='combined_perf_') as temp, \
         tempfile.TemporaryDirectory(dir=ROOT/'Output/Packs',prefix='.combined_perf_') as output:
        root=Path(temp);out=Path(output)
        original=Path(test_pack.PackTests.scourge[0])
        base=packs.read(original/'manifest.json')
        source=Path(base['dbc_registry_path']).parent/'exports'/base['dbc_export']/'DBFilesClient'
        dbc=root/'DBC/exports'/base['dbc_export']/'DBFilesClient';shutil.copytree(source,dbc)
        marker=packs.read(dbc/'studio_export.json')
        paths=[]
        needed=sum(p.stat().st_size for p in original.rglob('*') if p.is_file())*45
        if shutil.disk_usage(root).free<needed+1024**3:raise RuntimeError('Insufficient free space for isolated benchmark')
        for i in range(20):
            folder=root/str(i)/'export';shutil.copytree(original,folder)
            manifest=copy.deepcopy(base);manifest['model']='audit_model_'+str(i)
            manifest['client_model_path_candidates']=['Character/Audit'+str(i)+'/'+Path(base['client_model_path_candidates'][0].replace('\\','/')).name]
            manifest['dbc_registry_path']=str(root/'DBC/registry.json')
            for dance in manifest['dances']:
                allocation=next(d for d in marker['manifest'] if d['emote']==dance['emote'])
                allocation['models'].append(dict(target=manifest['model'],version=dance['version']))
            atomic_json(folder/'manifest.json',manifest);paths.append(str(folder))
        atomic_json(dbc/'studio_export.json',marker)
        stats=dict(model_count=20,copy_calls=0,copied_bytes=0,copy_seconds=0.,render_calls=0,render_seconds=0.)
        real_copy=shutil.copyfile
        def copy_file(source,destination,*args,**kwargs):
            start=time.perf_counter();result=real_copy(source,destination,*args,**kwargs)
            stats['copy_seconds']+=time.perf_counter()-start;stats['copy_calls']+=1;stats['copied_bytes']+=Path(destination).stat().st_size
            return result
        def render(function):
            def run(*args,**kwargs):
                start=time.perf_counter();result=function(*args,**kwargs)
                stats['render_seconds']+=time.perf_counter()-start;stats['render_calls']+=1
                return result
            return run
        with patch.object(packs,'OUTPUT',out), \
             patch('studio_core.client_compatibility.PROFILE',ROOT/'Output/absent_structural_test_client.json'), \
             patch.object(shutil,'copyfile',side_effect=copy_file), \
             patch.object(client_audio,'render_full',side_effect=render(client_audio.render_full)), \
             patch.object(client_audio,'render_cycle',side_effect=render(client_audio.render_cycle)):
            start=time.perf_counter();result=packs.build(dict(packages=paths))
            stats['build_seconds']=time.perf_counter()-start
            folder=Path(result['output']);manifest=packs.read(folder/'manifest.json')
            start=time.perf_counter()
            assert all(digest(folder/name)==sha for name,sha in manifest['checksums'].items())
            stats['independent_checksum_seconds']=time.perf_counter()-start
            stats['output_bytes']=sum(p.stat().st_size for p in folder.rglob('*') if p.is_file())
        report=ROOT/'Reports/PackPerformance';report.mkdir(exist_ok=True)
        atomic_json(report/'twenty_models.json',stats)
        print(json.dumps(stats,indent=2))
finally:
    test_pack.PackTests.doClassCleanups()
