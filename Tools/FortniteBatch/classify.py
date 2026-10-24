"""Conservative, evidence-based selection from the Fortnite Porting audit."""
import argparse
import collections
import csv
import hashlib
import json
import re
from pathlib import Path


# These notify types control animation, weapon holstering, or audio. Effects,
# gameplay cues, item swapping and unrecognized Blueprint notifies need review.
BENIGN_NOTIFIES = {
    'FortAnimNotifyState_EmoteRetargeting',
    'FortAnimNotifyState_EmoteSound',
    'FortAnimNotifyState_OnetimeSyncWithOffset',
    'FortAnimNotifyState_RandomizeNextSection',
    'AnimNotifyState_HolsterWeapon_C',
    'AnimNotify_PlaySound',
    'AnimNotify_SoundLibrary',
    'AnimNotifyState_SoundLibrary',
    'AnimNotifyState_DisableFootFX_C',
}
BENIGN_NAMES = {
    'FortEmoteRetargeting', 'FortEmoteSound',
    'Fort Anim Notify State Emote Sound', 'FortOnetimeSyncWithOffset',
    'FortRandomizeNextSection', 'HolsterWeapon', 'HolsterWeapon_C',
    'PlaySound', 'SoundLibrary', 'DisableFootFX_C',
}
COOP_NOTIFIES = {
    'FortAnimNotifyState_PlaySyncedMontage',
    'FortAnimNotifyState_SyncedEmoteAlign',
    'AnimNotifyState_SyncedEmoteFollower_C',
}


def scalar_strings(value):
    if isinstance(value, dict):
        for child in value.values():
            yield from scalar_strings(child)
    elif isinstance(value, list):
        for child in value:
            yield from scalar_strings(child)
    elif isinstance(value, str):
        yield value


def nonempty_reference(value):
    return isinstance(value, dict) and any(
        value.get(key) for key in ('AssetPathName', 'ObjectPath', 'ObjectName'))


