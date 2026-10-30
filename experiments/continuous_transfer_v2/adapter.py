"""Bind write metadata in the host; never guess or override stale model values."""
from copy import deepcopy

from experiments.cross_use_case_v1.engine import digest, exact, require
from experiments.thesis_transfer_v1.adapter import assess, decode, propose, schema as original_schema, validate_input


def schema(data):
    result = deepcopy(original_schema(data))
    item = result["properties"]["edits"]["items"]
    for field in ("expected_version", "before_sha256"):
        item["required"].remove(field)
        del item["properties"][field]
    return result


def bind_proposal(data, proposal, current_state):
    validate_input(data)
    require(digest(current_state) == data["state_sha256"], "STALE_REQUEST_SNAPSHOT")
    exact(proposal, ("action", "reason", "edits"), "ACTION_SHAPE")
    require(isinstance(proposal["edits"], list), "EDITS_TYPE")
    documents = {doc["artifact_id"]: doc for doc in data["state"]["documents"]}
    bound = deepcopy(proposal)
    for edit in bound["edits"]:
        # Supplying version fields is an error under this new contract. There is
        # no branch that silently fixes a malformed old-contract response.
        exact(edit, ("artifact_id", "body", "source_refs"), "BOUND_EDIT_SHAPE")
        ident = edit["artifact_id"]
        require(isinstance(ident, str) and ident in documents, "EDIT_IDENTITY")
        original = documents[ident]
        edit["expected_version"] = original["version"]
        edit["before_sha256"] = original["body_sha256"]
    return bound


def evaluate(case, raw, finish_reason, current_state):
    try:
        require(finish_reason == "stop", "INCOMPLETE_MODEL_COMPLETION")
        native = decode(raw)
        bound = bind_proposal(case["input"], native, current_state)
        receipt = propose(case["input"], bound)
        return {"structural_status": "accepted_as_review_draft", "assessment": assess(case, bound, receipt),
                "proposal": native, "host_bound_proposal": bound, "receipt": receipt,
                "metadata_binding": {"origin": "exact_saved_request_snapshot",
                                     "current_state_sha256": digest(current_state),
                                     "native_proposal_sha256": digest(native),
                                     "host_bound_proposal_sha256": digest(bound)},
                "semantic_review": "pending", "manual_response_edits": 0, "production_approved": False}
    except (ValueError, TypeError, KeyError, AttributeError) as error:
        return {"structural_status": "rejected", "error": str(error), "semantic_review": "not_accepted",
                "manual_response_edits": 0, "production_approved": False}
