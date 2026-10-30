"""Read-only integrity checks for the supplied release; no provider calls."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent


def require(condition, code):
    if not condition:
        raise ValueError(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def verify(root=ROOT):
    root = Path(root)
    manifest = json.loads((root / "RELEASE_MANIFEST.json").read_text())
    for name, expected in manifest["files"].items():
        path = root / name
        require(path.resolve().is_relative_to(root.resolve()) and path.is_file(), "MANIFEST_PATH")
        require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, "FILE_CHANGED:" + name)
    value = json.loads((root / "walkthrough/examples.json").read_text())
    require(value["kind"] == "recorded_native_fictional_walkthrough" and value["live_inference"] is False,
            "RECORDED_MODE")
    require(value["human_trials"] == 0 and value["independent_validation"] is False, "EVIDENCE_SCOPE")
    calls = {c["job_id"]: c for c in value["all_calls"]}
    require(len(calls) == len(value["all_calls"]) == value["verified_external_calls"] == 11, "CALL_IDENTITIES")
    counts = Counter(c["outcome"] for c in calls.values())
    require(counts == {"accepted_without_edits": 4, "repaired": 3, "blocked": 2, "unchanged": 2}, "OUTCOME_COUNTS")
    require({c["id"] for c in value["cases"]} == {"project-release", "research-corrected", "volunteer-paper", "volunteer-revoke", "research-noop"}, "CASE_IDENTITIES")
    require(len(value["cases"]) == 5, "CASE_COUNT")
    documents = 0
    exported = 0
    packets = []
    for case in value["cases"]:
        require(case["job_id"] in calls and calls[case["job_id"]]["work"] == case["work"], "CALL_WORK_BINDING")
        require(case["model"] == "nvidia/nemotron-3-super-120b-a12b" and case["provider"] == "nebius_token_factory", "PROVIDER_IDENTITY")
        ids = [d["id"] for d in case["documents"]]
        require(len(ids) == len(set(ids)), "DOCUMENT_IDENTITY")
        for doc in case["documents"]:
            for state in ("before", "native", "saved"):
                require(digest(doc[state]) == doc[state + "_sha256"], "DOCUMENT_CONTENT_BINDING")
            require(doc["changed"] == (doc["before"] != doc["native"]), "CHANGE_LABEL")
            require(doc["repaired"] == (doc["native"] != doc["saved"]), "REPAIR_LABEL")
            documents += 1
        require(case["changed_documents"] == sum(d["changed"] for d in case["documents"]), "CHANGE_COUNT")
        require(case["repaired_documents"] == sum(d["repaired"] for d in case["documents"]), "REPAIR_COUNT")
        if case["action"] == "noop":
            require(case["packet"] is None and all(d["before"] == d["native"] == d["saved"] for d in case["documents"]), "NOOP_CHANGED_CONTENT")
        if case["packet"]:
            require(Path(case["packet"]).name == case["packet"] and case["disposition"] == "accepted", "ACCEPTED_PACKET_REQUIRED")
            packets.append(case["packet"])
            with zipfile.ZipFile(root / "walkthrough/example-packets" / case["packet"]) as archive:
                names = [d["id"] + ".txt" for d in case["documents"]]
                require(set(archive.namelist()) == set(names + ["manifest.json", "READ_ME.txt"]), "PACKET_FILES")
                require(len(archive.namelist()) == len(names) + 2, "DUPLICATE_PACKET_FILES")
                meta = json.loads(archive.read("manifest.json"))
                for key in ("id", "job_id", "provider", "model", "contract", "reviewer", "manual_edit_rounds", "request_sha256", "native_response_sha256"):
                    require(meta[key] == case[key], "PACKET_IDENTITY")
                require(meta["new_model_call"] is False and meta["human_benefit_measured"] is False, "PACKET_SCOPE")
                require(meta["files"] == [{"path": d["id"] + ".txt", "body_sha256": d["saved_sha256"]} for d in case["documents"]], "PACKET_MANIFEST")
                for doc in case["documents"]:
                    require(archive.read(doc["id"] + ".txt").decode() == doc["saved"], "EXPORTED_TEXT_CHANGED")
                    exported += 1
    require(len(packets) == 4 and exported == 14 and documents == 17, "PROJECTION_SCOPE")
    revoked = next(c for c in value["cases"] if c["id"] == "volunteer-revoke")
    require(revoked["manual_edit_rounds"] == 1 and revoked["repaired_documents"] == 2
            and revoked["checks_passed"] == revoked["checks_total"] == 9, "SEMANTIC_FAILURE_DISCLOSURE")
    review = json.loads((root / "judge-build/review-data.json").read_text())
    require(review["kind"] == "recorded_review_build_v1" and review["new_provider_calls"] is False,
            "JUDGE_RECORDED_MODE")
    require(len(review["cases"]) == 5, "JUDGE_CASE_COUNT")
    original = {c["id"]: c for c in value["cases"]}
    require({c["id"] for c in review["cases"]} == set(original), "JUDGE_CASE_IDENTITIES")
    for case in review["cases"]:
        reference = original[case["id"]]
        require(all(case.get(key) == expected for key, expected in reference.items()),
                "JUDGE_NATIVE_RECORD_CHANGED")
        require(isinstance(case["package_id"], str) and case["package_id"], "JUDGE_PACKAGE_ID")
        require(isinstance(case["facts"], dict) and isinstance(case["protected"], dict), "JUDGE_FACT_SCHEMA")
    require((root / "judge-build/examples.json").read_bytes() == (root / "walkthrough/examples.json").read_bytes(),
            "JUDGE_EVIDENCE_CHANGED")
    return {"status": "passed", "files_verified": len(manifest["files"]), "historical_outcomes": dict(counts),
            "examples": 5, "document_views": documents, "accepted_packets": len(packets), "exported_documents": exported,
            "recorded_judge_cases": 5, "new_provider_calls": 0,
            "provider_call_independently_attested": False, "human_benefit_established": False}


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
