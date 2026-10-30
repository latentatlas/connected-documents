# Live mode: explicit operator setup

The recorded walkthrough runs immediately. Live generation uses the operator's
Nebius account and is deliberately closed in a fresh checkout. This guide does
not authorize spending, publish credentials, or provide free judge access by
itself. Arrange judge access separately before submission.

The implementation currently reserves at most USD 0.10 across at most twelve
requests in a 24-hour authorization, with no automatic retries and at most 4,096
output tokens per request. These are local process controls, not a provider-wide
billing cap. The configured token-rate contract is 0.30 input / 0.90 output USD
per million tokens; verify the actual current model price. A different price
requires updating and testing the contract, not claiming the old price is fresh.

## 1. Prepare real evidence privately

In a private directory outside the distribution, create these three records.
Use your own exact account/organization/project identity. Do not copy another
operator's authorization or the fabricated evidence in unit tests.

`operator.json` records the operator's authorization and completed checks:

```json
{
  "account": {
    "account_id": "YOUR_ACCOUNT_ID",
    "organization": "YOUR_ORGANIZATION",
    "project": "YOUR_PROJECT"
  },
  "model": "nvidia/nemotron-3-super-120b-a12b",
  "account_access_verified": true,
  "billing_behavior_reviewed": true,
  "model_available_verified": true,
  "credit_only_execution_authorized": true
}
```

Set a check to true only after performing it. `price.json` contains:

```json
{
  "model": "nvidia/nemotron-3-super-120b-a12b",
  "input_usd_per_million": "0.30",
  "output_usd_per_million": "0.90",
  "price_verified_at": "ACTUAL_ISO_TIMESTAMP_WITH_TIMEZONE",
  "price_evidence": {"path": "/absolute/private/price-evidence", "sha256": "ACTUAL_FILE_SHA256"}
}
```

`credit.json` describes a genuine authenticated console observation:

```json
{
  "source": "authenticated_nebius_console",
  "observed_at": "ACTUAL_ISO_TIMESTAMP_WITH_TIMEZONE",
  "account_id": "YOUR_ACCOUNT_ID",
  "organization": "YOUR_ORGANIZATION",
  "project": "YOUR_PROJECT",
  "billing_active": true,
  "credit_eligible_for_model": true,
  "balance_consistent": true,
  "balance_evidence": {"path": "/absolute/private/balance-evidence", "sha256": "ACTUAL_FILE_SHA256"},
  "expiry_evidence": {"path": "/absolute/private/expiry-evidence", "sha256": "ACTUAL_FILE_SHA256"},
  "expiry": {"kind": "non_expiring", "expires_at": null},
  "free_credit_usd": "ACTUAL_DECIMAL_BALANCE",
  "account_balance_usd": "ACTUAL_DECIMAL_BALANCE"
}
```

The non-expiring example is valid only when your evidence confirms that status.
For expiring credit use `"kind": "expires_at"` with the actual ISO expiry. Verify
the supported expiry contract in `execution/nebius_guard/budget.py` before use.
Credit evidence must be at most 120 seconds old and price evidence at most one
hour old. Evidence paths must be absolute. Do not refresh a timestamp without a
new observation. Files with account data stay outside source distribution.

## 2. Authorize one fresh scope

Before opening the live workspace for the first time, run:

```sh
python3 -B configure_live.py --records /absolute/private/records --authorize-new-scope
```

This creates `work/control/` for `work/runtime/`. It validates existing evidence
without changing its observation times. It sends no request and installs no key.
It refuses an existing control directory or a non-empty workspace; it cannot
reset an exhausted session. If you already explored a blank workspace, choose a
fresh extracted release for the explicitly authorized run instead of deleting a
ledger. Creating another scope requires another deliberate spending decision.

## 3. Install your credential privately

Using your own secure local editor, create the owned regular file
`work/local-secrets/nebius.env` with exactly one line containing
`NEBIUS_API_KEY=` followed by your Nebius key. Set the file mode to 0600 and keep
the directory private. Never paste a key in chat, a command argument, README or
public form. The server reads the file; the browser does not receive the key.

## 4. Run and review

```sh
python3 -B launch.py --workspace --port 8982
```

Open `http://127.0.0.1:8982/`. Generation happens only after clicking the update
button. Before each subsequent call, obtain new genuine credit evidence after
the preceding call and update only `work/control/credit.json` accordingly. Use
the connection refresh button to recheck it. An unknown-cost failure blocks
further dispatch. Do not delete or reset the ledger to bypass a block.

Local review, correction and download remain available when generation is
closed. The app does not silently switch models or use recorded text as a new
model response. Raw responses stay separate from later edits.

Official provider documentation:
[Quickstart](https://docs.tokenfactory.nebius.com/quickstart),
[billing](https://docs.tokenfactory.nebius.com/other-capabilities/billing-new).
