import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from studio_core.catalog import ROOT,digest
from studio_core.export_manifest import load_index,records_for,referenced_audio


class ExportManifestTests(unittest.TestCase):
    def test_exact_content_binding_and_split_sound_folders(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'Reports') as name:
            folder=Path(name);files=[]
            for rel in ('BRCosmetics/Sounds/OtherName/Emote_OtherName_Intro.wav','Game/Sounds/OtherName/Emote_OtherName_MX_LP.wav','Game/Sounds/OtherName/Emote_OtherName_SFX_Clap.wav'):
                path=folder/'Assets'/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(rel.encode())
                files.append(dict(Kind='audio',Path='C:/Export/Assets/'+rel,Sha256=digest(path)))
            record=dict(Id='EID_Public',Name='Public Name',Status='complete',Variants=[{'Files':[dict(Kind='animation',Sha256='exact-animation'),*files]}])
            manifest=folder/'exports.json';manifest.write_text(json.dumps([record]))
            index=load_index(manifest)
            self.assertFalse(records_for(index,['different-animation']))
            self.assertEqual(records_for(index,['exact-animation'])[0]['Name'],'Public Name')
            audio,warnings,details=referenced_audio(record,folder,digest)
            self.assertEqual(set(audio),{'intro','loop'});self.assertFalse(warnings)
            self.assertTrue(all('SFX' not in str(p) for p in audio.values()))
            audio['loop'].write_bytes(b'changed')
            self.assertEqual(set(referenced_audio(record,folder,digest)[0]),{'intro'})

    def test_genuine_alternatives_remain_ambiguous(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'Reports') as name:
            folder=Path(name);files=[]
            for n in ('A','B'):
                p=folder/'Assets'/(n+'_Loop.wav');p.parent.mkdir(exist_ok=True);p.write_bytes(n.encode())
                files.append(dict(Kind='audio',Path='C:/Export/Assets/'+p.name,Sha256=digest(p)))
            record=dict(Id='id',Variants=[{'Files':files}])
            audio,warnings,details=referenced_audio(record,folder,digest)
            self.assertFalse(audio);self.assertEqual(details['status'],'ambiguous')


if __name__=='__main__':unittest.main()
