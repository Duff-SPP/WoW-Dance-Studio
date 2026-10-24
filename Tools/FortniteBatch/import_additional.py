"""Validate and publish additional exports without writing original Input assets."""
import json,shutil,sys,uuid
from pathlib import Path,PureWindowsPath
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from studio_core.catalog import ROOT,digest,scan_emotes
from studio_core.fortnite_paths import IMPORTED
from studio_core.storage import atomic_json
from verify import verify_animation,verify_audio


def main():
    report=ROOT/'Reports/FortniteBatch/TagCorrection'
    records=json.loads((report/'exports.json').read_text())
    files={}
    for row in records:
        if row['Status']!='complete':raise ValueError('Export failed: '+row['Id'])
        for variant in row['Variants']:
            for file in variant['Files']:
                source=Path(file['Path'])
                if not source.is_file() or source.stat().st_size!=file['Bytes'] or digest(source)!=file['Sha256']:
                    raise ValueError('Export missing/changed: '+str(source))
                if file['Kind']=='animation':verify_animation(source)
                else:verify_audio(source)
                parts=PureWindowsPath(file['Path']).parts
                relative=Path(*parts[parts.index('Assets')+1:])
                destination=(IMPORTED/'Assets'/relative).resolve()
                if not destination.is_relative_to(IMPORTED.resolve()):raise ValueError('Unsafe asset path')
                files[destination]=(source,file['Sha256'])
    for destination,(source,sha) in files.items():
        destination.parent.mkdir(parents=True,exist_ok=True)
        if destination.exists():
            if digest(destination)!=sha:raise ValueError('Existing imported file differs: '+str(destination))
            continue
        pending=destination.with_name(destination.name+'.'+uuid.uuid4().hex+'.tmp')
        try:
            shutil.copyfile(source,pending)
            if digest(pending)!=sha:raise ValueError('Import hash mismatch')
            pending.replace(destination)
        finally:
            if pending.exists():pending.unlink()
    catalog=scan_emotes(ROOT/'Input/Fortnite')
    result=dict(imported_emotes=len(records),files=len(files),catalog_entries=len(catalog['emotes']),
                input_unchanged=True,emotes=[dict(id=r['Id'],name=r['Name']) for r in records])
    atomic_json(report/'import_result.json',result);print(json.dumps(result,indent=2))


if __name__=='__main__':main()
