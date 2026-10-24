import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from studio_core import models
from studio_core import cache,catalog
from studio_core.storage import atomic_json


class ValidationSessionTests(unittest.TestCase):
    def test_catalog_snapshot_reloads_after_atomic_update(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'Reports') as directory:
            path=Path(directory)/'emotes.json'
            atomic_json(path,dict(emotes=[dict(id='first')]))
            context=cache.Context.__new__(cache.Context)
            with patch.object(catalog,'CATALOG',path), patch.object(cache,'read_catalog',wraps=catalog.read_catalog) as reads:
                self.assertEqual(context.catalog_snapshot()['emotes'][0]['id'],'first')
                context.catalog_snapshot()
                self.assertEqual(reads.call_count,1)
                atomic_json(path,dict(emotes=[dict(id='updated')]))
                self.assertEqual(context.catalog_snapshot()['emotes'][0]['id'],'updated')
                self.assertEqual(reads.call_count,2)

    def test_cache_scope_checks_only_selected_emotes(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        context=SimpleNamespace(fingerprint=Mock(return_value=('fingerprint',{})))
        rows=[dict(id='selected',versions=[]),dict(id='unselected',versions=[])]
        with patch.object(cache,'read_catalog',return_value=dict(emotes=rows)), \
             patch('studio_core.variants.resolve_variant',return_value='CMF'), \
             patch.object(cache,'find_current',return_value=None):
            result=cache.inspect_cache(context,'profile','target','CMF',identifiers={'selected'})
            self.assertEqual(set(result),{'selected'})
            context.fingerprint.assert_called_once_with('selected','CMF','profile','target')

    def test_reuses_checks_but_rejects_changed_asset_and_registry(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'Reports') as directory:
            root=Path(directory)
            asset=root/'model.m2'; asset.write_bytes(b'original')
            scene=root/'model.blend'; scene.write_bytes(b'scene')
            row=dict(id='target',path=str(asset),scene=str(scene),
                     files={str(asset):hashlib.sha256(b'original').hexdigest()},
                     scene_sha256=hashlib.sha256(b'scene').hexdigest())
            registry=root/'models.json'
            atomic_json(registry,dict(models=[row]))
            with patch.object(models,'REGISTRY',registry), \
                 patch.object(models,'read_models',wraps=models.read_models) as reads, \
                 patch.object(models,'digest',wraps=models.digest) as hashes:
                with models.validation_session():
                    for _ in range(5): models.checked_model('target',scene)
                    self.assertEqual(reads.call_count,1)
                    self.assertEqual(hashes.call_count,2)
                    asset.write_bytes(b'modified and longer')
                    with self.assertRaisesRegex(ValueError,'Model assets changed'):
                        models.checked_model('target',scene)
                    row['files'][str(asset)]=hashlib.sha256(asset.read_bytes()).hexdigest()
                    atomic_json(registry,dict(models=[row]))
                    models.checked_model('target',scene)
                    self.assertEqual(reads.call_count,2)
                models.checked_model('target',scene)
                self.assertEqual(reads.call_count,3)


if __name__=='__main__': unittest.main()
