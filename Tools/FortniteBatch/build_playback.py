"""Build playback plans while preserving Unreal's case-insensitive FName links.

Reference: Epic's FName documentation. Raw parser evidence is never overwritten.
"""
import argparse
import copy
import json
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from studio_core.montage import build_plans
from studio_core.storage import atomic_json


def normalize(graph):
    graph=copy.deepcopy(graph)
    sections=graph.get('Properties',{}).get('CompositeSections',[])
    names={s['SectionName'].casefold():s['SectionName'] for s in sections}
    if len(names)!=len(sections):raise ValueError('Duplicate section FNames')
    for section in sections:
        next_name=section.get('NextSectionName')
        if isinstance(next_name,str) and next_name.casefold() in names:
            section['NextSectionName']=names[next_name.casefold()]
    return graph


def main():
    parser=argparse.ArgumentParser();parser.add_argument('audit',type=Path);args=parser.parse_args()
    source=args.audit.resolve()
    if not source.is_relative_to(ROOT/'Reports'):raise ValueError('Audit must be inside Reports')
    rows=json.loads(source.read_text(encoding='utf-8-sig'))
    for row in rows:
        for variant in row['Variants']:
            for path,raw in variant.get('AnimationGraphs',{}).items():
                variant['AnimationGraphs'][path]=json.dumps(normalize(json.loads(raw)))
    normalized=source.with_name('normalized_audit.json')
    atomic_json(normalized,rows)
    result=build_plans(normalized)
    print('Built playback plans for',len(result['emotes']),'favorite definitions; raw evidence preserved:',source)


if __name__=='__main__':main()
