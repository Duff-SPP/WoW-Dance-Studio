import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from studio_core import source_scene as source


class SourceSceneTests(unittest.TestCase):
    def setUp(self):
        reports = Path(__file__).resolve().parents[1]/'Reports'
        reports.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=reports)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.scene = self.root/'Blender'/'Prepared.blend'
        self.assets = self.root/'assets'
        self.assets.mkdir()
        self.addCleanup(patch.stopall)
        patch.object(source,'ROOT',self.root).start()
        patch.object(source,'asset_roots',return_value=[self.assets]).start()

    def skeleton(self,name='Skeleton.uemodel',data=b'one'):
        path = self.assets/name
        path.write_bytes(data)
        return path

    def test_existing_scene_is_preserved_without_running_blender(self):
        self.scene.parent.mkdir()
        self.scene.write_bytes(b'existing')
        with patch.object(source.subprocess,'run') as worker:
            result = source.ensure_source_scene('missing',self.scene,self.assets,emit=lambda _:None)
        self.assertFalse(result['created'])
        worker.assert_not_called()
        self.assertEqual(self.scene.read_bytes(),b'existing')

    def test_identical_exports_are_deduplicated(self):
        first = self.skeleton()
        second = self.skeleton('OtherSkeleton.uemodel')
        self.assertIn(source.choose_source(self.assets),(first,second))

    def test_different_skeletons_require_selection(self):
        first = self.skeleton()
        self.skeleton('OtherSkeleton.uemodel',b'two')
        with self.assertRaisesRegex(ValueError,'Multiple different'):
            source.choose_source(self.assets)
        self.assertEqual(source.choose_source(self.assets,first),first)

    def test_missing_assets_defer_only_when_requested(self):
        self.assertTrue(source.ensure_source_scene('',self.scene,self.assets,if_available=True,emit=lambda _:None)['pending'])
        with self.assertRaisesRegex(ValueError,'No exported'):
            source.ensure_source_scene('',self.scene,self.assets)
        self.assertFalse(self.scene.exists())

    def test_new_scene_location_and_extension_are_checked(self):
        for path in (self.root/'outside.blend',self.root/'Blender'/'file.txt'):
            with self.assertRaises(ValueError):
                source.managed_scene(path)

    def test_worker_output_integrity_is_verified(self):
        self.skeleton()
        def worker(command,**kwargs):
            self.scene.write_bytes(b'created')
            report = Path(command[command.index('--report')+1])
            report.write_text(json.dumps(dict(scene=str(self.scene),scene_sha256='incorrect')))
            return type('Result',(),dict(returncode=0))()
        with patch.object(source.subprocess,'run',side_effect=worker):
            with self.assertRaisesRegex(ValueError,'integrity'):
                source.ensure_source_scene('blender',self.scene,self.assets,emit=lambda _:None)

    def test_failed_worker_does_not_report_success(self):
        self.skeleton()
        with patch.object(source.subprocess,'run',return_value=type('Result',(),dict(returncode=1))()):
            with self.assertRaisesRegex(RuntimeError,'Source preparation failed'):
                source.ensure_source_scene('blender',self.scene,self.assets,emit=lambda _:None)
        self.assertFalse(self.scene.exists())
