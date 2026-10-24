import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from studio_core import models,dbc_manager


class BatchAuthorizationTests(unittest.TestCase):
    def test_profile_authorization_is_bound_to_validated_content(self):
        model=dict(id='fixture',signature='target',identity='identity',source={'signature':'source'})
        profile=dict(generator='fixture',model_id='fixture',target_signature='target',model_identity='identity',
                     source_signature='source',status='Batch Export Authorized',validation={'passed':True})
        profile['approval']=dict(kind='user_requested_batch_export',content_sha256=models.profile_content_hash(profile))
        with tempfile.TemporaryDirectory(dir=models.ROOT/'Reports') as folder,patch.object(models,'checked_model',return_value=model):
            path=Path(folder)/'profile.json'
            path.write_text(json.dumps(profile))
            self.assertEqual(models.checked_profile(path,'fixture','scene')['status'],'Batch Export Authorized')
            changed=copy.deepcopy(profile);changed['validation']['passed']=False
            path.write_text(json.dumps(changed))
            with self.assertRaises(models.ProfileApprovalRequired):models.checked_profile(path,'fixture','scene')
            changed=copy.deepcopy(profile);changed['mapping']={'hip':'wrong'}
            path.write_text(json.dumps(changed))
            with self.assertRaisesRegex(models.ProfileApprovalRequired,'changed after'):models.checked_profile(path,'fixture','scene')

    def test_action_authorization_cannot_bypass_output_integrity(self):
        version=dict(id='fixture',version='v1',action_library_sha256='sha',profile_sha256='profile',target_id='target')
        emote=dict(id='fixture',versions=[version],export_authorizations={'v1':dict(kind='user_requested_batch_export',sha256='sha',profile_sha256='profile')})
        with patch('studio_core.cache.valid_output',return_value=False):
            good,errors=dbc_manager.eligible_versions(emote)
        self.assertFalse(good);self.assertIn('missing/changed',errors[0]['reason'])
        emote['export_authorizations']['v1']['sha256']='tampered'
        good,errors=dbc_manager.eligible_versions(emote)
        self.assertFalse(good);self.assertIn('review',errors[0]['reason'])


if __name__=='__main__':unittest.main()
