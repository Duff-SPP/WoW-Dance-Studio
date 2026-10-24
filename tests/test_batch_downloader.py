"""Synthetic policy, catalog-filter, and managed-import regressions."""
import copy
import json
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from Tools.FortniteBatch import classify, catalog_tool
from Tools.FortniteBatch.verify import verify_animation


class BatchDownloaderTests(unittest.TestCase):
    def temporary(self):
        root = Path(__file__).resolve().parents[1]/'Reports'
        root.mkdir(exist_ok=True)
        context = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(context.cleanup)
        return Path(context.name)

    def row(self, root, identifier='EID_Fixture'):
        asset = root/(identifier+'.json')
        asset.write_text(json.dumps({'Properties':{}}))
        variants = []
        for sex in ('Male','Female'):
            variants.append(dict(Label=sex+' Medium',AnimationPaths=['/Game/Montage','/Game/Body'],
                                 NotifyTypes=[],NamedNotifies=[],PropEvidence=[],Errors=[],NotifyDetails=[]))
        return dict(Id=identifier,Name='Fixture',AssetPath='/Game/'+identifier+'.'+identifier,
                    AssetJson=str(asset),Status='inspected',Errors=[],Variants=variants)

    def test_music_optional_policy_keeps_prop_coop_and_unknown_gates(self):
        row = self.row(self.temporary())
        self.assertEqual(classify.classify(row)['Status'],'review')
        self.assertEqual(classify.classify(row,True)['Status'],'ready')
        for key,value,expected in [('PropEvidence',['prop spawn'],'excluded'),
                                   ('NotifyTypes',['FortAnimNotifyState_PlaySyncedMontage'],'excluded'),
                                   ('NotifyTypes',['UnknownEffect'],'review')]:
            changed = copy.deepcopy(row);changed['Variants'][0][key] = value
            self.assertEqual(classify.classify(changed,True)['Status'],expected)
        row['Variants'].pop()
        self.assertEqual(classify.classify(row,True)['Status'],'review')

    def test_classification_accepts_actual_counts_and_records_catalog_source(self):
        root = self.temporary()
        rows = [self.row(root,'EID_Fixture'+str(i)) for i in range(2)]
        (root/'audit.json').write_text(json.dumps(rows))
        (root/'audit-source.json').write_text(json.dumps({'Source':'catalog'}))
        with patch('sys.argv',['classify.py',str(root),'--allow-non-musical']):
            classify.main()
        result = json.loads((root/'selection.json').read_text())
        self.assertEqual(result['Source'],'catalog')
        self.assertEqual(result['Counts'],{'ready':2})
        rows.append(rows[0]);(root/'audit.json').write_text(json.dumps(rows))
        with patch('sys.argv',['classify.py',str(root)]),self.assertRaisesRegex(ValueError,'unique'):
            classify.main()

    def test_filter_uses_real_tags_and_name_and_does_not_select_unresolved(self):
        rows = [dict(Id='EID_B',Name='Beta',Status='inspected',Tags=['Cosmetics.Example']),
                dict(Id='EID_A',Name='Alpha',Status='inspected',Tags=['Cosmetics.Example']),
                dict(Id='EID_C',Name='Alpha unavailable',Status='unresolved',Tags=['Cosmetics.Example'])]
        self.assertEqual([r['Id'] for r in catalog_tool.selected(rows,'Cosmetics.Example',limit=1)],['EID_A'])
        self.assertEqual(len(catalog_tool.selected(rows,limit=0)),2)
        self.assertEqual(catalog_tool.selected(rows,search='BETA')[0]['Id'],'EID_B')
        self.assertEqual(catalog_tool.selected(rows,tag='Invented.Tag'),[])
        with self.assertRaises(ValueError):catalog_tool.selected(rows,limit=-1)
        with self.assertRaisesRegex(ValueError,'Ambiguous'):catalog_tool.selected(rows+[rows[0]])

    def test_incomplete_catalog_cannot_be_used_for_selection(self):
        root = self.temporary();catalog = root/'catalog.json';report = root/'selection'
        catalog.write_text(json.dumps([dict(Id='EID_A',Name='Alpha',Status='inspected',Tags=[])]))
        info = root/'catalog-info.json';info.write_text(json.dumps(dict(Source='catalog',Complete=False,Attempted=1)))
        arguments = ['catalog_tool.py','select',str(catalog),str(report)]
        with patch('sys.argv',arguments),self.assertRaisesRegex(ValueError,'incomplete'):
            catalog_tool.main()
        self.assertFalse(report.exists())
        info.write_text(json.dumps(dict(Source='catalog',Complete=True,Attempted=1)))
        with patch('sys.argv',arguments):catalog_tool.main()
        self.assertEqual(json.loads((report/'ids.json').read_text()),['EID_A'])

    def container(self, identifier):
        def string(value):
            raw = value.encode();return struct.pack('<i',len(raw))+raw
        return b'UEFORMAT'+string(identifier)+b'\x0a'+string('Fixture')+string('/Game/Fixture')+b'\x01'+string('ZSTD')+struct.pack('<ii',32,4)+b'\x28\xb5\x2f\xfd'

    def import_fixture(self):
        root = self.temporary();report = root/'Reports/run';downloads = root/'Output/downloads'
        report.mkdir(parents=True);downloads.mkdir(parents=True)
        files = []
        for kind,ext,container in [('animation','.ueanim','UEANIM'),('skeleton','.uemodel','UEMODEL')]:
            source = downloads/('Fixture'+ext);source.write_bytes(self.container(container))
            files.append(dict(Kind=kind,Path=str(source),Sha256=catalog_tool.digest(source),Bytes=source.stat().st_size))
        audit = report/'audit.json';audit.write_text('[]')
        selection = dict(AuditSha256=catalog_tool.digest(audit),Items=[dict(Id='EID_Fixture',Status='ready')])
        (report/'selection.json').write_text(json.dumps(selection))
        records = [dict(Id='EID_Fixture',Status='complete',Variants=[dict(Label='Male Medium',Files=files)])]
        (report/'exports.json').write_text(json.dumps(records))
        (report/'verification.json').write_text(json.dumps(dict(errors=[],missing=[])))
        return root,report,downloads,files

    def test_import_preserves_inputs_and_publishes_catalog_manifest(self):
        root,report,downloads,files = self.import_fixture()
        with patch.object(catalog_tool,'ROOT',root):catalog_tool.import_verified(report,downloads)
        manifest = json.loads((root/'Reports/FortniteBatch/verified_manual_exports.json').read_text())
        imported = Path(manifest[0]['Variants'][0]['Files'][0]['Path'])
        self.assertTrue(imported.is_file())
        self.assertTrue(Path(files[0]['Path']).is_file())
        self.assertTrue(imported.is_relative_to(root/'Output/FortniteImports/Assets'))

    def test_import_rejects_changed_files_and_preserves_conflicting_asset(self):
        root,report,downloads,files = self.import_fixture()
        destination = root/'Output/FortniteImports/Assets/Fixture.ueanim'
        destination.parent.mkdir(parents=True);destination.write_bytes(b'previous user file')
        with patch.object(catalog_tool,'ROOT',root),self.assertRaisesRegex(ValueError,'differs'):
            catalog_tool.import_verified(report,downloads)
        self.assertEqual(destination.read_bytes(),b'previous user file')
        Path(files[0]['Path']).write_bytes(b'changed')
        with patch.object(catalog_tool,'ROOT',root),self.assertRaisesRegex(ValueError,'missing, changed'):
            catalog_tool.import_verified(report,downloads)

    def test_skeleton_container_has_distinct_type_validation(self):
        root = self.temporary();path = root/'fixture.uemodel';path.write_bytes(self.container('UEMODEL'))
        self.assertEqual(verify_animation(path,identifier='UEMODEL')['version'],10)
        with self.assertRaises(ValueError):verify_animation(path)


if __name__ == '__main__':unittest.main()
