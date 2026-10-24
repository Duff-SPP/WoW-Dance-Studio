"""Compile authoritative Fortnite montage evidence; never infer routing from filenames."""
import json
import math
from pathlib import Path
from .catalog import ROOT
from .storage import atomic_json

PLANS = ROOT/'Output/Library/montage_playback.json'


def reference(value):
    if not isinstance(value, dict):
        raise ValueError('Missing animation reference')
    path=value.get('ObjectPath','').rsplit('.',1)[0]
    name=value.get('ObjectName','').split("'")
    if not path.startswith('/') or len(name)!=3:
        raise ValueError('Invalid animation object reference')
    return path+'.'+name[1].rsplit(':',1)[-1]


def number(value, name):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError('Invalid montage '+name)
    return float(value)


def compile_graph(graph, notify_types=()):
    """Represent trim/rate/repeat and exact section edges, including unplayable plans.

    Parsing a graph does not authorize its execution. Native loop-region support
    and additive source composition are separate capabilities.
    """
    if graph.get('Type')!='AnimMontage':
        raise ValueError('Nested composites/montages require explicit composition')
    props=graph.get('Properties',{})
    rate=number(props.get('RateScale',1),'rate scale')
    if rate<=0: raise ValueError('Reverse/zero montage rate requires separate support')
    length=number(props.get('SequenceLength'),'length')
    if not 0<length<=600: raise ValueError('Montage length outside supported range')
    slots=[]
    for slot in props.get('SlotAnimTracks',[]):
        segments=[]
        for raw in slot.get('AnimTrack',{}).get('AnimSegments',[]):
            start=number(raw.get('StartPos',0),'segment start')
            first=number(raw.get('AnimStartTime',0),'trim start')
            last=number(raw.get('AnimEndTime'),'trim end')
            speed=number(raw.get('AnimPlayRate',1),'segment rate')
            repeats=raw.get('LoopingCount',1)
            if not isinstance(repeats,int) or isinstance(repeats,bool) or not 1<=repeats<=1000:
                raise ValueError('Invalid segment repeat count')
            if start<0 or first<0 or last<=first or speed<=0:
                raise ValueError('Unsupported segment trim/rate')
            duration=(last-first)*repeats/speed
            if start+duration>length+0.002: raise ValueError('Segment exceeds montage length')
            segments.append(dict(source=reference(raw.get('AnimReference')),start=start,end=start+duration,
                                 source_start=first,source_end=last,rate=speed,repeats=repeats))
        slots.append(dict(name=slot.get('SlotName'),segments=segments))
    full=[s for s in slots if s['name']=='FullBody']
    if len(full)!=1 or not full[0]['segments']: raise ValueError('No unique FullBody montage slot')
    ordered=sorted(props.get('CompositeSections',[]),key=lambda s:s.get('LinkValue',0))
    if not ordered: raise ValueError('No section routing evidence')
    sections={}
    for i,raw in enumerate(ordered):
        if raw.get('LinkMethod','EAnimLinkMethod::Absolute')!='EAnimLinkMethod::Absolute':
            raise ValueError('Non-absolute section linkage requires explicit resolution')
        name=raw.get('SectionName')
        if not isinstance(name,str) or not name or name in sections: raise ValueError('Duplicate/invalid section')
        start=number(raw.get('LinkValue',0),'section start')
        end=number(ordered[i+1].get('LinkValue',0) if i+1<len(ordered) else length,'section end')
        if start<0 or end<=start or end>length+0.002: raise ValueError('Invalid section interval')
        next_name=raw.get('NextSectionName','None')
        sections[name]=dict(start=start,end=end,next=None if next_name in ('None','',None) else next_name)
    for section in sections.values():
        if section['next'] is not None and section['next'] not in sections: raise ValueError('Unresolved next section')
    if abs(next(iter(sections.values()))['start'])>0.002: raise ValueError('Montage entry does not start at zero')
    route=[];current=next(iter(sections));seen={}
    while current is not None and current not in seen:
        seen[current]=len(route);route.append(current);current=sections[current]['next']
    loop_from=seen[current] if current is not None else None
    routing=sorted(n for n in notify_types if any(t in n.casefold() for t in ('section','random','branch')))
    layered=[s['name'] for s in slots if s['name']!='FullBody' and s['segments']]
    segments=full[0]['segments']
    cursor=0
    for segment in sorted(segments,key=lambda s:s['start']):
        if abs(segment['start']-cursor)>0.002: raise ValueError('FullBody gap/overlap requires composition policy')
        cursor=segment['end']
    if abs(cursor-length)>0.002: raise ValueError('FullBody does not cover montage duration')
    requirements=[]
    if layered: requirements.append('layer_composition')
    if routing: requirements.append('dynamic_section_routing')
    if len(segments)!=1 or len(route)!=1 or sections[route[0]]['start']!=0 or sections[route[0]]['end']<length-0.002:
        requirements.append('section_composition')
    if loop_from not in (None,0): requirements.append('native_intro_once_loop_region')
    if rate!=1 or any(s['source_start']!=0 or s['rate']!=1 or s['repeats']!=1 for s in segments):
        requirements.append('trim_rate_repeat_bake')
    return dict(duration_seconds=length/rate,montage_rate=rate,slots=slots,sections=sections,
                route=route,loop_from=loop_from,layered_slots=layered,routing_notifies=routing,
                requirements=requirements,execution_supported=not requirements,
                sound_notifies=[n for n in props.get('Notifies',[]) if 'sound' in str(n.get('NotifyName','')).casefold()])


