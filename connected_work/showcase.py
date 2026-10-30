"""Build a public-safe, read-only projection of verified fictional native calls.

No provider access or workspace mutation. Original, native and reviewed text
remain distinct. This is a recorded walkthrough, never a live inference claim.
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import zipfile

from .core import digest, require
from .nebius_provider import MODEL
from .verify import verify
from .review_context import explain

CASES = (
    ("project-release", "project", "5c5a448da96e459bbdd7327f04beea7f"),
    ("research-corrected", "research", "b9115341bd414b1f87e50f59b7b10ee5"),
    ("volunteer-paper", "volunteer", "c958104444684213afd29760691d1f1c"),
    ("volunteer-revoke", "volunteer", "241bc3468bda41e6924b06cbca09c559"),
    ("research-noop", "research", "f3d7348b9c514178b2cde480fb17e48d"),
)
PACKETS = tuple(case[0]+".zip" for case in CASES if case[0] != "research-noop")


def project_case(key, work_id, job, row, reviewer):
    require({case[0]: case[1] for case in CASES}.get(key) == work_id, "CASE_IDENTITY")
    require(row["job_id"] == job["id"] and row["work"] == work_id, "CASE_IDENTITY")
    require(job["provider"] == "nebius_token_factory" and job["usage"]["model"] == MODEL,
            "SHOWCASE_PROVIDER_IDENTITY")
    require(job["status"] == "needs_review", "SHOWCASE_REVIEWABLE_RESULT_REQUIRED")
    before = job["input"]["state"]
    native = job["receipt"]["draft_state"]
    accepted = job["draft"]
    require(before["package_id"] == native["package_id"] == accepted["package_id"], "PACKAGE_IDENTITY")
    before_ids = [doc["artifact_id"] for doc in before["documents"]]
    require(before_ids == [doc["artifact_id"] for doc in native["documents"]]
            == [doc["artifact_id"] for doc in accepted["documents"]], "DOCUMENT_IDENTITY")
    documents = []
    for old, proposed, saved in zip(before["documents"], native["documents"], accepted["documents"]):
        for doc in (old, proposed, saved):
            # A packet can contain a protected document belonging to another project.
            # Bind each document to its own original identity, never to the packet label.
            require(doc["project_id"] == old["project_id"] and doc.get("audience") == old.get("audience")
                    and doc["body_sha256"] == digest(doc["body"]),
                    "DOCUMENT_CONTENT_BINDING")
        documents.append({"id": old["artifact_id"], "title": old["title"], "project_id": old["project_id"],
            "before": old["body"], "native": proposed["body"], "saved": saved["body"],
            "changed": old["body"] != proposed["body"], "repaired": proposed["body"] != saved["body"],
            "before_sha256": old["body_sha256"], "native_sha256": proposed["body_sha256"],
            "saved_sha256": saved["body_sha256"]})
    require(bool(job["manual_edits"]) == any(d["repaired"] for d in documents), "REPAIR_DISCLOSURE")
    require(row["disposition"] == ("discarded" if key == "research-noop" else "accepted"), "DISPOSITION")
    return {"id": key, "work": work_id, "job_id": job["id"], "model": MODEL,
        "provider": job["provider"], "contract": row["provider_contract"],
        "reasoning_enabled": row["provider_contract"] == "nebius_documents_v3_reasoning",
        "completed_at": job["finished_at"], "action": job["proposal"]["action"],
        "manual_edit_rounds": job["manual_edits"], "reviewer": reviewer,
        "changed_documents": sum(d["changed"] for d in documents),
        "repaired_documents": sum(d["repaired"] for d in documents),
        "checks_passed": sum(c["passed"] for c in row["native_checks"]),
        "checks_total": len(row["native_checks"]), "disposition": row["disposition"],
        "request_sha256": row["request_sha256"], "native_response_sha256": row["native_response_sha256"],
        "documents": documents, "packet": None if key == "research-noop" else key+".zip"}


def build(evidence, output):
    evidence, output = Path(evidence), Path(output)
    report = verify(evidence)  # fail before exporting anything if identity/provenance is broken
    require(report["verified_external_calls"] == 11 and report["models"] == [MODEL], "SHOWCASE_EVIDENCE_SCOPE")
    value = json.loads((evidence/"workspace.json").read_text())
    rows = {row["job_id"]: row for row in report["rows"]}
    jobs = {}
    for work in value["works"].values():
        for record in work["history"]:
            jobs[record["job"]["id"]] = (record["job"], record["reviewer"])
    for path in (evidence/"discarded").glob("*.json"):
        job = json.loads(path.read_text())
        jobs[job["id"]] = (job, None)
    cases = [project_case(key, work, jobs[ident][0], rows[ident], jobs[ident][1])
             for key, work, ident in CASES]
    for case in cases:
        job = jobs[case["job_id"]][0]
        case["review_context"] = explain(case["work"], job["input"], job["transition"]["facts"], job["receipt"]["draft_state"], "recorded")
    # Keep every negative outcome visible. The examples are a selection, not a success denominator.
    overview = []
    for row in report["rows"]:
        job = jobs[row["job_id"]][0]
        outcome = ("blocked" if row["status"] != "needs_review" else
                   "repaired" if row["operator_edit_rounds"] else
                   "unchanged" if row["native_action"] == "noop" else "accepted_without_edits")
        overview.append({"job_id": row["job_id"], "work": row["work"], "outcome": outcome,
            "contract": row["provider_contract"], "completed_at": job["finished_at"],
            "manual_edit_rounds": row["operator_edit_rounds"], "disposition": row["disposition"]})
    overview.sort(key=lambda r: r["completed_at"])
    result = {"kind": "recorded_native_fictional_walkthrough", "live_inference": False, "workspace_url": "/",
        "human_trials": 0, "independent_validation": False, "cases": cases, "all_calls": overview,
        "evidence_workspace_sha256": hashlib.sha256((evidence/"workspace.json").read_bytes()).hexdigest(),
        "verified_external_calls": report["verified_external_calls"], "audit_events": report["audit_events"]}
    output.mkdir(parents=True, exist_ok=True)
    packets = output/"example-packets"
    packets.mkdir(exist_ok=True)
    for case in cases:
        if not case["packet"]:
            continue
        manifest = {k: deepcopy(case[k]) for k in ("id", "job_id", "provider", "model", "contract",
            "reviewer", "manual_edit_rounds", "request_sha256", "native_response_sha256")}
        manifest.update(kind="recorded_accepted_fictional_packet", new_model_call=False,
            human_benefit_measured=False, files=[{"path": d["id"]+".txt", "body_sha256": d["saved_sha256"]}
                                               for d in case["documents"]])
        with zipfile.ZipFile(packets/case["packet"], "w", zipfile.ZIP_DEFLATED) as z:
            for doc in case["documents"]:
                z.writestr(doc["id"]+".txt", doc["saved"])
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2)+"\n")
            z.writestr("READ_ME.txt", "Recorded fictional example; no new model call.\n"
                "These are the accepted texts, which may include the separately disclosed assistant corrections.\n"
                "Assistant QA is not independent human review. No human productivity benefit is measured.\n")
    (output/"examples.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", default="work/connected-work-nebius-v2-2026-10-30/evidence-snapshot")
    parser.add_argument("--output", default="connected_work/site")
    args = parser.parse_args()
    result = build(args.evidence, args.output)
    print(json.dumps({"examples": len(result["cases"]), "verified_calls": result["verified_external_calls"],
                      "new_model_calls": 0, "human_trials": 0}))
