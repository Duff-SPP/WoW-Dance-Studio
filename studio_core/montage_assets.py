"""Resolve saved montage slots to exact, full-pose UEANIM exports."""
import copy
import io
import struct
from pathlib import Path
from .catalog import digest


def animation_metadata(path):
    import zstandard
    from Tools.FortniteBatch.verify import read_exact,read_string
    with Path(path).open('rb') as f:
        if read_exact(f,8)!=b'UEFORMAT' or read_string(f)!='UEANIM' or read_exact(f,1)!=b'\x0a':
            raise ValueError('Montage requires UEANIM v10')
        read_string(f);source=read_string(f)
        if read_exact(f,1)!=b'\x01' or read_string(f)!='ZSTD':raise ValueError('Unexpected UEANIM compression')
        size,packed=struct.unpack('<ii',read_exact(f,8))
        if not 0<size<=256*1024*1024 or not 0<packed<=64*1024*1024:raise ValueError('UEANIM exceeds inspection bounds')
        payload=zstandard.ZstdDecompressor().decompress(read_exact(f,packed),max_output_size=size)
        if len(payload)!=size:raise ValueError('Truncated UEANIM payload')
    stream=io.BytesIO(payload);count=struct.unpack('<i',read_exact(stream,4))[0]
    if not 0<count<=64:raise ValueError('Invalid animation attributes')
    for _ in range(count):
        name=read_string(stream);length=struct.unpack('<i',read_exact(stream,4))[0]
        data=read_exact(stream,length)
        if name=='METADATA':
            m=io.BytesIO(data);frames,fps=struct.unpack('<if',read_exact(m,8));ref=read_string(m)
            additive,pose=read_exact(m,2);frame=struct.unpack('<i',read_exact(m,4))[0]
            return dict(source=source,num_frames=frames,fps=fps,additive=additive,
                        ref_pose=ref,ref_type=pose,ref_frame=frame)
    raise ValueError('Missing animation metadata')


def resolve(emote,plan):
    """AdditiveCorrective exports are already baked by FP AnimExport.HandleSectionTree.

    Only accept that known layout when each correction matches its base interval
    and the downloaded UEANIM explicitly contains non-additive full-pose data.
    Other slots require an explicit blend policy.
    """
    resolved=copy.deepcopy(plan)
    if 'error' in resolved:raise ValueError(resolved['error'])
    source_assets={}
    for asset in emote['variants']:
        if digest(asset['path'])!=asset['sha256']:raise ValueError('Montage source changed')
        meta=animation_metadata(asset['path'])
        key=meta['source'].casefold()
        if key in source_assets and source_assets[key]['asset']['sha256']!=asset['sha256']:
            raise ValueError('Conflicting animation exports for montage source')
        source_assets[key]=dict(asset=asset,metadata=meta)
    slots=resolved['slots'];full=next(s for s in slots if s['name']=='FullBody')
    # FullBodyInMotion is an alternative traversal slot. WoW playback stops on
    # movement, so select the explicitly exported stationary FullBody track.
    moving=[s for s in slots if s['name']=='FullBodyInMotion' and s['segments']]
    if moving:resolved['omitted_alternatives']=['FullBodyInMotion'];resolved['motion_policy']='stationary FullBody'
    extra=[s for s in slots if s['name'] not in ('FullBody','FullBodyInMotion') and s['segments']]
    if not extra:
        resolved['slots']=[full]
        resolved['requirements']=[r for r in resolved['requirements'] if r!='layer_composition']
    if extra:
        if len(extra)!=1 or extra[0]['name']!='AdditiveCorrective':
            raise ValueError('Montage slot blend policy is not implemented')
        correction=extra[0]['segments'];chosen=[]
        for base in full['segments']:
            matching=[s for s in correction if abs(s['start']-base['start'])<.001 and abs(s['end']-base['end'])<.001]
            if len(matching)!=1:raise ValueError('No unique baked corrective interval')
            chosen.append(matching[0])
        full['segments']=chosen
        resolved['baked_corrective']=True
        resolved['slots']=[full]
        resolved['requirements']=[r for r in resolved['requirements'] if r!='layer_composition']
    assets={}
    for segment in full['segments']:
        key=segment['source'].casefold()
        if key not in source_assets:raise ValueError('Missing montage source export: '+segment['source'])
        row=source_assets[key]
        if row['metadata']['additive']!=0:raise ValueError('Montage source is not a baked full pose')
        duration=row['metadata']['num_frames']/row['metadata']['fps']
        if segment['source_end']>duration+.002:raise ValueError('Montage trim exceeds exported clip duration')
        assets[segment['source']]=row
    resolved['assets']=assets
    resolved['execution_supported']=not resolved['requirements']
    return resolved


def flat_compatible(plan):
    segments=plan['slots'][0]['segments']
    if len(segments)!=1 or plan['montage_rate']!=1:return False
    s=segments[0]
    if s['source_start']!=0 or s['rate']!=1 or s['repeats']!=1 or s['start']!=0:return False
    cursor=0
    for name in plan['route']:
        section=plan['sections'][name]
        if abs(section['start']-cursor)>.002:return False
        cursor=section['end']
    return abs(cursor-plan['duration_seconds'])<.002


def loop_region(plan):
    spans=[plan['sections'][name]['end']-plan['sections'][name]['start'] for name in plan['route']]
    start=sum(spans[:plan['loop_from']])/plan['montage_rate'] if plan['loop_from'] is not None else 0
    return dict(start_ms=round(start*1000),duration_ms=round(sum(spans)/plan['montage_rate']*1000))
