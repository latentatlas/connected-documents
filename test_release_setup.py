import json
from pathlib import Path
import tempfile
import unittest
from datetime import timedelta

from configure_live import configure
from connected_work.nebius_provider import MODEL,Client
from execution.nebius_guard.budget import file_sha,utcnow


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.records=self.root/'records';self.records.mkdir()
        proof=self.records/'proof.txt';proof.write_text('OFFLINE TEST ONLY; NOT REAL PROVIDER EVIDENCE')
        ev={'path':str(proof),'sha256':file_sha(proof)}
        account={'account_id':'offline-test-account','organization':'offline-test-org','project':'offline-test-project'}
        self.operator={'account':account,'model':MODEL,**{k:True for k in ('account_access_verified','billing_behavior_reviewed','model_available_verified','credit_only_execution_authorized')}}
        self.credit=dict(account,source='authenticated_nebius_console',observed_at=utcnow().isoformat(),billing_active=True,
            credit_eligible_for_model=True,balance_consistent=True,balance_evidence=ev,expiry_evidence=ev,
            expiry={'kind':'non_expiring','expires_at':None},free_credit_usd='5.00',account_balance_usd='5.00')
        self.price={'model':MODEL,'input_usd_per_million':'0.30','output_usd_per_million':'0.90',
            'price_verified_at':utcnow().isoformat(),'price_evidence':ev}
        self.save()
    def save(self):
        for name,value in [('operator',self.operator),('credit',self.credit),('price',self.price)]:
            (self.records/(name+'.json')).write_text(json.dumps(value))
    def test_explicit_authorization_and_no_reset(self):
        with self.assertRaisesRegex(ValueError,'EXPLICIT_LOCAL_AUTHORIZATION_REQUIRED'):
            configure(self.records,self.root)
        result=configure(self.records,self.root,True)
        self.assertEqual(result['provider_calls'],0)
        Client(self.root/'work/control').preflight(self.root/'work/runtime')
        saved=json.loads((self.root/'work/control/credit.json').read_text())
        self.assertEqual(saved,self.credit)
        with self.assertRaisesRegex(ValueError,'EXISTING_SCOPE_MUST_NOT_BE_RESET'):
            configure(self.records,self.root,True)
    def test_stale_evidence_and_wrong_account_leave_no_control(self):
        self.credit['observed_at']=(utcnow()-timedelta(minutes=3)).isoformat();self.save()
        with self.assertRaisesRegex(ValueError,'CREDIT_CHECK_STALE'):
            configure(self.records,self.root,True)
        self.assertFalse((self.root/'work/control').exists())
        self.credit['observed_at']=utcnow().isoformat();self.credit['account_id']='another';self.save()
        with self.assertRaisesRegex(ValueError,'ACCOUNT_IDENTITY'):
            configure(self.records,self.root,True)
    def test_existing_workspace_cannot_obtain_fresh_scope(self):
        work=self.root/'work/runtime';work.mkdir(parents=True);(work/'prior.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'NEW_EMPTY_WORKSPACE_REQUIRED'):
            configure(self.records,self.root,True)
        self.assertFalse((self.root/'work/control').exists())


if __name__=='__main__':
    unittest.main()