def build_plans(audit_path, destination=PLANS):
    from .catalog import digest
    audit_path=Path(audit_path).resolve()
    if not audit_path.is_relative_to(ROOT/'Reports'): raise ValueError('Evidence must be inside Reports')
    rows=json.loads(audit_path.read_text(encoding='utf-8-sig'));entries={}
    for row in rows:
        variants={}
        for variant in row['Variants']:
            label={'Male Medium':'CMM','Female Medium':'CMF'}.get(variant['Label'])
            if label is None: continue
            try:
                raw=variant.get('AnimationGraphs',{}).get(variant['MontagePath'])
                if not raw: raise ValueError('Missing serialized montage evidence')
                plan=compile_graph(json.loads(raw),variant.get('NotifyTypes',[]))
                plan['montage']=variant['MontagePath']
            except (ValueError,KeyError,TypeError) as error:
                plan=dict(execution_supported=False,requirements=['unresolved_graph'],error=str(error))
            variants[label]=plan
        entries[row['Id']]=dict(name=row['Name'],variants=variants)
    document=dict(schema=1,evidence=str(audit_path),evidence_sha256=digest(audit_path),emotes=entries)
    atomic_json(destination,document)
    return document


def playback(emote,variant):
    if not PLANS.is_file():return None
    document=json.loads(PLANS.read_text(encoding='utf-8'))
    identifiers=emote.get('export_ids',[]) or [emote.get('export_id')]
    plans=[document['emotes'][i]['variants'].get(variant) for i in identifiers if i in document['emotes']]
    plans=[p for p in plans if p]
    if not plans:return None
    if any(p!=plans[0] for p in plans[1:]):raise ValueError('Favorite aliases have differing montage playback plans')
    return plans[0]


def sample_time(plan, elapsed, repeat=True):
    """Reference playback clock for conversion/export validation, not an engine hook.

    Walk the verified section route. An intro is visited once; only the actual
    cyclic suffix repeats. Return per-slot trimmed source time for source baking.
    Dynamic routing remains unsupported until notify rules are implemented.
    """
    elapsed=number(elapsed,'elapsed time')
    if elapsed<0:raise ValueError('Negative playback time')
    if plan.get('routing_notifies'):raise ValueError('Dynamic section routing needs notify rules')
    route=plan['route'];sections=plan['sections'];rate=plan['montage_rate']
    remaining=elapsed*rate
    spans=[sections[name]['end']-sections[name]['start'] for name in route]
    loop=plan['loop_from'] if repeat else None
    if loop is not None:
        prefix=sum(spans[:loop]);period=sum(spans[loop:])
        if remaining>=prefix:remaining=prefix+(remaining-prefix)%period
    elif remaining>=sum(spans):return None
    for name,duration in zip(route,spans):
        if remaining<duration:
            position=sections[name]['start']+remaining
            samples=[]
            for slot in plan['slots']:
                for segment in slot['segments']:
                    if segment['start']<=position<segment['end']:
                        span=segment['source_end']-segment['source_start']
                        source_time=segment['source_start']+((position-segment['start'])*segment['rate'])%span
                        samples.append(dict(slot=slot['name'],source=segment['source'],seconds=source_time))
                        break
            return dict(section=name,montage_seconds=position,samples=samples)
        remaining-=duration
    return None
