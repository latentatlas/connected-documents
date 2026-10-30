"""Offline, review-only baseline for explicitly bound document updates.

The rules and dependencies are authored, not inferred. This is a deterministic
comparison arm, not an LLM agent or a claim of general-purpose understanding.
No source is promoted and no existing artifact is overwritten by this module.
"""
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import json
import re
from string import Formatter


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(value):
    raw = json.dumps(value, sort_keys=True, ensure_ascii=False,
                     separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def exact(value, keys, message):
    require(isinstance(value, dict) and set(value) == set(keys), message)


def identifier(value):
    return isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_-]{0,79}", value)


def source(source_id, version, facts):
    return {"source_id": source_id, "version": version,
            "facts": deepcopy(facts), "sha256": digest(facts)}


def validate_source(value):
    exact(value, ("source_id", "version", "facts", "sha256"), "SOURCE_SHAPE")
    require(identifier(value["source_id"]), "SOURCE_IDENTITY")
    require(type(value["version"]) is int and value["version"] > 0, "SOURCE_VERSION")
    require(isinstance(value["facts"], dict) and bool(value["facts"]), "SOURCE_FACTS")
    for key, item in value["facts"].items():
        require(identifier(key), "FACT_IDENTITY")
        require(type(item) is int or (isinstance(item, str) and 0 < len(item) <= 2000), "FACT_TYPE")
    require(value["sha256"] == digest(value["facts"]), "SOURCE_HASH")


def validate_rules(rules):
    exact(rules, ("schema", "package_id", "fields", "locked_fields", "bindings", "constraints", "views"), "RULES_SHAPE")
    require(type(rules["schema"]) is int and rules["schema"] == 1, "RULES_SCHEMA")
    require(identifier(rules["package_id"]), "PACKAGE_IDENTITY")
    require(isinstance(rules["fields"], dict) and bool(rules["fields"]), "FIELDS")
    require(all(identifier(k) and v in ("text", "date", "integer")
                for k, v in rules["fields"].items()), "FIELD_TYPE")
    require(isinstance(rules["locked_fields"], list) and
            len(set(rules["locked_fields"])) == len(rules["locked_fields"]) and
            all(key in rules["fields"] for key in rules["locked_fields"]), "LOCKED_FIELDS")
    require(isinstance(rules["bindings"], dict) and bool(rules["bindings"]), "BINDINGS")
    require(isinstance(rules["constraints"], list), "CONSTRAINTS")
    for name, expression in rules["bindings"].items():
        require(identifier(name) and isinstance(expression, dict), "BINDING_IDENTITY")
        op = expression.get("op")
        shapes = {"fact": ("op", "field"), "date_offset": ("op", "field", "days"),
                  "percentage": ("op", "numerator", "denominator"),
                  "percentage_decision": ("op", "numerator", "denominator", "threshold", "met", "not_met")}
        require(op in shapes, "UNSUPPORTED_EXPRESSION")
        exact(expression, shapes[op], "EXPRESSION_SHAPE")
        refs = [expression[k] for k in ("field", "numerator", "denominator") if k in expression]
        require(all(ref in rules["fields"] for ref in refs), "UNBOUND_FIELD")
        if op == "date_offset":
            require(rules["fields"][expression["field"]] == "date" and
                    type(expression["days"]) is int and abs(expression["days"]) <= 365, "DATE_OFFSET")
        if op in ("percentage", "percentage_decision"):
            require(all(rules["fields"][ref] == "integer" for ref in refs), "PERCENTAGE_FIELDS")
        if op == "percentage_decision":
            require(type(expression["threshold"]) is int and 0 <= expression["threshold"] <= 100,
                    "DECISION_THRESHOLD")
            require(all(isinstance(expression[k], str) and expression[k].strip()
                        for k in ("met", "not_met")), "DECISION_TEXT")
    for constraint in rules["constraints"]:
        require(isinstance(constraint, dict), "CONSTRAINT_SHAPE")
        if constraint.get("op") == "le":
            exact(constraint, ("op", "left", "right", "message"), "CONSTRAINT_SHAPE")
            left, right = constraint["left"], constraint["right"]
            require(left in rules["fields"] and right in rules["fields"] and
                    rules["fields"][left] == rules["fields"][right] and
                    rules["fields"][left] in ("date", "integer"), "CONSTRAINT_FIELDS")
        else:
            exact(constraint, ("op", "field", "minimum", "message"), "CONSTRAINT_SHAPE")
            require(constraint["op"] == "minimum" and constraint["field"] in rules["fields"] and
                    rules["fields"][constraint["field"]] == "integer" and
                    type(constraint["minimum"]) is int, "CONSTRAINT_FIELDS")
        require(isinstance(constraint["message"], str) and constraint["message"].strip(), "CONSTRAINT_MESSAGE")
    require(isinstance(rules["views"], list) and bool(rules["views"]), "VIEWS")
    seen = set()
    for view in rules["views"]:
        exact(view, ("artifact_id", "title", "blocks"), "VIEW_SHAPE")
        require(identifier(view["artifact_id"]) and view["artifact_id"] not in seen, "ARTIFACT_IDENTITY")
        seen.add(view["artifact_id"])
        require(isinstance(view["title"], str) and view["title"].strip(), "VIEW_TITLE")
        require(isinstance(view["blocks"], dict) and bool(view["blocks"]), "VIEW_BLOCKS")
        for block, template in view["blocks"].items():
            require(identifier(block) and isinstance(template, str) and template.strip(), "BLOCK")
            for _, name, spec, conversion in Formatter().parse(template):
                if name is not None:
                    require(name in rules["bindings"] and not spec and conversion is None, "TEMPLATE_BINDING")


