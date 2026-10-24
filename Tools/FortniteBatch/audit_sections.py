"""Read-only audit of every catalog clip against saved favorite animation graphs."""
import collections
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from studio_core.variants import main_performance
from Tools.FortniteBatch.verify import verify_animation


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def run():
    audits = {}
    for folder in ('Reports/FortniteBatch', 'Reports/FortniteBatch/TagCorrection'):
        for row in load(ROOT / folder / 'audit.json'):
            audits[row['Id']] = row
    catalog = load(ROOT / 'Output/Library/emotes.json')
    files = {}; errors = []
    for emote in catalog['emotes']:
        for clip in emote['variants']:
            path = clip['path']
            if path in files:
                continue
            try:
                files[path] = verify_animation(Path(path), allow_large=True)
            except (ValueError, OSError) as error:
                files[path] = {}; errors.append(dict(path=path, error=str(error)))
    results = []
    for emote in catalog['emotes']:
        ids = set(emote.get('export_ids', []))
        if emote.get('export_id'): ids.add(emote['export_id'])
        records = [audits[i] for i in ids if i in audits]
        all_sources = {files[v['path']].get('source', '').casefold() for v in emote['variants']} - {''}
        variants = []
        for gender in sorted({v['variant'] for v in emote['variants']}):
            clips = [v for v in emote['variants'] if v['variant'] == gender]
            sources = {files[v['path']].get('source', '').casefold() for v in clips} - {''}
            try: selected = main_performance(clips)['path']
            except ValueError: selected = None
            graphs = [v for row in records for v in row['Variants']
                      if v['Label'] == {'CMM':'Male Medium','CMF':'Female Medium'}.get(gender)]
            graph_paths = sorted({p for g in graphs for p in g['AnimationPaths']})
            montage_paths = {g['MontagePath'].casefold() for g in graphs}
            unresolved = [p for p in graph_paths if p.casefold() not in sources and p.casefold() not in montage_paths]
            missing = [p for p in unresolved if p.casefold() not in all_sources]
            # Graph traversal also contains composite/montage containers. An unmatched
            # path is evidence requiring review, not proof that an animation is missing.
            temporal = [Path(v['path']).stem for v in clips
                        if set(re.split(r'[^a-z0-9]+', Path(v['path']).stem.casefold()))
                        & {'intro','loop','cycle','breakout','outro','exit','start','end'}]
            notifies = sorted({n for g in graphs for n in g.get('NotifyTypes', [])})
            routing = [n for n in notifies if any(t in n.casefold() for t in ('section','random','branch'))]
            reasons = []
            if not selected: reasons.append('ambiguous_clip_selection')
            if temporal and len(clips)>1: reasons.append('temporal_clip_names')
            if missing: reasons.append('graph_paths_not_in_any_catalog_clip_for_emote')
            if routing: reasons.append('section_routing_notify')
            if not graphs: reasons.append('no_saved_matching_graph')
            variants.append(dict(variant=gender, clips=[dict(path=v['path'], source=files[v['path']].get('source')) for v in clips],
                                 selected=selected, graph_paths=graph_paths, unmatched_graph_paths=unresolved,
                                 unavailable_graph_paths=missing,
                                 temporal_clips=temporal, routing_notifies=routing, review_reasons=reasons,
                                 section_timing_verified=False))
        results.append(dict(emote=emote['name'], id=emote['id'], export_ids=sorted(ids), variants=variants))
    reasons=collections.Counter(r for e in results for v in e['variants'] for r in v['review_reasons'])
    report=dict(catalog_emotes=len(results), catalog_variants=sum(len(e['variants']) for e in results),
                inspected_files=len(files), file_errors=errors, saved_favorites=len(audits),
                review_reason_variant_counts=dict(reasons),
                review_emotes=[e['emote'] for e in results if any(v['review_reasons'] for v in e['variants'])],
                limitation='Saved graphs lack section timing/routing. Single-clip entries cannot be certified as complete Fortnite montage playback.',
                emotes=results,
                favorites=[dict(id=r['Id'], name=r['Name'], status=r['Status'], errors=r['Errors'],
                                graph_count=len(r['Variants']),
                                animation_paths=sorted({p for v in r['Variants'] for p in v['AnimationPaths']}),
                                cataloged=any(r['Id'] in e['export_ids'] for e in results)) for r in audits.values()])
    output=ROOT/'Reports/all_emote_sections_audit.json'
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('emotes','favorites')},indent=2))


if __name__ == '__main__': run()
