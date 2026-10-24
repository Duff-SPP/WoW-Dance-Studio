"""Client guards tested with synthetic profiles and binary identities."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from studio_core import client_compatibility as client
from studio_core.catalog import digest


class PublicClientTests(unittest.TestCase):
    def test_missing_profile_blocks_native_export(self):
        with tempfile.TemporaryDirectory(dir=client.ROOT/'Reports') as folder:
            with patch.object(client, 'PROFILE', Path(folder) / 'missing.json'):
                with self.assertRaisesRegex(ValueError, 'not configured'):
                    client.check_animation_ids([1792])

    def test_limit_boundary(self):
        with tempfile.TemporaryDirectory(dir=client.ROOT/'Reports') as folder:
            profile = Path(folder) / 'client.json'
            profile.write_text(json.dumps(dict(schema=1, client='Synthetic', animation_id_limit_exclusive=506)))
            with patch.object(client, 'PROFILE', profile):
                self.assertEqual(client.check_animation_ids([0, 505])['limit_exclusive'], 506)
                for identifier in (506, 1792):
                    with self.assertRaisesRegex(ValueError, 'Client compatibility blocked'):
                        client.check_animation_ids([identifier])

    def test_installed_binary_must_match_recorded_hash(self):
        with tempfile.TemporaryDirectory(dir=client.ROOT/'Reports') as folder:
            binary = Path(folder) / 'fixture.bin'
            binary.write_bytes(b'synthetic fixture, not a real DLL')
            profile = Path(folder) / 'client.json'
            profile.write_text(json.dumps(dict(schema=1, client='Synthetic', animation_id_limit_exclusive=506,
                                              installed_client_dll=dict(path=str(binary), sha256=digest(binary)))))
            with patch.object(client, 'PROFILE', profile):
                self.assertFalse(client.check_animation_ids([505])['client_playback_verified'])
                binary.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError, 'differs from the tested version'):
                    client.check_animation_ids([505])


if __name__ == '__main__':
    unittest.main()
