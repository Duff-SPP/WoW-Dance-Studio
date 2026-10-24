import unittest
from types import SimpleNamespace
from unittest.mock import patch
from studio_core.variants import model_sex, resolve_variant, source_candidate,main_performance


class VariantTests(unittest.TestCase):
    def test_main_clip_selection_preserves_ambiguity(self):
        main={'path':'Emote_Example_CMM.ueanim'}
        for suffix in ('Static','AdditiveIdentity','Traversal','Intro','Loop','Breakout'):
            self.assertEqual(main_performance([main,{'path':'Emote_Example_CMM_'+suffix+'.ueanim'}]),main)
        for paths in [('Emote_Example_CMF_Intro','Emote_Example_CMF_Loop'),('Emote_Example_CMM','Emote_Example_Alternate_CMM')]:
            with self.assertRaisesRegex(ValueError,'ambiguous'):
                main_performance([{'path':p+'.ueanim'} for p in paths])
        with self.assertRaisesRegex(ValueError,'ambiguous'):main_performance([])

    def test_bulk_resolves_from_checked_model_snapshot(self):
        with patch('studio_core.models.get_model',side_effect=AssertionError('unnecessary registry reload')):
            self.assertEqual(resolve_variant({'variants':[{'variant':'CMF'}]},'fixture',model={'sex':'female'}),'CMF')

    def test_source_rig_is_not_determined_by_performance_sex(self):
        male='Male/Fortnite_M_Avg_Player_Skeleton.uemodel'
        female='Female/Fortnite_F_Avg_Player_Skeleton.uemodel'
        self.assertEqual(source_candidate([male],'CMF'),male)
        self.assertEqual(source_candidate([female,male],'CMF'),female)
        self.assertIsNone(source_candidate([],'CMF'))
        self.assertIsNone(source_candidate([male,'Male/Other_Skeleton.uemodel'],'CMF'))

    def test_model_names(self):
        self.assertEqual(model_sex({'path':'humanfemale2.m2'}),'F')
        self.assertEqual(model_sex({'path':'TaurenMale.M2'}),'M')
        self.assertIsNone(model_sex({'path':'unknown.m2'}))
        self.assertEqual(model_sex({'path':'Characters/Player/Male/Male_Avg_Base/Fortnite_M_Avg_Player_Skeleton.uemodel'}),'M')
        self.assertEqual(model_sex({'path':'female_test/Player/Male/Male_Avg_Base/Fortnite_M_Avg_Player_Skeleton.uemodel'}),'M')

    def test_batch_resolves_each_emote_separately(self):
        from studio_core import batch
        emotes=[{'id':'one','variants':[{'variant':'CMF'},{'variant':'CMM'}]},
                {'id':'two','variants':[{'variant':'CLF'},{'variant':'CMM'}]}]
        args=SimpleNamespace(emotes='fixture',emote='one,two',variant='AUTO',target='fixture',
                             profile='Profiles/fixture.json',scene='fixture.blend',blender='blender.exe',force=False)
        state={'jobs':[]}
        with patch.object(batch,'scan_emotes'), patch.object(batch,'read_catalog',return_value={'emotes':emotes}), \
             patch.object(batch,'Context') as context, patch.object(batch,'find_current',return_value=None), patch.object(batch,'reuse_profile_revision',return_value=None), \
             patch.object(batch,'update',side_effect=lambda operation:operation(state)), patch.object(batch,'read_queue',return_value=state), patch.object(batch,'summary',return_value={}), \
             patch('studio_core.models.get_model',return_value={'sex':'female'}):
            context.return_value.fingerprint.return_value=('fixture',{})
            batch.enqueue(args)
        self.assertEqual([job['variant'] for job in state['jobs']],['CMF','CLF'])
        self.assertTrue(all(job['status']=='Pending' for job in state['jobs']))

    def test_prefers_medium_and_never_crosses_sex(self):
        emote={'variants':[{'variant':v} for v in ('CLF','CMF','CMM')]}
        with patch('studio_core.models.get_model',return_value={'sex':'female'}):
            self.assertEqual(resolve_variant(emote,'fixture'),'CMF')
            self.assertEqual(resolve_variant({'variants':[{'variant':'CLF'}]},'fixture'),'CLF')
            with self.assertRaisesRegex(ValueError,'No female'):
                resolve_variant({'variants':[{'variant':'CMM'}]},'fixture')
            self.assertEqual(resolve_variant(emote,'fixture','CMM'),'CMM')

    def test_unknown_requires_explicit_selection(self):
        with patch('studio_core.models.get_model',return_value={'path':'unknown.m2'}):
            with self.assertRaisesRegex(ValueError,'unknown'):
                resolve_variant({'variants':[]},'fixture')

if __name__=='__main__': unittest.main()
