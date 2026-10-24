"""Standard-library discovery regression tests; no source assets are changed."""
from pathlib import Path
import tempfile
import unittest
from studio_core.audio import select_soundtrack


class AudioDiscoveryTests(unittest.TestCase):
    def test_pl_suffix_is_not_part_of_emote_identity(self):
        self.add('FutureDance/Emote_FutureDance_PL_Intro.wav')
        self.add('FutureDance/Emote_FutureDance_PL_Loop.wav')
        self.add('FutureDance/Emote_OtherDance_PL_Loop.wav')
        files,warnings=select_soundtrack(self.root,'FutureDance')
        self.assertEqual(set(files),{'intro','loop'})
        self.assertFalse(warnings)
        self.assertTrue(all('OtherDance' not in p.name for p in files.values()))

    def test_blender_action_suffix(self):
        self.add('FutureDance/Emote_FutureDance_Loop.wav')
        self.add('FutureDance/Emote_FutureDance_Intro.wav')
        files,warnings=select_soundtrack(self.root,'Emote_FutureDance_CMM.001')
        self.assertEqual(set(files),{'intro','loop'})
        self.assertFalse(warnings)

    def test_nested_emote_folder_and_generic_names(self):
        self.add('FutureDance/Music/Intro/Theme_Master.wav')
        self.add('FutureDance/Music/Loop/Theme_Master_Loop.wav')
        # The Intro directory alone is not a timing label; use explicit roles.
        (self.root/'FutureDance/Music/Intro/Theme_Master.wav').rename(self.root/'FutureDance/Music/Intro/Theme_Master_Intro.wav')
        files,warnings = select_soundtrack(self.root,'FutureDance')
        self.assertEqual(set(files),{'intro','loop'})
        self.assertFalse(warnings)

    def test_folder_full_track_and_effect_exclusion(self):
        self.add('FutureDance/Theme_Master.wav')
        self.add('FutureDance/Footsteps.wav')
        self.add('FutureDance/SFX_Impact.wav')
        files,_ = select_soundtrack(self.root,'FutureDance')
        self.assertEqual(set(files),{'track'})
        self.assertEqual(files['track'].name,'Theme_Master.wav')

    def test_folder_does_not_override_other_emote(self):
        self.add('FutureDance/Emote_OtherDance_Loop.wav')
        self.assertFalse(select_soundtrack(self.root,'FutureDance')[0])

    def test_duplicate_mixes_are_ambiguous(self):
        self.add('FutureDance/Emote_FutureDance_MX_Loop.wav')
        self.add('FutureDance/Emote_FutureDance_Music_Loop.wav')
        files,warnings=select_soundtrack(self.root,'FutureDance')
        self.assertFalse(files)
        self.assertTrue(warnings)

    def test_prefix_labels_role_position_and_variant_suffix(self):
        self.add('MX_Intro_Emote_FutureDance.wav')
        self.add('BGM_Emote_FutureDance_Loop01.wav')
        files,warnings=select_soundtrack(self.root,'Emote_FutureDance_CMM_Test')
        self.assertEqual(set(files),{'intro','loop'})
        self.assertFalse(warnings)

    def test_emote_identity_digits_preserved(self):
        self.add('Emote_Dance2_MX_Loop_01.wav')
        self.assertEqual(set(select_soundtrack(self.root,'Dance2')[0]),{'loop'})
        self.assertFalse(select_soundtrack(self.root,'Dance')[0])

    def test_mx_soundtrack_suffix(self):
        self.add('Emote_FuturePhoto_MX_Intro.wav')
        self.add('Emote_FuturePhoto_MX_Loop.wav')
        self.add('Emote_Unrelated_MX_Loop.wav')
        files,warnings = select_soundtrack(self.root,'FuturePhoto')
        self.assertEqual(set(files),{'intro','loop'})
        self.assertFalse(warnings)
        self.assertFalse(select_soundtrack(self.root,'Future')[0])
        self.add('Emote_BMX_Loop.wav')
        self.assertEqual(set(select_soundtrack(self.root,'BMX')[0]),{'loop'})
        self.assertFalse(select_soundtrack(self.root,'B')[0])

    def test_single_soundtrack(self):
        self.add('Emote_Future_Dance.wav')
        self.add('Emote_Unrelated.wav')
        files,warnings = select_soundtrack(self.root,'FutureDance')
        self.assertEqual(set(files),{'track'})
        self.assertFalse(warnings)
        self.assertFalse(select_soundtrack(self.root,'OtherDance')[0])

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[1]/'Reports')
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def add(self, relative):
        path = self.root/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    def test_matching_and_no_unrelated_fallback(self):
        for name in ['Emote_Maple_Dance_Intro.wav','Emote_Maple_Dance_Loop.wav','Emote_Other_Loop.wav']:
            self.add(name)
        files, warnings = select_soundtrack(self.root, 'Emote_MapleDance_CMM')
        self.assertEqual(set(files), {'intro','loop'})
        self.assertFalse(warnings)
        self.assertFalse(select_soundtrack(self.root, 'Unrelated')[0])
        self.assertFalse(select_soundtrack(self.root, 'MapleDanceExtra')[0])

    def test_plain_files_and_missing_intro(self):
        self.add('Intro.wav'); self.add('Loop.wav')
        self.assertEqual(set(select_soundtrack(self.root,'AnyAction')[0]), {'intro','loop'})
        (self.root/'Intro.wav').unlink()
        files, warnings = select_soundtrack(self.root,'AnyAction')
        self.assertEqual(set(files), {'loop'})
        self.assertTrue(warnings)

    def test_music_numbered_and_case(self):
        self.add('Emote_Future_Music_LOOP_01.WAV')
        self.assertEqual(set(select_soundtrack(self.root,'Emote_Future_CMF')[0]), {'loop'})

    def test_ambiguity_and_missing_directory(self):
        self.add('one/Emote_Dance_Loop.wav'); self.add('two/Emote_Dance_Loop.wav')
        self.assertFalse(select_soundtrack(self.root,'Emote_Dance_CMM')[0])
        self.assertFalse(select_soundtrack(self.root/'missing','Dance')[0])


if __name__ == '__main__':
    unittest.main()
