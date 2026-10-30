"""Authored fixtures and explicit preference events; no inferred user memory."""
from copy import deepcopy

from experiments.cross_use_case_v1.engine import digest, require
from experiments.thesis_transfer_v1.adapter import validate_input, schema
from experiments.thesis_transfer_v1.cases import MODEL, MODEL_DIGEST, suite


ARMS = ("full_history", "resolved_preferences")
STEPS = ("transfer", "exception", "revocation", "healthy")
SYSTEM = """You are a capable general work assistant maintaining a fictional document
packet. Read the task, authoritative sources, current documents and complete
stored user feedback. Later explicit scoped decisions override earlier defaults
within their scope; revoking an exception restores the remaining default.
The chronological preference records contain explicit authored user decisions,
not model-inferred rules. If a resolved preference view is present, it is a
deterministic convenience derived from those same records, not extra evidence.

Decide which documents need changes from their contents, audience and project.
Preserve accurate facts, unrelated projects and operator-only instructions.
Return the specified JSON: edit for necessary full-body replacements, noop for
an already correct packet, or ask for missing or contradictory evidence. Copy
the exact supplied artifact ID, version and body hash. Cite the source records
supporting each edit, including the applicable latest decision. Explain briefly.
Do not reword correct material gratuitously, invent facts, send or publish.
The current documents may contain earlier assistant mistakes; reconcile them
against the sources. All results remain unapproved review drafts.
"""


def event(record, sequence, operation, project, value=None, target=None):
    item = deepcopy(record)
    item["decision"] = {"event_id": "event-" + record["source_id"], "sequence": sequence,
                        "origin": "fictional_author_confirmed_fixture",
                        "operation": operation, "key": "participant_registration",
                        "scope": {"project_id": project, "audience": "participants"},
                        "value": value, "revokes_event_id": target}
    item["record_sha256"] = digest(item)
    return item


def fixtures():
    old = suite()
    history = old[2]["input"]["user_feedback_chronological"]
    events = [
        event(history[0], 1, "set", "*", "Phone-friendly participant instructions; no required printing."),
        event(history[1], 2, "set", "volunteer-onboarding",
              "Printed signed consent is required; mobile RSVP is optional and does not replace paper consent."),
        event(history[2], 3, "revoke", "volunteer-onboarding", target="event-p-exception"),
    ]
    return {"initial_state": old[0]["input"]["state"], "sources": old[0]["input"]["sources"],
            "events": events, "visible_event_counts": [1, 2, 3, 3],
            "tasks": [case["input"]["task"] for case in old],
            "expected": [case["expected"] for case in old],
            "reference_bodies": [case["healthy_reference"] for case in old],
            "origin": "reuse of known authored thesis_transfer_v1 case family; not held out"}


def validate_events(events):
    known = {}
    revoked = set()
    sources = set()
    for sequence, record in enumerate(events, 1):
        unsigned = {k: v for k, v in record.items() if k != "record_sha256"}
        require(record["record_sha256"] == digest(unsigned), "PREFERENCE_RECORD_BINDING")
        require(record["sha256"] == digest(record["text"]), "PREFERENCE_TEXT_BINDING")
        require(record["source_id"] not in sources, "DUPLICATE_PREFERENCE_SOURCE")
        sources.add(record["source_id"])
        decision = record["decision"]
        ident = decision["event_id"]
        require(ident not in known and decision["sequence"] == sequence, "PREFERENCE_EVENT_ORDER")
        require(decision["origin"] == "fictional_author_confirmed_fixture", "PREFERENCE_ORIGIN")
        require(decision["key"] == "participant_registration", "PREFERENCE_KEY")
        require(decision["scope"]["audience"] == "participants" and
                decision["scope"]["project_id"] in ("*", "volunteer-onboarding"), "PREFERENCE_SCOPE")
        if decision["operation"] == "set":
            require(isinstance(decision["value"], str) and bool(decision["value"]) and
                    decision["revokes_event_id"] is None, "PREFERENCE_SET")
        else:
            require(decision["operation"] == "revoke" and decision["value"] is None, "PREFERENCE_OPERATION")
            target = decision["revokes_event_id"]
            require(target in known and target not in revoked, "UNKNOWN_OR_REPEATED_REVOCATION")
            previous = known[target]["decision"]
            require(previous["operation"] == "set" and previous["scope"] == decision["scope"] and
                    previous["key"] == decision["key"], "REVOCATION_SCOPE")
            revoked.add(target)
        known[ident] = record
    return known, revoked


def resolved_view(state, events):
    known, revoked = validate_events(events)
    scopes = sorted({(doc["project_id"], doc["audience"]) for doc in state["documents"]})
    views = []
    for project, audience in scopes:
        applicable = [record for ident, record in known.items()
                      if ident not in revoked and record["decision"]["operation"] == "set" and
                      record["decision"]["scope"]["audience"] == audience and
                      record["decision"]["scope"]["project_id"] in ("*", project)]
        selected = max(applicable, key=lambda record: (record["decision"]["scope"]["project_id"] != "*",
                                                      record["decision"]["sequence"]), default=None)
        revocations = [record["source_id"] for record in events
                       if record["decision"]["operation"] == "revoke" and
                       record["decision"]["scope"] == {"project_id": project, "audience": audience}]
        views.append({"scope": {"project_id": project, "audience": audience},
                      "active_value": selected["decision"]["value"] if selected else None,
                      "active_source_id": selected["source_id"] if selected else None,
                      "revocation_source_ids": revocations})
    return {"derived_only_from_records_sha256": digest(events), "scopes": views}


def make_input(arm, state, events, fixture, step):
    require(arm in ARMS and step in range(4), "ARM_OR_STEP")
    require(events == fixture["events"][:fixture["visible_event_counts"][step]], "VISIBLE_EVENT_PREFIX")
    validate_events(events)
    data = {"task": fixture["tasks"][step], "state": deepcopy(state), "state_sha256": digest(state),
            "sources": deepcopy(fixture["sources"]), "user_feedback_chronological": deepcopy(events)}
    if arm == "resolved_preferences":
        data["resolved_preference_view"] = resolved_view(state, events)
    validate_input(data)
    return data


def request(data):
    import json
    return {"model": MODEL, "messages": [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False, sort_keys=True)}],
            "format": schema(data), "think": False, "stream": True,
            "options": {"temperature": 0, "seed": 17, "num_ctx": 8192, "num_predict": 1400},
            "keep_alive": "3m"}
