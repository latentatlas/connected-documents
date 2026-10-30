# Connected Documents

**One confirmed change. Consistent documents. A review you control.**

Connected Documents is a working prototype for teams that repeat facts across
briefs, plans, handoffs and reports. NVIDIA Nemotron proposes document updates
through Nebius Token Factory. The application binds proposals to the selected
source and document identities, exposes changed and preserved text, and lets an
operator correct, accept, download or undo the packet.

Three prepared fictional workspaces demonstrate the same workflow: project
delivery, research reporting and volunteer onboarding. Arbitrary uploads and
discovery of unknown document relationships are not implemented. Field checks
cover defined dates, counts, links and protected text; correct meaning still
requires review.

## Try the recorded review build

Requirements: Python 3.11+ on macOS or Linux. No installation, account or API key.

```sh
python3 -B launch.py --judge --port 8984
```

Open [the test build](http://127.0.0.1:8984/), choose **Try a recorded proposal**,
then:

1. Read the confirmed facts and content to preserve.
2. Inspect every numbered document; edit the proposed text if necessary.
3. Confirm your review and accept the packet.
4. Download your accepted document files, or undo to restore the original packet.

This is a functioning **recorded review mode**, initialized from real historical
Nemotron responses. It makes no fresh inference request. The selected case,
document identities and allowed scope are fixed. The browser keeps your edits in
tab memory; download before refreshing if you want to retain them. No participant
answers, analytics or credentials are collected by the test build.

Try the volunteer revocation example: its original model response passed nine
field checks but retained obsolete optional-registration wording. The historical
assistant correction is explicitly separate and may be loaded into a new review.
The research no-change case lets you download a local copy; it does not alter the
historical record, which correctly produced no new accepted revision.

`judge-build/` can also be served at the root of a static site. The hosted version
includes a separately packaged source ZIP at `downloads/connected-documents-source.zip`.
The local launcher serves that path by packaging only manifest-listed files after
integrity verification. It never exports local runtime, credentials or extra files.
Stop the local server with Ctrl-C.

## Inspect the historical evidence

The test build links to an evidence page with all eleven historical outcomes,
five selected examples, original versus accepted text, and four historical ZIPs.
Alternatively, run the original read-only walkthrough:

```sh
python3 -B launch.py --port 8981
```

Open [the evidence walkthrough](http://127.0.0.1:8981/?lang=en). It makes no model
call and does not let visitors change the historical record.

## Run fresh Nemotron generation

The separate Python product runtime can generate a new proposal. Complete
[LIVE_SETUP.md](LIVE_SETUP.md) in a fresh copy **before the first workspace launch**.
Then start:

```sh
python3 -B launch.py --workspace --port 8982
```

Open [the workspace](http://127.0.0.1:8982/). Select a prepared work type, enter the
confirmed fictional change, generate, inspect every document, correct the draft,
confirm review, and accept. Export contains accepted text; undo restores the prior
accepted packet. The runtime keeps local source, proposal, review and audit state.

The model is `nvidia/nemotron-3-super-120b-a12b`, called at
`https://api.tokenfactory.nebius.com/v1/chat/completions`. The current request
contract enables reasoning and requests JSON. This uses Python's standard library,
not the OpenAI SDK, and does not require an OpenAI API key.

Without operator credentials, matching account authorization and fresh credit and
price evidence, new generation stays blocked. A saved or fabricated response is
never substituted for a failed live request. An unconfigured launch still provides
source preview and document navigation; preserve it and use a fresh extracted copy
if configuring live generation later. The browser test build does not expose the
operator's paid API account.

## What the evidence supports

All eleven historical native outcomes are represented in the public projection:
four accepted without text edits, three accepted after assistant correction, two
blocked identical-text proposals, and two no-change responses. Five examples expose
17 document views and four accepted packets containing 14 document files.

These are authored development checks. They demonstrate linked updates,
preservation, review, file output and failure handling. They do **not** establish a
general success rate, independent reliability, reduced human checking, fewer user
errors or comparative time savings. The private participant studies are excluded.
The Turkish study instrument in the source is separate from the product demo.

The nine-check revocation failure remains visible because auditability is useful
only if the original error and the correction are distinguishable. Neither the
model nor the field checks make the final acceptance decision.

## Verify offline

```sh
python3 -B verify_release.py
python3 -B -m unittest discover -s connected_work -t . -v
python3 -B -m unittest test_release_setup -v
node judge-tests/test-review.mjs
```

Node.js 18+ is required only for the browser engine tests. They check 23 field-check
variants against saved Python results, five review flows, identity and scope guards,
acceptance, exact export text and undo. Temporary test exports are removed on exit.
The Python tests use synthetic responses; no test above sends inference requests.

The integrity verifier checks the distribution manifest, projected document bodies,
accepted ZIP texts, all eleven outcome identities and the recorded test build's
bindings. This verifies internal integrity, not independent provider attestation.
Original private native receipts were replayed before packaging; account/credit
evidence, credentials, participant data and raw model reasoning are excluded.

## Code map

| Location | Purpose |
|---|---|
| `connected_work/core.py` | Source/document identity, proposal state, review, audit and undo |
| `connected_work/nebius_provider.py` | Nemotron transport, scope, durable usage reservations and native replay |
| `connected_work/server.py` | Loopback API, request boundaries and accepted-only export |
| `connected_work/review_context.py` | Source excerpts, derived facts and preservation guidance |
| `connected_work/site/` | Bilingual live product UI and separate study instrument |
| `connected_work/showcase.py` | Public projection from verified private fictional evidence |
| `execution/nebius_guard/budget.py` | Durable accounting and evidence checks |
| `experiments/` | Source, decision and identity helpers used by the product |
| `judge-build/` | Browser review test build using recorded proposals |
| `judge-tests/` | Offline browser-engine checks and Python parity fixtures |
| `walkthrough/` | Unchanged read-only historical examples and accepted packets |

## Source, demo and license

[Source repository](https://github.com/latentatlas/connected-documents) ·
[Recorded review test build](https://connected-documents-latentatlas.hushed-ant-4642.chatgpt.site/)

MIT License, copyright 2026 Huseyin Buldurgan. See [LICENSE](LICENSE). This license
covers the original application source; it does not change model or service terms.
The hackathon entry is being prepared separately; public source does not mean the
entry has been submitted.

Only fictional data belongs in the prototype. The Python runtime is a local,
single-operator application, not a multi-tenant service. Live generation transmits
its selected fictional source/document snapshot to Nebius. Keep credentials and
private evidence in ignored local storage. See [LIVE_SETUP.md](LIVE_SETUP.md) and
[RELEASE_CHANGES.txt](RELEASE_CHANGES.txt).
