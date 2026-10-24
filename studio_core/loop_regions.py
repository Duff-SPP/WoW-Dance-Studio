"""Experimental native loop-region deployment, outside the MPQ."""
import os
import shutil
import struct
from .catalog import ROOT,digest

DLL=ROOT/'Output/Research/ascension-extensions-reconstruction/build-dance-loop-regions/Extensions.dll'


def encode(regions):
    rows={}
    for identifier,duration,start in regions:
        if not 506<=identifier<65536 or not 0<duration<=600000 or not 0<=start<duration:
            raise ValueError('Invalid native loop region')
        if identifier in rows and rows[identifier]!=(duration,start):
            raise ValueError('Conflicting loop timings for the same animation ID across models')
        rows[identifier]=(duration,start)
    return b'WDSLOOP1'+struct.pack('<I',len(rows))+b''.join(struct.pack('<III',identifier,*rows[identifier]) for identifier in sorted(rows))


def attach(stage,models,manifest):
    regions=[(d['animation_id'],d['native_loop_region']['duration_ms'],d['native_loop_region']['start_ms'])
             for model in models for d in model['manifest']['dances'] if d.get('native_loop_region') and d['native_loop_region']['start_ms']]
    if not regions:return
    if os.environ.get('WDS_MONTAGE_PREVIEW')!='1' or not DLL.is_file():
        raise ValueError('Native intro/loop region pack requires the experimental sampler DLL build')
    folder=stage/'ClientRoot';folder.mkdir(exist_ok=True)
    shutil.copyfile(DLL,folder/'Extensions.dll')
    if digest(folder/'Extensions.dll')!=digest(DLL):raise ValueError('Native loop DLL changed during packaging')
    config=folder/'WoWDanceStudio.loops';config.write_bytes(encode(regions))
    manifest['native_loop_regions']=dict(experimental=True,config='ClientRoot/WoWDanceStudio.loops',
        sha256=digest(config),count=len(set(r[0] for r in regions)),runtime_verified=False)
    compatibility=manifest.get('client_compatibility') or {}
    compatibility['required_client_dll']=dict(path=str(DLL),sha256=digest(DLL),reason='Native intro-once and loop-region sampling')
    manifest['client_compatibility']=compatibility
    with (stage/'INSTALL.txt').open('a',encoding='utf-8') as f:
        f.write('\nEXPERIMENTAL NATIVE LOOP REGIONS: with the client closed, back up its existing Extensions.dll and copy BOTH ClientRoot files beside Ascension.exe, outside the MPQ. This DLL and WoWDanceStudio.loops must match this pack. Native section playback is not yet verified in game. Restore both the prior DLL/config and prior MPQ when reverting.\n')
