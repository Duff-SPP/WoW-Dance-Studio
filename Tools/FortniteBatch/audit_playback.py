"""Report each catalog variant's experimental playback capability without converting."""
import json
import sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from studio_core.montage_assets import resolve,flat_compatible
from studio_core.storage import atomic_json


def main():
    catalog=json.loads((ROOT/'Output/Library/emotes.json').read_text(encoding='utf-8'))
    plans=json.loads((ROOT/'Output/Library/montage_playback.json').read_text())
    rows=[];counts=Counter()
    for emote in catalog['emotes']:
        record=plans['emotes'].get(emote.get('export_id',''))
        if not record:continue
        for gender,plan in record['variants'].items():
            try:
                resolved=resolve(emote,plan)
                status='held_dynamic_routing' if resolved['routing_notifies'] else 'reuse_full_clip' if flat_compatible(resolved) else 'compose_sections'
                row=dict(emote=emote['name'],variant=gender,status=status,requirements=resolved['requirements'],
                         baked_corrective=resolved.get('baked_corrective',False),motion_policy=resolved.get('motion_policy'))
            except (ValueError,OSError,KeyError,TypeError) as error:
                status='held_unresolved';row=dict(emote=emote['name'],variant=gender,status=status,error=str(error))
            rows.append(row);counts[status]+=1
    atomic_json(ROOT/'Reports/montage_capability_audit.json',dict(counts=dict(counts),rows=rows,in_game_verified=False))
    print(dict(counts))
    for row in rows:
        if row['status'].startswith('held'):print(row['emote'],row['variant'],row.get('error',row.get('requirements')))


if __name__=='__main__':main()