def classify(row):
    reasons, review = [], []
    asset_path = Path(row['AssetJson'])
    asset_bytes = asset_path.read_bytes()
    asset = json.loads(asset_bytes)
    props = asset.get('Properties', {})
    tags = {s for s in scalar_strings(props.get('DataList', [])) if s.startswith('Cosmetics.')}
    tags.update(s for s in scalar_strings(props.get('GameplayTags', [])) if s.startswith('Cosmetics.'))
    variants = row['Variants']
    notify_types = {t for v in variants for t in v['NotifyTypes']}
    notify_names = {n for v in variants for n in v['NamedNotifies']}
    prop_evidence = [p for v in variants for p in v['PropEvidence']]
    prop_evidence.extend(n for n in notify_names if 'prop' in n.lower())
    if prop_evidence:
        reasons.append('props')
    coop_evidence = [tag for tag in tags if 'synced' in tag.lower() or tag.endswith('.Emote.Group')]
    for key, value in props.items():
        if key.startswith('GroupEmoteToStart') and nonempty_reference(value):
            coop_evidence.append(key)
        if key == 'bGroupAnimationSync' and value is True:
            coop_evidence.append(key)
    coop_evidence.extend(sorted(notify_types & COOP_NOTIFIES))
    if coop_evidence:
        reasons.append('co-op/synced')
    # The optional user-facing tag is incomplete (e.g. Dance Monkey). For an
    # untagged favorite, require real music references in both audited graphs.
    # Props, synced behavior, variant and unknown-notify checks still apply.
    tagged='Cosmetics.UserFacingFlags.Emote.Dance' in tags
    music_pair=all(any("EmoteMusic'" in detail or "EmoteMusic3P'" in detail
                       for detail in v.get('NotifyDetails',[])) for v in variants) and len(variants)==2
    if not tagged and not music_pair:
        review.append('untagged favorite needs musical-performance review')
    if row['Status'] != 'inspected' or row['Errors']:
        review.extend(row['Errors'] or ['asset inspection incomplete'])
    labels = {v['Label'] for v in variants}
    if labels != {'Male Medium', 'Female Medium'}:
        review.append('separate male/female medium pair unavailable')
    for variant in variants:
        review.extend(variant['Errors'])
        if len(variant['AnimationPaths']) < 2:
            review.append('no animation sequence resolved')
        for path in variant['AnimationPaths']:
            if re.search(r'(?:^|[_/])CL[MF](?:[_/.]|$)', path, re.I):
                review.append('large-body animation referenced by medium montage: ' + path)
    unknown_types = notify_types - BENIGN_NOTIFIES - COOP_NOTIFIES
    unknown_types = {t for t in unknown_types if 'prop' not in t.lower()}
    unknown_names = notify_names - BENIGN_NAMES
    unknown_names = {n for n in unknown_names if 'prop' not in n.lower()}
    if unknown_types:
        review.append('effects/custom notify inspection needed: ' + ', '.join(sorted(unknown_types)))
    if unknown_names:
        review.append('custom notify names need inspection: ' + ', '.join(sorted(unknown_names)))
    ability = props.get('CustomDanceAbility')
    if nonempty_reference(ability) and not coop_evidence:
        review.append('custom gameplay ability needs inspection')
    status = 'excluded' if reasons else ('review' if review else 'ready')
    return {
        'Id': row['Id'], 'Name': row['Name'], 'AssetPath': row['AssetPath'],
        'Status': status, 'Reasons': reasons, 'Review': sorted(set(review)),
        'Tags': sorted(tags), 'PropEvidence': prop_evidence,
        'CoopEvidence': sorted(set(coop_evidence)),
        'DanceEvidence': 'user-facing tag' if tagged else 'music references in both medium graphs' if music_pair else 'needs review',
        'AssetSha256': hashlib.sha256(asset_bytes).hexdigest(),
        'Variants': variants,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('report_root', type=Path)
    args = parser.parse_args()
    root = args.report_root.resolve()
    audit_path = root / 'audit.json'
    source = audit_path.read_bytes()
    audit = json.loads(source)
    if len(audit) != 488 or len({r['AssetPath'].lower() for r in audit}) != 488:
        raise ValueError('Expected a complete audit of 488 unique dance favorites')
    rows = [classify(row) for row in audit]
    counts = dict(collections.Counter(r['Status'] for r in rows))
    manifest = {
        'SourceRevision': '8058810ece4405bfde931d97c72467b07034a881',
        'AuditSha256': hashlib.sha256(source).hexdigest(),
        'Policy': 'Dance tag or audited medium-pair music references; no props/co-op; hold unknown behavior',
        'Counts': counts, 'Items': rows,
    }
    (root / 'selection.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    with (root / 'selection.csv').open('w', newline='', encoding='utf-8-sig') as out:
        writer = csv.writer(out)
        writer.writerow(['Name', 'ID', 'Status', 'Exclusion reasons', 'Review reasons'])
        for row in rows:
            writer.writerow([row['Name'], row['Id'], row['Status'], '; '.join(row['Reasons']), '; '.join(row['Review'])])
    lines = ['# Fortnite favorites batch', '', f'Inspected: {len(rows)}.', '',
             f'Ready: {counts.get("ready", 0)}. Excluded: {counts.get("excluded", 0)}. Needs review: {counts.get("review", 0)}.', '',
             'Only ready entries are eligible for export. Prop/co-op evidence and uncertainty remain recorded in selection.json.', '',
             'A missing user-facing Dance tag is not an exclusion: audited music references in both medium graphs can establish eligibility.',
             'No prop spawn was detected across either medium montage and its referenced animation tracks; unfamiliar effects/abilities are held for review.',
             'Missing female overrides are held rather than duplicated or replaced with large variants.', '']
    (root / 'RESULTS.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps(counts))
    print('Exclusions (overlap):', dict(collections.Counter(reason for r in rows for reason in r['Reasons'])))


if __name__ == '__main__':
    main()
