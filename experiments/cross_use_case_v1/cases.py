"""Two authored development tasks; neither is held out or real customer data."""
from copy import deepcopy

from .engine import digest, initial_state, source


def fact(name):
    return {"op": "fact", "field": name}


def project():
    rules = {
        "schema": 1, "package_id": "synthetic-release-a",
        "fields": {"release_date": "date", "qa_signoff": "date", "scope": "text", "owner": "text"},
        "locked_fields": ["scope", "owner"],
        "bindings": {"release": fact("release_date"), "signoff": fact("qa_signoff"),
                     "qa_start": {"op": "date_offset", "field": "qa_signoff", "days": -3}},
        "constraints": [{"op": "le", "left": "qa_signoff", "right": "release_date",
                         "message": "Release precedes mandatory QA sign-off; a revised decision is required."}],
        "views": [
            {"artifact_id": "project-brief", "title": "Project brief", "blocks": {
                "purpose": "Prepare the fictional release of CSV export and saved filters.",
                "timeline": "Release: {release}. Mandatory QA sign-off: {signoff}.",
                "exclusions": "Offline mode is excluded. Do not add features or change ownership."}},
            {"artifact_id": "work-plan", "title": "Delivery work plan", "blocks": {
                "qa": "QA runs from {qa_start} through {signoff}, using a three-calendar-day lead-in.",
                "launch": "The release milestone is {release}, after QA sign-off.",
                "scope": "Deliver CSV export and saved filters. Release manager owns the launch decision."}},
            {"artifact_id": "handoff-note", "title": "Internal handoff note (unsent)", "blocks": {
                "instruction": "Prepare the handoff for {release}; obtain QA sign-off by {signoff}.",
                "ownership": "The release manager remains accountable. This draft sends no notification.",
                "exclusions": "Offline mode remains excluded."}},
        ],
    }
    facts = {"release_date": "2026-11-12", "qa_signoff": "2026-11-10",
             "scope": "CSV export and saved filters; offline mode excluded", "owner": "Release manager"}
    revised = facts | {"release_date": "2026-11-19", "qa_signoff": "2026-11-17"}
    invalid = facts | {"release_date": "2026-11-09"}
    request = (
        "The release decision was revised: QA sign-off is now 17 November and release is 19 November. "
        "Update my project brief, delivery work plan and internal handoff note consistently. "
        "QA begins three calendar days before sign-off. Preserve scope, exclusions and ownership. "
        "If release would precede QA sign-off, keep the current package and ask for a revised decision. "
        "Do not send the handoff note."
    )
    expected = {
        "project-brief": {"timeline": "Release: 2026-11-19. Mandatory QA sign-off: 2026-11-17."},
        "work-plan": {
            "qa": "QA runs from 2026-11-14 through 2026-11-17, using a three-calendar-day lead-in.",
            "launch": "The release milestone is 2026-11-19, after QA sign-off."},
        "handoff-note": {"instruction": "Prepare the handoff for 2026-11-19; obtain QA sign-off by 2026-11-17."},
    }
    return rules, source("release-decision-a", 1, facts), revised, invalid, request, expected


