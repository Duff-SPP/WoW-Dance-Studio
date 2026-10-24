"""Read-only reconciliation of favorites, batch exports and project catalog."""
import json,sys
from pathlib import Path,PureWindowsPath
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from studio_core.catalog import ROOT,read_catalog,digest
from studio_core.storage import atomic_json
from studio_core.fortnite_paths import IMPORTED


def main():
    reports=ROOT/'Reports/FortniteBatch'
    audit=json.loads((reports/'audit.json').read_text())
    selection=json.loads((reports/'selection.json').read_text())
    exports=json.loads((reports/'exports.json').read_text())
    settings=Path.home()/'AppData/Roaming/FortnitePorting/AppSettingsV4.json'
    favorites=json.loads(settings.read_text(encoding='utf-8-sig'))['Application']['FavoriteAssets']
    dances={p for p in favorites if '/Dances/' in p}
    catalog=read_catalog()['emotes'];by_hash={}
    for e in catalog:
        for v in e['variants']:by_hash.setdefault(v['sha256'],set()).add(e['id'])
    files={};links=[]
    for record in exports:
        families=set()
        for variant in record['Variants']:
            for f in variant['Files']:
                parts=PureWindowsPath(f['Path']).parts
                relative=parts[parts.index('Assets')+1:]
                p=ROOT/'Input/Fortnite/Assets'/Path(*relative)
                if not p.is_file():p=IMPORTED/'Assets'/Path(*relative)
                if str(p) not in files:
                    files[str(p)]=dict(kind=f['Kind'],valid=p.is_file() and p.stat().st_size==f['Bytes'] and digest(p)==f['Sha256'])
                if f['Kind']=='animation':families.update(by_hash.get(f['Sha256'],set()))
        links.append(dict(id=record['Id'],name=record['Name'],families=sorted(families),status=record['Status']))
    linked={i for row in links for i in row['families']}
    result=dict(favorites_total=len(favorites),favorite_dance_emotes=len(dances),audited_favorites=len(audit),
        favorites_added_since_audit=sorted(dances-{r['AssetPath'] for r in audit}),
        favorites_removed_since_audit=sorted({r['AssetPath'] for r in audit}-dances),
        classification=selection['Counts'],batch_exports=len(exports),catalog_entries=len(catalog),
        represented_exports=sum(bool(r['families']) for r in links),unrepresented_exports=[r for r in links if not r['families']],
        unique_catalog_families_linked=len(linked),
        additional_catalog_entries=[dict(id=e['id'],name=e['name']) for e in catalog if e['id'] not in linked],
        verified_project_animation_files=sum(f['kind']=='animation' and f['valid'] for f in files.values()),
        verified_project_audio_files=sum(f['kind']=='audio' and f['valid'] for f in files.values()),
        changed_or_missing_files=[p for p,f in files.items() if not f['valid']],
        missing_catalog_audio=[e['id'] for e in catalog if not e['audio']],
        manifest_resolved_soundtracks=[dict(id=e['id'],name=e['name'],roles=list(e['audio'])) for e in catalog if e.get('audio_match',{}).get('reason')=='verified exporter sound references'],
        exports=links)
    atomic_json(reports/'catalog_reconciliation.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='exports'},indent=2,ensure_ascii=True))


if __name__=='__main__':main()
