"""Generic review-draft adapter. It does not decide which documents are relevant."""
from copy import deepcopy
import json

from experiments.cross_use_case_v1.engine import digest, exact, identifier, require


def validate_input(data):
    state = data["state"]
    require(data["state_sha256"] == digest(state), "INPUT_STATE_HASH")
    require(identifier(state["package_id"]), "PACKAGE_IDENTITY")
    ids = set()
    for document in state["documents"]:
        require(identifier(document["artifact_id"]) and document["artifact_id"] not in ids, "ARTIFACT_IDENTITY")
        ids.add(document["artifact_id"])
        require(type(document["version"]) is int and document["version"] > 0 and
                isinstance(document["body"], str) and document["body_sha256"] == digest(document["body"]), "ARTIFACT_BINDING")
    ids = set()
    for record in data["sources"] + data["user_feedback_chronological"]:
        require(identifier(record["source_id"]) and record["source_id"] not in ids, "SOURCE_IDENTITY")
        ids.add(record["source_id"])
        require(type(record["version"]) is int and record["version"] > 0 and
                isinstance(record["text"], str) and record["sha256"] == digest(record["text"]), "SOURCE_BINDING")


def schema(data):
    validate_input(data)
    source_ids = [item["source_id"] for item in data["sources"] + data["user_feedback_chronological"]]
    return {"type": "object", "additionalProperties": False, "required": ["action", "reason", "edits"],
            "properties": {
                "action": {"type": "string", "enum": ["edit", "noop", "ask"]},
                "reason": {"type": "string"},
                "edits": {"type": "array", "maxItems": len(data["state"]["documents"]), "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["artifact_id", "expected_version", "before_sha256", "body", "source_refs"],
                    "properties": {
                        "artifact_id": {"type": "string", "enum": [doc["artifact_id"] for doc in data["state"]["documents"]]},
                        "expected_version": {"type": "integer"}, "before_sha256": {"type": "string"},
                        "body": {"type": "string"},
                        "source_refs": {"type": "array", "minItems": 1, "items": {"type": "string", "enum": source_ids}},
                    }}}}}


def decode(raw):
    require(isinstance(raw, str) and 0 < len(raw) <= 50000, "RESPONSE_SIZE")
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, "DUPLICATE_KEY")
            out[key] = value
        return out
    def invalid(value):
        raise ValueError("NONFINITE_JSON")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def propose(data, proposal):
    validate_input(data)
    exact(proposal, ("action", "reason", "edits"), "ACTION_SHAPE")
    require(proposal["action"] in ("edit", "noop", "ask"), "ACTION")
    require(isinstance(proposal["reason"], str) and 0 < len(proposal["reason"].strip()) <= 4000, "REASON")
    edits = proposal["edits"]
    require(isinstance(edits, list) and (bool(edits) == (proposal["action"] == "edit")), "EDIT_ACTION")
    before = data["state"]
    draft = deepcopy(before)
    documents = {item["artifact_id"]: item for item in draft["documents"]}
    source_ids = {item["source_id"] for item in data["sources"] + data["user_feedback_chronological"]}
    seen = set()
    for edit in edits:
        exact(edit, ("artifact_id", "expected_version", "before_sha256", "body", "source_refs"), "EDIT_SHAPE")
        ident = edit["artifact_id"]
        require(isinstance(ident, str) and ident in documents and ident not in seen, "EDIT_IDENTITY")
        seen.add(ident)
        original = documents[ident]
        require(type(edit["expected_version"]) is int and edit["expected_version"] == original["version"] and
                edit["before_sha256"] == original["body_sha256"], "EDIT_VERSION_OR_HASH")
        require(isinstance(edit["body"], str) and 0 < len(edit["body"].strip()) <= 6000 and
                edit["body"] != original["body"], "EDIT_BODY")
        require(isinstance(edit["source_refs"], list) and bool(edit["source_refs"]) and
                all(isinstance(ref, str) and ref in source_ids for ref in edit["source_refs"]), "EDIT_REFERENCES")
        original.update(body=edit["body"], body_sha256=digest(edit["body"]), version=original["version"] + 1)
    changes = [{"artifact_id": old["artifact_id"], "before_sha256": digest(old), "after_sha256": digest(new),
                "version_before": old["version"], "version_after": new["version"]}
               for old, new in zip(before["documents"], draft["documents"]) if old != new]
    return {"status": "needs_content_review", "draft_state": draft, "changes": changes,
            "input_sha256": digest(data), "proposal_sha256": digest(proposal), "draft_sha256": digest(draft),
            "production_approved": False, "semantic_approved": False}


def assess(case, proposal, receipt):
    expected = case["expected"]
    before = {doc["artifact_id"]: doc for doc in case["input"]["state"]["documents"]}
    draft = {doc["artifact_id"]: doc for doc in receipt["draft_state"]["documents"]}
    changed = {ident for ident in before if before[ident] != draft[ident]}
    anchors = ("2026-11-03", "10:00", "Cedar Hall", "45")
    participants = ("volunteer-message", "volunteer-faq")
    expected_url = ("https://example.invalid/volunteer/rsvp" if expected["participant_mode"] == "phone"
                    else "https://example.invalid/volunteer/consent.pdf")
    checks = {
        "action": proposal["action"] == expected["action"],
        "affected_documents": changed == set(expected["changed_ids"]),
        "protected_documents": all(before[ident] == draft[ident] for ident in expected["protected_ids"]),
        "source_anchors": all(all(anchor in draft[ident]["body"] for anchor in anchors) and
                              "North Hall" not in draft[ident]["body"] and expected_url in draft[ident]["body"] for ident in participants),
        "latest_policy_cited": all(expected["latest_policy"] in edit["source_refs"] for edit in proposal["edits"]),
    }
    return {"checks": checks, "machine_checks_passed": all(checks.values()),
            "semantic_verdict": "needs_assistant_or_independent_review",
            "warning": "URL and anchor checks do not establish instruction meaning; read every full document."}
