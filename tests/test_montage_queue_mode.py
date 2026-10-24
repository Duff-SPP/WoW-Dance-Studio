import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,MagicMock

from studio_core import batch
from studio_core.storage import atomic_json


class MontageQueueModeTests(unittest.TestCase):
    def test_environment_restores_after_failure(self):
        with patch.dict(os.environ, {'WDS_MONTAGE_PREVIEW': 'original'}):
            with self.assertRaises(ValueError):
                with batch.montage_mode(True):
                    self.assertEqual(os.environ['WDS_MONTAGE_PREVIEW'], '1')
                    raise ValueError('blocked asset')
            self.assertEqual(os.environ['WDS_MONTAGE_PREVIEW'], 'original')
            with batch.montage_mode(False):
                self.assertNotIn('WDS_MONTAGE_PREVIEW', os.environ)
            self.assertEqual(os.environ['WDS_MONTAGE_PREVIEW'], 'original')

    def test_saved_job_modes_control_fingerprint_and_worker_on_resume(self):
        observed = []

        class Context:
            def __init__(self, *args):
                pass

            def fingerprint(self, *args):
                return ('sections' if os.environ.get('WDS_MONTAGE_PREVIEW') == '1' else 'ordinary'), {}

        def worker(command, **kwargs):
            mode = os.environ.get('WDS_MONTAGE_PREVIEW') == '1'
            observed.append(mode)
            report = Path(command[command.index('--report') + 1])
            atomic_json(report, {'version': 'converted', 'fingerprint': 'sections' if mode else 'ordinary'})
            process=MagicMock()
            process.__enter__.return_value=process
            process.poll.return_value=0
            process.returncode=0
            return process

        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'Reports') as directory:
            root = Path(directory)
            jobs = [dict(id=str(i), batch='active', emote='dance'+str(i), variant='CMF', target='target',
                         profile='profile', scene='scene', blender='blender', force=False, status='Pending',
                         attempts=0, montage_playback=mode) for i, mode in enumerate([True, False])]
            atomic_json(root/'queue.json', dict(batch='active', mode='paused', jobs=jobs))
            with patch.object(batch, 'ROOT', root), patch.object(batch, 'LIBRARY', root), \
                 patch.object(batch, 'QUEUE', root/'queue.json'), patch.object(batch, 'Context', Context), \
                 patch.object(batch, 'find_current', return_value=None), \
                 patch.object(batch, 'valid_output', return_value=True), \
                 patch.object(batch, 'read_catalog', return_value={'emotes': [dict(id=j['emote'], approvals={}) for j in jobs]}), \
                 patch.object(batch.subprocess, 'Popen', side_effect=worker), \
                 patch.dict(os.environ, {'WDS_MONTAGE_PREVIEW': 'caller'}):
                batch.control('resume')
                result = batch.run_queue(lambda text: None)
                self.assertEqual(result['completed'], 2)
                self.assertEqual(observed, [True, False])
                self.assertEqual(os.environ['WDS_MONTAGE_PREVIEW'], 'caller')


if __name__ == '__main__':
    unittest.main()