def validate_facts(rules, facts):
    require(set(facts) == set(rules["fields"]), "FACT_SET")
    for name, kind in rules["fields"].items():
        value = facts[name]
        if kind == "integer":
            require(type(value) is int, "INTEGER_FACT")
        elif kind == "date":
            require(isinstance(value, str) and date.fromisoformat(value).isoformat() == value, "DATE_FACT")
        else:
            require(isinstance(value, str) and value.strip(), "TEXT_FACT")


def conflicts(rules, facts):
    issues = []
    for item in rules["constraints"]:
        ok = (facts[item["left"]] <= facts[item["right"]] if item["op"] == "le"
              else facts[item["field"]] >= item["minimum"])
        if not ok:
            issues.append(item["message"])
    return issues


def values(rules, facts):
    result = {}
    for name, expression in rules["bindings"].items():
        op = expression["op"]
        if op == "fact":
            value = facts[expression["field"]]
        elif op == "date_offset":
            value = (date.fromisoformat(facts[expression["field"]]) +
                     timedelta(days=expression["days"])).isoformat()
        else:
            denominator = facts[expression["denominator"]]
            require(denominator > 0, "INVALID_DENOMINATOR")
            percent = Decimal(facts[expression["numerator"]]) * 100 / Decimal(denominator)
            if op == "percentage":
                value = format(percent.quantize(Decimal("0.1")), "f") + "%"
            else:
                value = expression["met" if percent >= expression["threshold"] else "not_met"]
        result[name] = value
    return result


def render(rules, facts):
    bindings = values(rules, facts)
    return [{"artifact_id": view["artifact_id"], "title": view["title"], "version": 1,
             "blocks": {key: value.format_map(bindings) for key, value in view["blocks"].items()}}
            for view in rules["views"]]


def initial_state(rules, initial_source):
    validate_rules(rules)
    validate_source(initial_source)
    validate_facts(rules, initial_source["facts"])
    require(not conflicts(rules, initial_source["facts"]), "INITIAL_CONFLICT")
    return {"schema": 1, "package_id": rules["package_id"], "rules_sha256": digest(rules),
            "source": deepcopy(initial_source), "documents": render(rules, initial_source["facts"])}


def validate_state(rules, state):
    exact(state, ("schema", "package_id", "rules_sha256", "source", "documents"), "STATE_SHAPE")
    expected = initial_state(rules, state["source"])
    require(state["schema"] == 1 and type(state["schema"]) is int and
            state["package_id"] == rules["package_id"] and state["rules_sha256"] == digest(rules), "STATE_BINDING")
    require(isinstance(state["documents"], list) and len(state["documents"]) == len(expected["documents"]), "DOCUMENT_SET")
    for current, canonical in zip(state["documents"], expected["documents"]):
        require(type(current.get("version")) is int and current["version"] > 0, "ARTIFACT_VERSION")
        canonical["version"] = current["version"]
        require(current == canonical, "UNTRACKED_DOCUMENT_CHANGE")


def preview(rules, before, event):
    """Return a proposed state and receipt. Never approve or commit the state."""
    validate_state(rules, before)
    exact(event, ("schema", "package_id", "before_state_sha256", "source", "revision_of"), "EVENT_SHAPE")
    require(type(event["schema"]) is int and event["schema"] == 1, "EVENT_SCHEMA")
    require(identifier(event["package_id"]) and event["before_state_sha256"] == digest(before), "EVENT_STATE_BINDING")
    incoming = event["source"]
    validate_source(incoming)
    after = deepcopy(before)
    issues = []
    current = before["source"]
    if event["package_id"] != before["package_id"]:
        status = "out_of_scope"
    elif incoming["source_id"] != current["source_id"]:
        require(incoming["version"] == 1 and event["revision_of"] is None, "UNBOUND_NEW_SOURCE")
        status = "needs_source_selection"
    else:
        binding = {key: current[key] for key in ("source_id", "version", "sha256")}
        require(event["revision_of"] == binding and incoming["version"] == current["version"] + 1,
                "SOURCE_REVISION_BINDING")
        validate_facts(rules, incoming["facts"])
        issues = conflicts(rules, incoming["facts"])
        issues.extend("Changing protected field requires a reviewed rule revision: " + key
                      for key in rules["locked_fields"] if incoming["facts"][key] != current["facts"][key])
        if issues:
            status = "needs_decision"
        else:
            after["source"] = deepcopy(incoming)
            after["documents"] = render(rules, incoming["facts"])
            for old, new in zip(before["documents"], after["documents"]):
                new["version"] = old["version"] + (old["blocks"] != new["blocks"])
            status = ("review_draft" if after["documents"] != before["documents"]
                      else "source_only_review_draft")
    transitions = []
    for old, new in zip(before["documents"], after["documents"]):
        if old != new:
            transitions.append({"artifact_id": old["artifact_id"], "before_sha256": digest(old),
                                "after_sha256": digest(new), "version_before": old["version"],
                                "version_after": new["version"],
                                "blocks": [key for key in old["blocks"] if old["blocks"][key] != new["blocks"][key]]})
    return {"status": status, "draft_state": after, "issues": issues, "transitions": transitions,
            "before_sha256": digest(before), "event_sha256": digest(event), "draft_sha256": digest(after),
            "rules_sha256": digest(rules), "provider_calls": 0,
            "semantic_approved": False, "production_approved": False,
            "human_active_seconds": None, "time_savings_supported": False}
