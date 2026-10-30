"""Validate operator-provided evidence and authorize one NEW local live scope.

Does not read a credential or call a provider. Does not refresh evidence times,
change an existing ledger, or copy a previous operator's authorization.
"""
import argparse
from datetime import timedelta
import json
from pathlib import Path
import tempfile

from connected_work.core import atomic, require
from connected_work.nebius_provider import Client, MODEL
from execution.nebius_guard.budget import evidence, timestamp, utcnow, money

ROOT=Path(__file__).resolve().parent


def configure(records,root=ROOT,authorized=False):
    require(authorized is True,'EXPLICIT_LOCAL_AUTHORIZATION_REQUIRED')
    records,root=Path(records).resolve(),Path(root).resolve()
    request=json.loads((records/'operator.json').read_text())
    credit=json.loads((records/'credit.json').read_text())
    price=json.loads((records/'price.json').read_text())
    account=request.get('account')
    require(isinstance(account,dict) and set(account)=={'account_id','organization','project'}
            and all(isinstance(v,str) and v.strip() for v in account.values()),'ACCOUNT_AUTHORIZATION_REQUIRED')
    require(all(credit.get(k)==v for k,v in account.items()),'ACCOUNT_IDENTITY')
    checks=('account_access_verified','billing_behavior_reviewed','model_available_verified','credit_only_execution_authorized')
    require(all(request.get(k) is True for k in checks),'OPERATOR_REVIEW_REQUIRED')
    require(request.get('model')==price.get('model')==MODEL,'POLICY_MODEL_MISMATCH')
    require(price.get('input_usd_per_million')=='0.30' and price.get('output_usd_per_million')=='0.90','PRICE_CHANGED_REPLAN_REQUIRED')
    for record in (price['price_evidence'],credit['balance_evidence'],credit['expiry_evidence']):
        require(Path(record['path']).is_absolute(),'ABSOLUTE_EVIDENCE_PATH_REQUIRED');evidence(record)
    now=utcnow()
    require(0<=(now-timestamp(price['price_verified_at'])).total_seconds()<=3600,'PRICE_CHECK_STALE')
    require(0<=(now-timestamp(credit['observed_at'])).total_seconds()<=120,'CREDIT_CHECK_STALE')
    require(credit.get('source')=='authenticated_nebius_console','CREDIT_SOURCE')
    require(all(credit.get(k) is True for k in ('billing_active','credit_eligible_for_model','balance_consistent')),'CREDIT_REVIEW_REQUIRED')
    money(credit['free_credit_usd']);money(credit['account_balance_usd'])
    work=root/'work';work.mkdir(mode=0o700,exist_ok=True)
    control=work/'control';workspace=work/'runtime'
    require(not control.exists(),'EXISTING_SCOPE_MUST_NOT_BE_RESET')
    require(not workspace.exists() or not any(workspace.iterdir()),'NEW_EMPTY_WORKSPACE_REQUIRED')
    auth=dict(authorized=True,scope='connected_work_nebius_v1',workspace=str(workspace),account=account,
              model=MODEL,operational_cap_usd='0.10',max_calls=12,expires_at=(now+timedelta(hours=24)).isoformat())
    policy=dict(account,model=MODEL,run_budget_usd='0.10',input_usd_per_million='0.30',output_usd_per_million='0.90',
                authorization_reference=str(control/'authorization.json'),price_verified_at=price['price_verified_at'],
                price_evidence=price['price_evidence'],untouched_credit_usd='0.25',**{k:request[k] for k in checks})
    # Write a complete staged directory before making it the active scope.
    with tempfile.TemporaryDirectory(prefix='.new-scope-',dir=work) as temp:
        stage=Path(temp)/'control';stage.mkdir(mode=0o700)
        for name,value in [('authorization',auth),('policy',policy),('credit',credit)]:
            atomic(stage/(name+'.json'),value)
        require(not control.exists(),'EXISTING_SCOPE_MUST_NOT_BE_RESET')
        stage.rename(control)
    return dict(control=str(control),workspace=str(workspace),provider_calls=0,authorization_hours=24,
                credential_installed=False,credit_observation_preserved=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--records',type=Path,required=True)
    parser.add_argument('--authorize-new-scope',action='store_true',help='Authorize up to $0.10 and 12 requests for 24 hours; no request is sent by setup')
    args=parser.parse_args()
    try:
        print(json.dumps(configure(args.records,authorized=args.authorize_new_scope)))
    except (ValueError,KeyError,OSError) as exc:
        raise SystemExit(str(exc)) from None
