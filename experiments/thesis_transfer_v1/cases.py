"""Authored, independent state snapshots for a new volunteer-onboarding job.

Only input is sent to the actor. Expected answers are evaluator-only. The actor
sees previous user feedback in context; no durable memory/learning is tested.
"""
from copy import deepcopy
from experiments.cross_use_case_v1.engine import digest


MODEL = "qwen3.6-27b-q4-local:latest"
MODEL_DIGEST = "0004b3d1d08363b7305f94ca53c3a9a1bcb02e98430df0e0897dc23e8121fbc6"
SYSTEM = """You are preparing a fictional local document packet. Read the user's task,
authoritative source records and chronological prior user feedback. Determine
which current documents actually need edits. Apply feedback within its scope;
an explicit later exception or revocation governs that scope. Retain unrelated
documents, accurate facts and operator-only instructions. Do not invent facts,
publish anything or send messages. Document relationships are not supplied as
an edit map: decide from the contents, audience and project identities.

Return exactly the specified JSON action. Use edit for necessary complete-body
replacements only, noop if the packet is already correct, or ask if necessary
evidence is missing or contradictory. Do not perform gratuitous rewording. Copy
the supplied exact artifact ID, version and body hash for each replacement.
Explain the proposed action briefly and cite source IDs in each edit. Include
all required corrections in this single proposed action. This is a first-response
probe, not a comparison against another assistant. All proposals require review.
"""


def doc(ident, title, project, audience, version, body):
    return {"artifact_id": ident, "title": title, "project_id": project,
            "audience": audience, "version": version, "body": body, "body_sha256": digest(body)}


def source(ident, text):
    return {"source_id": ident, "version": 1, "text": text, "sha256": digest(text)}


def snapshot(mode, location="Cedar Hall"):
    instructions = {
        "old": "Print the registration sheet and bring it to check-in. Mobile registration is not available.",
        "phone": "Confirm attendance using https://example.invalid/volunteer/rsvp on your phone. No printing is required.",
        "paper": "Bring a printed, signed consent sheet from https://example.invalid/volunteer/consent.pdf. Mobile RSVP is optional and does not replace the signed paper sheet.",
    }[mode]
    return {"schema": 1, "package_id": "volunteer-onboarding",
            "documents": [
                doc("volunteer-message", "Volunteer welcome message (unsent)", "volunteer-onboarding", "participants", 3,
                    f"Welcome to volunteer orientation on 2026-11-03 at 10:00 in {location}. {instructions} Orientation lasts 45 minutes. No prior experience is required."),
                doc("volunteer-faq", "Volunteer orientation FAQ", "volunteer-onboarding", "participants", 2,
                    f"When and where? 2026-11-03, 10:00, {location}. How do I prepare? {instructions} How long is orientation? 45 minutes. Is experience required? No."),
                doc("coordinator-checklist", "Coordinator checklist", "volunteer-onboarding", "internal_operators", 5,
                    "The coordinator prints one attendance roster for internal check-in. Prepare the welcome desk and keep the roster with the coordinator. This operator-only roster is separate from participant registration."),
                doc("workshop-invite", "Separate workshop invitation (unsent)", "writing-workshop", "participants", 7,
                    "Writing workshop: 2026-11-06 at 14:00 in Elm Room. Confirm at https://example.invalid/workshop/rsvp on your phone. No printing is required. Bring your draft on your device."),
            ]}


def suite():
    global_feedback = source("p-global", "Earlier user feedback from workshop work: From now on, across my projects, participant-facing instructions must work on a phone and must not require printing. This remains my default until I change it. It does not apply to internal operator paperwork.")
    exception = source("p-exception", "Later user decision: For the volunteer orientation only, ask every participant to bring a printed, signed consent sheet from https://example.invalid/volunteer/consent.pdf. Mobile RSVP is optional and does not replace the paper consent. This is an exception for this project only; keep the phone-friendly default elsewhere.")
    revoke = source("p-revoke", "Latest user decision: Cancel the paper-consent exception for volunteer orientation. Restore registration through the mobile RSVP form, with no required printing for participants. Keep the confirmed venue, time and the internal coordinator roster unchanged.")
    facts = [
        source("s-venue", "Confirmed volunteer orientation: 2026-11-03 at 10:00 in Cedar Hall. Cedar Hall replaces North Hall. Duration remains 45 minutes; no prior experience is required."),
        source("s-rsvp", "The approved volunteer mobile RSVP form is https://example.invalid/volunteer/rsvp. It works on a phone. Whether it is required or optional follows the latest applicable user decision."),
        source("s-roster", "The coordinator must print one attendance roster for internal check-in. This is operator paperwork, separate from participant registration."),
    ]
    definitions = [
        ("transfer", snapshot("old", "North Hall"), [global_feedback], "phone", "edit",
         "Please prepare my volunteer onboarding packet using the confirmed sources and my previous feedback. Keep other projects intact."),
        ("exception", snapshot("phone"), [global_feedback, exception], "paper", "edit",
         "Please bring my volunteer onboarding packet into line with my latest decision. Keep other projects intact."),
        ("revocation", snapshot("paper"), [global_feedback, exception, revoke], "phone", "edit",
         "Please bring my volunteer onboarding packet into line with my latest decision. Keep other projects intact."),
        ("healthy", snapshot("phone"), [global_feedback, exception, revoke], "phone", "noop",
         "Please check my volunteer onboarding packet against the sources and latest decision. Make only necessary changes; if it is already correct, leave it intact."),
    ]
    cases = []
    for name, before, history, mode, action, task in definitions:
        cases.append({"case_id": name, "kind": "authored_development_snapshot", "held_out": False,
                      "input": {"task": task, "state": before, "state_sha256": digest(before),
                                "sources": deepcopy(facts), "user_feedback_chronological": deepcopy(history)},
                      "expected": {"action": action, "participant_mode": mode,
                                   "changed_ids": ["volunteer-message", "volunteer-faq"] if action == "edit" else [],
                                   "protected_ids": ["coordinator-checklist", "workshop-invite"],
                                   "latest_policy": history[-1]["source_id"]},
                      "healthy_reference": snapshot(mode)})
    return cases