def research():
    rules = {
        "schema": 1, "package_id": "synthetic-research-a",
        "fields": {"passed": "integer", "total": "integer", "cohort": "text", "method": "text"},
        "locked_fields": ["cohort", "method"],
        "bindings": {
            "passed": fact("passed"), "total": fact("total"), "cohort": fact("cohort"),
            "rate": {"op": "percentage", "numerator": "passed", "denominator": "total"},
            "decision": {"op": "percentage_decision", "numerator": "passed", "denominator": "total",
                         "threshold": 75, "met": "The authored 75% pilot continuation threshold is met.",
                         "not_met": "The authored 75% pilot continuation threshold is not met; investigate before extending this pilot."},
        },
        "constraints": [
            {"op": "minimum", "field": "passed", "minimum": 0, "message": "Passed count cannot be negative."},
            {"op": "minimum", "field": "total", "minimum": 1, "message": "A positive task count is required."},
            {"op": "le", "left": "passed", "right": "total", "message": "Passed count exceeds the cohort size; resolve the source conflict."},
        ],
        "views": [
            {"artifact_id": "research-note", "title": "Research result note", "blocks": {
                "finding": "{cohort}: {passed}/{total} tasks passed ({rate}).",
                "decision": "{decision}",
                "method": "Fixed authored tasks, one local run, unchanged scoring rubric.",
                "limit": "This descriptive pilot result does not establish independent reliability, statistical significance or user time savings."}},
            {"artifact_id": "progress-brief", "title": "Research progress brief", "blocks": {
                "finding": "The corrected pilot record reports {rate}, from {passed} passing tasks out of {total} in {cohort}.",
                "decision": "{decision}",
                "limit": "Report the correction and keep the original result in the audit trail. No general superiority claim is supported."}},
            {"artifact_id": "presentation-notes", "title": "Presentation speaking notes", "blocks": {
                "finding": "Say: In our fictional {cohort}, {passed} of {total} tasks passed, a descriptive rate of {rate}.",
                "decision": "Say: {decision}",
                "limit": "Mention the fixed task set and single-run scope. Do not claim statistical significance or human productivity gains."}},
        ],
    }
    facts = {"passed": 32, "total": 40, "cohort": "October cohort A",
             "method": "Fixed authored tasks, one local run, unchanged scoring rubric"}
    revised = facts | {"passed": 26}
    invalid = facts | {"passed": 45}
    request = (
        "The source owner corrected the same October cohort A: 26 of 40 tasks passed, not 32. "
        "Update the result note, progress brief and presentation speaking notes, including the conclusion. "
        "Use the explicitly authored 75% pilot continuation threshold. Preserve method and limitations. "
        "A different cohort must not overwrite this one. Conflicting counts need a source clarification. "
        "Do not imply independent validation, statistical significance or human time savings."
    )
    decision = "The authored 75% pilot continuation threshold is not met; investigate before extending this pilot."
    expected = {
        "research-note": {"finding": "October cohort A: 26/40 tasks passed (65.0%).", "decision": decision},
        "progress-brief": {"finding": "The corrected pilot record reports 65.0%, from 26 passing tasks out of 40 in October cohort A.", "decision": decision},
        "presentation-notes": {"finding": "Say: In our fictional October cohort A, 26 of 40 tasks passed, a descriptive rate of 65.0%.", "decision": "Say: " + decision},
    }
    return rules, source("cohort-a-results", 1, facts), revised, invalid, request, expected


def suite():
    cases = []
    for name, builder in (("project", project), ("research", research)):
        rules, original, revised, invalid, request, expected = builder()
        before = initial_state(rules, original)
        for event_kind in ("revision", "same_values", "other_source", "conflict"):
            facts = revised if event_kind in ("revision", "other_source") else invalid if event_kind == "conflict" else original["facts"]
            incoming = source(original["source_id"] + "-other" if event_kind == "other_source" else original["source_id"],
                              1 if event_kind == "other_source" else 2, facts)
            event = {"schema": 1, "package_id": rules["package_id"], "before_state_sha256": digest(before),
                     "source": incoming, "revision_of": None if event_kind == "other_source" else
                     {key: original[key] for key in ("source_id", "version", "sha256")}}
            status = {"revision": "review_draft", "same_values": "source_only_review_draft",
                      "other_source": "needs_source_selection", "conflict": "needs_decision"}[event_kind]
            task = request if event_kind == "revision" else {
                "same_values": "The same source has a new verified revision with unchanged facts. Preserve all document content and document versions.",
                "other_source": "A different, unselected source arrived. Keep the active package intact and request explicit source selection; similar numbers or wording do not establish identity.",
                "conflict": "A same-source revision contains conflicting facts. Identify the conflict and preserve the active package until the source is clarified.",
            }[event_kind]
            cases.append({"case_id": name + "-" + event_kind, "domain": name,
                          "case_kind": "authored_development_fixture", "held_out": False,
                          "task": task, "rules": deepcopy(rules), "before": deepcopy(before), "event": event,
                          "expected_status": status, "expected_changes": deepcopy(expected) if event_kind == "revision" else {}})
    return cases
