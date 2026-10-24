"""Offline filtering and verified import for the BAT emote menu."""
import argparse
import csv
import hashlib
import json
import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from studio_core.storage import atomic_json
from Tools.FortniteBatch.verify import verify_animation, verify_audio


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def selected(catalog, tag='', search='', limit=25):
    if limit < 0:
        raise ValueError('Maximum must be zero (all) or positive')
    rows = []
    identifiers = set()
    for row in catalog:
        if row.get('Status') != 'inspected':
            continue
        if tag and tag not in row.get('Tags', []):
            continue
        if search and search.casefold() not in (row['Id']+' '+row['Name']).casefold():
            continue
        key = row['Id'].casefold()
        if key in identifiers:
            raise ValueError('Ambiguous emote identifier: '+row['Id'])
        identifiers.add(key)
        rows.append(row)
    rows.sort(key=lambda row: (row['Name'].casefold(), row['Id'].casefold()))
    return rows[:limit] if limit else rows


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def import_verified(report, downloads):
    """Recheck evidence/files before publishing managed Studio imports."""
    report, downloads = Path(report).resolve(), Path(downloads).resolve()
    if not report.is_relative_to(ROOT/'Reports') or not downloads.is_relative_to(ROOT/'Output'):
        raise ValueError('Menu reports/downloads must be inside this Studio checkout')
    verification = load(report/'verification.json')
    if verification.get('errors') or verification.get('missing'):
        raise ValueError('Verification is incomplete; fix/retry exports before importing')
    selection = load(report/'selection.json')
    if selection['AuditSha256'] != digest(report/'audit.json'):
        raise ValueError('Audit changed after selection')
    ready = {row['Id']: row for row in selection['Items'] if row['Status'] == 'ready'}
    records = load(report/'exports.json')
    if not ready or len(records) != len(ready) or {row['Id'] for row in records} != set(ready):
        raise ValueError('Exports must match the complete ready selection')
    copies = {}
    for record in records:
        if record['Status'] != 'complete':
            raise ValueError('Export failed: '+record['Id'])
        for variant in record['Variants']:
            if not any(file['Kind'] == 'skeleton' for file in variant['Files']):
                raise ValueError('Export the matching source skeleton before importing')
            for file in variant['Files']:
                source = Path(file['Path']).resolve()
                if not source.is_relative_to(downloads) or not source.is_file() or source.stat().st_size != file['Bytes'] or digest(source) != file['Sha256']:
                    raise ValueError('Export missing, changed, or outside the menu download folder: '+str(source))
                if file['Kind'] == 'audio':
                    verify_audio(source)
                elif file['Kind'] in {'animation','skeleton'}:
                    verify_animation(source, identifier='UEANIM' if file['Kind']=='animation' else 'UEMODEL')
                else:
                    raise ValueError('Unknown file kind')
                relative = source.relative_to(downloads)
                destination = ROOT/'Output/FortniteImports/Assets'/relative
                previous = copies.get(destination)
                if previous and previous[1] != file['Sha256']:
                    raise ValueError('Conflicting exported asset paths')
                if destination.exists() and digest(destination) != file['Sha256']:
                    raise ValueError('Existing Studio import differs; preserved: '+str(destination))
                copies[destination] = (source,file['Sha256'])
    for destination,(source,expected) in copies.items():
        destination.parent.mkdir(parents=True,exist_ok=True)
        if not destination.exists():
            temporary = destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.tmp')
            try:
                shutil.copyfile(source,temporary)
                if digest(temporary) != expected:
                    raise ValueError('Copied asset checksum mismatch')
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
    # Retain the manifest shape the existing Studio catalog already reads.
    manifest_path = ROOT/'Reports/FortniteBatch/verified_manual_exports.json'
    merged = load(manifest_path) if manifest_path.exists() else []
    by_id = {row['Id']:row for row in merged}
    for record in records:
        clone = json.loads(json.dumps(record))
        for variant in clone['Variants']:
            for file in variant['Files']:
                relative = Path(file['Path']).resolve().relative_to(downloads)
                file['Path'] = str(ROOT/'Output/FortniteImports/Assets'/relative)
        by_id[record['Id']] = clone
    atomic_json(manifest_path,list(by_id.values()))
    print(f'Imported {len(copies)} verified files. Open Studio and Scan Emotes; original Input files were preserved.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command',required=True)
    tags = sub.add_parser('tags'); tags.add_argument('catalog',type=Path)
    choose = sub.add_parser('select'); choose.add_argument('catalog',type=Path); choose.add_argument('report',type=Path)
    choose.add_argument('--tag',default=''); choose.add_argument('--search',default=''); choose.add_argument('--limit',type=int,default=25)
    imported = sub.add_parser('import'); imported.add_argument('report',type=Path); imported.add_argument('downloads',type=Path)
    args = parser.parse_args()
    if args.command == 'import':
        import_verified(args.report,args.downloads); return
    catalog = load(args.catalog)
    if args.command == 'tags':
        counts = {}
        for row in catalog:
            for tag in set(row.get('Tags',[])):
                counts[tag] = counts.get(tag,0)+1
        for tag in sorted(counts):
            print(f'{counts[tag]:5}  {tag}')
        return
    info = load(args.catalog.with_name('catalog-info.json'))
    if info.get('Source') != 'catalog' or not info.get('Complete') or info.get('Attempted') != len(catalog):
        raise ValueError('Catalog scan is incomplete. Refresh the full catalog before selecting candidates.')
    rows = selected(catalog,args.tag,args.search,args.limit)
    if not rows:
        raise ValueError('No inspected catalog entries match these filters')
    args.report.mkdir(parents=True,exist_ok=True)
    atomic_json(args.report/'ids.json',[row['Id'] for row in rows])
    with (args.report/'candidates.csv').open('w',newline='',encoding='utf-8-sig') as stream:
        writer = csv.writer(stream); writer.writerow(['Name','Id','Tags'])
        for row in rows: writer.writerow([row['Name'],row['Id'],'; '.join(row.get('Tags',[]))])
    print(f'Selected {len(rows)} candidates for animation audit. This is not export approval.')
    for row in rows[:25]: print(row['Id']+'  '+row['Name'])


if __name__ == '__main__':
    main()
