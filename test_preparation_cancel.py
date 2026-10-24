import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from studio_core import batch,catalog
from studio_core.storage import atomic_json,locked


class PreparationCancelTests(unittest.TestCase):
    def test_cancel_recovers_dead_runner_but_leaves_live_runner_owned(self):
        with tempfile.TemporaryDirectory(dir=catalog.ROOT/'Reports') as folder:
            root=Path(folder);queue=root/'queue.json'
            with patch.object(batch,'QUEUE',queue),patch.object(batch,'LIBRARY',root):
                atomic_json(queue,dict(batch='test',mode='running',jobs=[
                    dict(id='a',batch='test',emote='test',status='Running'),
                    dict(id='b',batch='test',emote='next',status='Pending')]))
                with locked(root/'runner.lock'):
                    self.assertEqual(batch.control('cancel')['remaining'],1)
                    self.assertEqual(batch.read_queue()['jobs'][1]['status'],'Cancelled')
                self.assertEqual(batch.control('cancel')['remaining'],0)
                self.assertEqual(batch.read_queue()['jobs'][0]['status'],'Cancelled')

    def test_cancel_and_pause_stop_before_fingerprinting(self):
        for action in ('cancel','pause'):
            with self.subTest(action=action), tempfile.TemporaryDirectory(dir=catalog.ROOT/'Reports') as folder:
                queue=Path(folder)/'queue.json'
                atomic_json(queue,dict(batch='previous',mode='idle',jobs=[]))
                def scan(*args,**kwargs):batch.control(action)
                args=SimpleNamespace(emotes='fixture')
                with patch.object(batch,'QUEUE',queue),patch.object(batch,'scan_emotes',side_effect=scan), \
                     patch.object(batch,'Context') as context:
                    result=batch.enqueue(args,lambda text:None)
                    self.assertTrue(result['preparation_cancelled'])
                    context.assert_not_called()
                    saved=batch.read_queue()
                    self.assertEqual(saved['batch'],'previous')
                    self.assertEqual(saved['jobs'],[])
                    self.assertEqual(saved['preparation']['status'],'cancelled')

    def test_scan_cancellation_does_not_publish_partial_catalog(self):
        with tempfile.TemporaryDirectory(dir=catalog.ROOT/'Reports') as folder:
            root=Path(folder);assets=root/'assets';assets.mkdir()
            for i in range(5):(assets/(str(i)+'.txt')).write_text('fixture')
            path=root/'emotes.json';atomic_json(path,dict(version=2,emotes=[]))
            before=path.read_bytes();calls=0
            def checkpoint():
                nonlocal calls
                calls+=1
                if calls==3:raise batch.PreparationCancelled()
            with patch.object(catalog,'CATALOG',path):
                with self.assertRaises(batch.PreparationCancelled):catalog.scan_emotes(assets,checkpoint=checkpoint)
            self.assertEqual(path.read_bytes(),before)
