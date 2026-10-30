"""Read-only replay of saved native responses. Does not call any model."""
from copy import deepcopy
import argparse
import json
from pathlib import Path

from .core import digest, inspect, request, require, validate_input
from .local_provider import MODEL, MODEL_DIGEST
from .nebius_provider import verify_call as verify_nebius
from experiments.continuous_transfer_v2.adapter import bind_proposal
from experiments.thesis_transfer_v1.adapter import decode, propose


def verify(folder):
    root=Path(folder);value=json.loads((root/"workspace.json").read_text())
    prev=None;latest={};rows=[]
    for index,event in enumerate(value["audit"],1):
        require(event["sequence"]==index and event["previous"]==prev,"AUDIT_SEQUENCE")
        require(event["sha256"]==digest({k:v for k,v in event.items() if k!="sha256"}),"AUDIT_HASH")
        prev=event["sha256"];latest[event["work_id"]]=event
    for ident,work in value["works"].items():
        if ident in latest: require(latest[ident]["workspace_sha256"]==digest(work),"WORKSPACE_AUDIT_BINDING")
        records=[(item["job"],item["reviewer"],item["after_sha256"],"accepted") for item in work["history"]]
        if work["pending"]: records.append((work["pending"],None,None,"pending"))
        for path in sorted((root/"discarded").glob("*.json")):
            archived=json.loads(path.read_text())
            if archived["input"]["state"]["package_id"]==work["state"]["package_id"]:
                records.append((archived,None,None,"discarded"))
        for path in sorted((root/"undone").glob("*.json")):
            archived=json.loads(path.read_text())
            if archived["job"]["input"]["state"]["package_id"]==work["state"]["package_id"]:
                records.append((archived["job"],archived["reviewer"],archived["after_sha256"],"undone"))
        for job,reviewer,after_hash,disposition in records:
            if job["status"]!="needs_review":
                row={"work":ident,"job_id":job["id"],"status":job["status"],"reviewer":reviewer,"disposition":disposition}
                if job["provider"]=="nebius_token_factory" and job.get("usage"):
                    verify_nebius(root/"calls"/job["id"],job)
                    reproduced=None
                    try:
                        native=decode(job["raw_response"])
                        propose(job["input"],bind_proposal(job["input"],native,job["input"]["state"]))
                    except ValueError as exc: reproduced=str(exc)
                    require(reproduced==job.get("error"),"APPLICATION_FAILURE_NOT_REPRODUCED")
                    row.update(provider=job["provider"],model=job["usage"]["model"],external_calls=1,
                        application_error=reproduced,provider_contract=job.get("provider_contract","nebius_documents_v1"),
                        native_checks_passed=False,operator_edit_rounds=job["manual_edits"],
                        model_seconds=job["usage"]["model_wall_seconds"])
                rows.append(row);continue
            validate_input(job["input"]);native=decode(job["raw_response"])
            require(native==job["proposal"],"NATIVE_PROPOSAL_CHANGED")
            receipt=propose(job["input"],bind_proposal(job["input"],native,job["input"]["state"]))
            require(receipt==job["receipt"],"NATIVE_RECEIPT_CHANGED")
            final=receipt
            if "operator_proposal" in job:
                final=propose(job["input"],bind_proposal(job["input"],job["operator_proposal"],job["input"]["state"]))
            require(final["draft_state"]==job["draft"],"FINAL_DRAFT_CHANGED")
            if after_hash: require(after_hash==digest(job["draft"]),"ACCEPTED_SNAPSHOT_CHANGED")
            folder=root/"calls"/job["id"]
            payload=json.loads((folder/"request.json").read_text());attempt=json.loads((folder/"attempt.json").read_text())
            require(digest(payload)==attempt["request_sha256"],"SAVED_REQUEST_CHANGED")
            response=json.loads((folder/"response.json").read_text())
            require(response=={"raw_content":job["raw_response"],"usage":job["usage"]},"RESPONSE_RECORD_CHANGED")
            if job["provider"] == "nebius_token_factory":
                verify_nebius(folder,job)
            else:
                require(job["provider"]=="local_ollama","PROVIDER_IDENTITY")
                require(payload==request(job["input"],MODEL,job["language"]),"REQUEST_REPLAY_MISMATCH")
                chunks=[json.loads(line) for line in (folder/"raw-stream.jsonl").read_text().splitlines() if line.strip()]
                require(chunks[-1].get("done") is True and chunks[-1].get("done_reason")=="stop","RAW_COMPLETION")
                require(all(chunk.get("model")==MODEL for chunk in chunks),"RAW_MODEL")
                require("".join(c.get("message",{}).get("content","") for c in chunks)==job["raw_response"],"RAW_TEXT_CHANGED")
                require(job["usage"]["model_digest"]==MODEL_DIGEST,"MODEL_DIGEST")
            context=deepcopy(work);context["state"]=job["input"]["state"]
            checks=inspect(context,job["draft"],job["transition"]["facts"])
            native_checks=inspect(context,receipt["draft_state"],job["transition"]["facts"])
            rows.append({"work":ident,"job_id":job["id"],"status":job["status"],"reviewer":reviewer,
                "disposition":disposition,"input_contract_version":job["input"].get("input_contract_version","connected_work_v1"),
                "provider":job["provider"],"model":job["usage"]["model"],
                "provider_contract":job.get("provider_contract","nebius_documents_v1" if job["provider"]=="nebius_token_factory" else "local_ollama_v1"),
                "external_calls":job["usage"].get("external_calls",0),
                "native_action":native["action"],"native_changed_documents":len(native["edits"]),
                "native_output_manually_edited":False,"operator_edit_rounds":job["manual_edits"],
                "native_checks_passed":all(c["passed"] for c in native_checks),"native_checks":native_checks,
                "current_checks_passed":all(c["passed"] for c in checks),"current_checks":checks,
                "initial_check_failures":[c["name"] for old in job.get("previous_checks",[]) for c in old["checks"] if not c["passed"]],
                "model_seconds":job["usage"]["model_wall_seconds"],"request_sha256":attempt["request_sha256"],
                "native_response_sha256":digest(job["raw_response"]),"reviewed_state_sha256":after_hash})
    models=sorted({row["model"] for row in rows if "model" in row})
    return {"kind":"native_workflow_qa","new_external_calls":0,"human_trials":0,
        "verified_external_calls":sum(row.get("external_calls",0) for row in rows),
        "causal_user_benefit_established":False,"models":models,
        "audit_events":len(value["audit"]),"audit_chain_verified":True,"rows":rows}


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("folder");args=parser.parse_args()
    print(json.dumps(verify(args.folder),ensure_ascii=False,indent=2))
