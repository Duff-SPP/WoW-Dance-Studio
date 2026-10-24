"""Deterministic PCM soundtrack cycles for native character M2 $CSD events."""
import array, math, sys, wave
from pathlib import Path
from .catalog import ROOT,digest

RATE=44100

def duration_ms(version):
    validation=version['validation'];first,last=validation['frames'];fps=validation['fps']
    if not math.isfinite(fps) or fps<=0:raise ValueError('Invalid animation audio rate')
    count=version.get('imported',{}).get('num_frames')
    span=last-first
    if isinstance(count,int) and count==round(span)+1 and abs(span-round(span))<1e-5:span+=1
    duration=round(span/fps*1000)
    if not 0<duration<=600000:raise ValueError('Invalid animation audio duration')
    return duration

def pcm(asset):
    from .fortnite_paths import allowed_audio
    path=Path(asset['source']).resolve()
    if not allowed_audio(path) or digest(path)!=asset['sha256']:
        raise ValueError('Client audio source changed or outside Fortnite Input')
    with wave.open(str(path),'rb') as reader:
        channels=reader.getnchannels();rate=reader.getframerate();frames=reader.getnframes()
        if reader.getsampwidth()!=2 or channels not in (1,2) or reader.getcomptype()!='NONE' or not 0<frames<=rate*600:
            raise ValueError('Client audio requires bounded PCM16 mono/stereo WAV')
        data=array.array('h',reader.readframes(frames))
    if sys.byteorder!='little':data.byteswap()
    return resample(data,channels,rate,frames)


def resample(data,channels,rate,frames):
    if rate==RATE:
        if channels==2:return data
        out=array.array('h',[0])*(frames*2)
        out[0::2]=data;out[1::2]=data
        return out
    try:
        import numpy as np
    except ImportError:
        return resample_reference(data,channels,rate,frames)
    source=np.frombuffer(data,dtype=np.int16).reshape(frames,channels)
    out=array.array('h')
    count=round(frames*RATE/rate)
    for start in range(0,count,65536):
        indices=np.arange(start,min(start+65536,count),dtype=np.int64)
        position=(indices*rate).astype(np.float64)/RATE
        left=np.minimum(position.astype(np.int64),frames-1)
        right=np.minimum(left+1,frames-1)
        fraction=position-left
        a=source[left].astype(np.float64);b=source[right].astype(np.float64)
        values=np.rint(a+(b-a)*fraction[:,None]).astype(np.int16)
        if channels==1:values=np.repeat(values,2,axis=1)
        out.frombytes(values.tobytes())
    return out


def resample_reference(data,channels,rate,frames):
    out=array.array('h')
    for i in range(round(frames*RATE/rate)):
        position=i*rate/RATE;left=min(int(position),frames-1);right=min(left+1,frames-1);fraction=position-left
        for channel in range(2):
            a=data[left*channels+min(channel,channels-1)];b=data[right*channels+min(channel,channels-1)]
            out.append(round(a+(b-a)*fraction))
    return out


def render_full(asset,destination):
    """Normalize the complete source section, never crop it to animation time."""
    data=pcm(asset);frames=len(data)//2
    if sys.byteorder!='little':data.byteswap()
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(destination),'wb') as writer:
        writer.setnchannels(2);writer.setsampwidth(2);writer.setframerate(RATE);writer.writeframes(data.tobytes())
    return dict(sha256=digest(destination),samples=frames,sample_rate=RATE,channels=2,duration_ms=round(frames*1000/RATE))

def render_cycle(asset,destination):
    parts={role:pcm(value) for role,value in asset['parts'].items()}
    frames=round(asset['duration_ms']*RATE/1000);output=array.array('h')
    if 'intro' in parts:output.extend(parts['intro'][:frames*2])
    repeat=parts.get('loop',parts.get('track'))
    if repeat:
        if not repeat:raise ValueError('Empty client soundtrack')
        while len(output)<frames*2:output.extend(repeat[:frames*2-len(output)])
    if len(output)<frames*2:output.extend([0]*(frames*2-len(output)))
    if sys.byteorder!='little':output.byteswap()
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    with wave.open(str(destination),'wb') as writer:
        writer.setnchannels(2);writer.setsampwidth(2);writer.setframerate(RATE);writer.writeframes(output.tobytes())
    return dict(sha256=digest(destination),samples=frames,sample_rate=RATE,channels=2,duration_ms=asset['duration_ms'])
