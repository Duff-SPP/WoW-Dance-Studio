import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from studio_core.storage import atomic_json


class AtomicStorageTests(unittest.TestCase):
    def test_windows_reader_sharing_failure_is_retried(self):
        import os
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'Reports') as directory:
            path=Path(directory)/'queue.json'
            atomic_json(path,{'mode':'paused'})
            replace=os.replace
            error=PermissionError('reader has destination open');error.winerror=5
            calls=[]
            def transient(source,destination):
                calls.append(source)
                if len(calls)==1:raise error
                replace(source,destination)
            with patch('studio_core.storage.os.replace',side_effect=transient):
                atomic_json(path,{'mode':'running'})
            self.assertEqual(len(calls),2)
            self.assertEqual(json.loads(path.read_text()),{'mode':'running'})
            self.assertEqual(list(Path(directory).glob('*.tmp')),[])

    def test_checksum_reuse_detects_replacement_and_mutation(self):
        import hashlib
        from studio_core.storage import ContentChecks
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'Reports') as directory:
            path=Path(directory)/'asset';path.write_bytes(b'first')
            calls=[]
            def digest(file):
                calls.append(file)
                return hashlib.sha256(file.read_bytes()).hexdigest()
            checks=ContentChecks(digest)
            first=checks.digest(path)
            self.assertEqual(checks.digest(path),first)
            self.assertEqual(len(calls),1)
            path.write_bytes(b'changed and larger')
            self.assertNotEqual(checks.digest(path),first)
            replacement=path.with_suffix('.replacement');replacement.write_bytes(b'replaced')
            replacement.replace(path)
            self.assertEqual(checks.digest(path),digest(path))

    def test_checksum_does_not_cache_file_changed_during_hash(self):
        from studio_core.storage import ContentChecks
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'Reports') as directory:
            path=Path(directory)/'asset';path.write_bytes(b'first')
            def digest(file):
                file.write_bytes(b'modified during read')
                return 'untrusted'
            checks=ContentChecks(digest)
            with self.assertRaisesRegex(ValueError,'changed during checksum'):
                checks.digest(path)
            self.assertFalse(checks.entries)

    def test_retry_keeps_pending_work_in_active_batch(self):
        from studio_core import batch
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'Reports') as directory:
            path=Path(directory)/'queue.json'
            atomic_json(path,dict(batch='active',mode='paused',jobs=[dict(status='Pending',batch='active'),dict(status='Failed',batch='old')]))
            with patch.object(batch,'QUEUE',path):
                state=batch.control('retry')
                self.assertEqual(state['remaining'],2)
                self.assertTrue(all(j['batch']=='active' for j in state['jobs']))

    def test_failed_replace_preserves_original(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent/'Reports') as directory:
            path=Path(directory)/'queue.json'
            atomic_json(path,{'mode':'paused'})
            with patch('studio_core.storage.os.replace',side_effect=OSError('interrupted replacement')):
                with self.assertRaises(OSError): atomic_json(path,{'mode':'running'})
            self.assertEqual(json.loads(path.read_text()),{'mode':'paused'})
            self.assertEqual(list(Path(directory).glob('*.tmp')),[])


if __name__=='__main__': unittest.main()
