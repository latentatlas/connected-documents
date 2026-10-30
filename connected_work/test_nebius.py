"""Provider boundary tests. Responses are fabricated; no live calls."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from .core import Store, atomic
from . import nebius_provider as n
from .provider import Provider
from execution.nebius_guard.budget import file_sha, utcnow


class NebiusBoundaries(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.control=self.root/'control';self.control.mkdir()
        self.store=Store(self.root/'workspace');now=utcnow()
        proof=self.control/'proof.txt';proof.write_text('OFFLINE TEST EVIDENCE, NOT A CONSOLE OBSERVATION')
        evidence={'path':str(proof),'sha256':file_sha(proof)}
        self.auth={'authorized':True,'scope':'connected_work_nebius_v1','workspace':str(self.store.folder.resolve()),
                   'model':n.MODEL,'operational_cap_usd':'0.10','max_calls':12,'expires_at':(now+timedelta(hours=1)).isoformat()}
        self.policy={'model':n.MODEL,'run_budget_usd':'0.10','input_usd_per_million':'0.30','output_usd_per_million':'0.90',
            'authorization_reference':str(self.control/'authorization.json'),'account_id':'offline-test-account',
            'organization':'offline-test-organization','project':'default-project','credit_only_execution_authorized':True,
            'account_access_verified':True,'billing_behavior_reviewed':True,'model_available_verified':True,
            'price_verified_at':now.isoformat(),'price_evidence':evidence,'untouched_credit_usd':'0.25'}
        self.credit={'source':'authenticated_nebius_console','observed_at':now.isoformat(),
            'account_id':self.policy['account_id'],'organization':self.policy['organization'],'project':'default-project',
            'billing_active':True,'credit_eligible_for_model':True,'balance_consistent':True,
            'balance_evidence':evidence,'expiry_evidence':evidence,'expiry':{'kind':'non_expiring','expires_at':None},
            'free_credit_usd':'50.00','account_balance_usd':'50.00'}
        self.auth['account']={k:self.policy[k] for k in ('account_id','organization','project')}
        for name,value in [('authorization',self.auth),('policy',self.policy),('credit',self.credit)]:atomic(self.control/(name+'.json'),value)
        self.client=n.Client(self.control)
        self.job=self.store.begin('research',1,{'passed':26,'total':40},'tr','nebius_token_factory')
        self.folder=self.store.folder/'calls'/self.job['id'];self.calls=0

    def transport(self,data,secret):
        self.calls+=1
        return {'model':n.MODEL,'usage':{'prompt_tokens':300,'completion_tokens':20,'total_tokens':320},
                'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'action':'noop','reason':'offline test','edits':[]})}}]}

    def fresh_credit(self):
        self.credit['observed_at']=utcnow().isoformat();atomic(self.control/'credit.json',self.credit)

    def test_durable_reservation_no_replay_and_test_provenance(self):
        content,usage=self.client.generate(self.job,self.folder,self.transport)
        self.assertEqual(self.calls,1);self.assertFalse(usage['fresh_model_execution_verified'])
        self.assertEqual(usage['external_calls'],0)
        ledger=n.read(self.control/'spending-control/ledger.json')
        self.assertEqual(ledger['attempts'][0]['status'],'settled')
        self.fresh_credit()
        with self.assertRaisesRegex(ValueError,'CALL_ALREADY_EXISTS'):
            self.client.generate(self.job,self.folder,self.transport)
        job=deepcopy(self.job);job.update(raw_response=content,usage=usage)
        with self.assertRaisesRegex(ValueError,'NOT_NATIVE_TRANSPORT'):n.verify_call(self.folder,job)
        self.assertEqual(self.calls,1)

    def test_missing_or_stale_credit_never_dispatches(self):
        self.credit['observed_at']=(utcnow()-timedelta(minutes=3)).isoformat();atomic(self.control/'credit.json',self.credit)
        with self.assertRaisesRegex(ValueError,'CREDIT_CHECK_STALE'):
            self.client.generate(self.job,self.folder,self.transport)
        self.assertFalse(self.folder.exists());self.assertEqual(self.calls,0)

    def test_unknown_cost_blocks_next_call_without_retry(self):
        def failure(*_):self.calls+=1;raise TimeoutError('SECRET SHOULD NOT ENTER LOGS')
        with self.assertRaises(TimeoutError):self.client.generate(self.job,self.folder,failure)
        self.assertNotIn('SECRET SHOULD', (self.folder/'failure.json').read_text())
        self.fresh_credit()
        with self.assertRaisesRegex(ValueError,'UNRESOLVED_ATTEMPT'):
            self.client.generate(self.job,self.folder,self.transport)
        self.assertEqual(self.calls,1)

    def test_wrong_model_missing_usage_and_truncation_fail(self):
        data=n.payload(self.job);raw=self.transport(data,'test')
        for key,value in [('model','another-model'),('usage',{}),('choices',[{'finish_reason':'length','message':{'content':'{}'}}])]:
            changed=deepcopy(raw);changed[key]=value
            with self.assertRaises(ValueError):n.response_usage(changed,data,1,True)

    def test_price_identity_and_workspace_fail_before_transport(self):
        self.policy['model']='another-model';atomic(self.control/'policy.json',self.policy)
        with self.assertRaisesRegex(ValueError,'POLICY_MODEL_MISMATCH'):
            self.client.generate(self.job,self.folder,self.transport)
        self.assertEqual(self.calls,0)
        with self.assertRaisesRegex(ValueError,'WORKSPACE_SCOPE_MISMATCH'):
            self.client.configuration(self.root/'different')

    def test_account_mismatch_and_missing_authorization_never_dispatch(self):
        self.policy['account_id']='wrong-account';atomic(self.control/'policy.json',self.policy)
        with self.assertRaisesRegex(ValueError,'ACCOUNT_IDENTITY'):
            self.client.generate(self.job,self.folder,self.transport)
        self.assertEqual(self.calls,0)
        self.auth.pop('account');atomic(self.control/'authorization.json',self.auth)
        with self.assertRaisesRegex(ValueError,'ACCOUNT_AUTHORIZATION_REQUIRED'):
            self.client.generate(self.job,self.folder,self.transport)
        self.assertEqual(self.calls,0)

    def test_no_local_fallback_and_no_test_response_acceptance(self):
        provider=Provider('nebius',self.control)
        with patch.object(provider.backend,'generate',side_effect=ValueError('RESPONSE_MODEL_MISMATCH')),patch('connected_work.local_provider.run_job') as local:
            provider.run_job(self.store,'research',self.job)
            local.assert_not_called()
        self.assertEqual(self.store.current('research')['pending']['status'],'blocked')
        self.assertEqual(self.store.current('research')['revision'],1)

    def test_changed_saved_transport_stops_next_dispatch(self):
        self.client.generate(self.job,self.folder,self.transport);self.fresh_credit()
        (self.folder/'raw_response.json').write_text('{}')
        next_job=deepcopy(self.job);next_job['id']='different'
        with self.assertRaisesRegex(ValueError,'CALL_ARTIFACT_CHANGED'):
            self.client.generate(next_job,self.folder.parent/'different',self.transport)
        self.assertEqual(self.calls,1)


if __name__=='__main__':unittest.main()
