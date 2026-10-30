"""Persistent review workflow using existing, host-bound edit contracts.

Only fictional starter projects are supported. Structural/anchor checks never
replace explicit content review. No production publication.
"""
from copy import deepcopy
from datetime import date, timedelta, datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
import uuid

from experiments.cross_use_case_v1.engine import digest, require, initial_state
from experiments.cross_use_case_v1.cases import project, research
from experiments.continuous_transfer_v2.adapter import bind_proposal, schema
from experiments.thesis_transfer_v1.adapter import decode, propose, validate_input
from experiments.continuous_transfer_v2.design import SYSTEM
from experiments.continuous_transfer_v1.design import fixtures, event as preference_event, validate_events

TITLES = {"project": "Proje teslimi", "research": "Araştırma raporu", "volunteer": "Gönüllü katılımı"}
CHECK_VERSION = "anchor_checks_v2_case_insensitive_decision"


def stamp():
    return datetime.now(timezone.utc).isoformat()


def source(ident, text, version=1):
    return {"source_id": ident, "text": text, "version": version, "sha256": digest(text)}


def body(blocks):
    return "\n\n".join(f"{key.upper()}:\n{value}" for key, value in blocks.items())


def starters():
    work = {}
    for kind, factory in (("project", project), ("research", research)):
        rules, original, *_ = factory()
        state = initial_state(rules, original)
        documents, protected = [], {}
        for doc in state["documents"]:
            text = body(doc["blocks"])
            documents.append({"artifact_id": doc["artifact_id"], "title": doc["title"],
                              "project_id": state["package_id"], "audience": "project-team",
                              "version": 1, "body": text, "body_sha256": digest(text)})
            dynamic = {"timeline", "qa", "launch", "instruction", "finding", "decision"}
            protected[doc["artifact_id"]] = [value for key, value in doc["blocks"].items() if key not in dynamic]
        work[kind] = {"id": kind, "title": TITLES[kind], "state": {"schema": 1, "package_id": state["package_id"], "documents": documents},
                      "facts": original["facts"], "source_id": original["source_id"], "source_version": 1,
                      "protected": protected, "events": [], "history": [], "pending": None, "revision": 1}
    fixture = fixtures()
    state = deepcopy(fixture["initial_state"])
    work["volunteer"] = {"id": "volunteer", "title": TITLES["volunteer"], "state": state,
        "facts": {"venue": "Cedar Hall", "registration": "phone"}, "source_id": "volunteer-source",
        "source_version": 1, "sources": fixture["sources"], "events": [fixture["events"][0]],
        "protected": {doc["artifact_id"]: [doc["body"]] for doc in state["documents"]
                      if doc["artifact_id"] in ("coordinator-checklist", "workshop-invite")},
        "history": [], "pending": None, "revision": 1}
    return work


def facts_for(work, incoming):
    require(isinstance(incoming, dict), "FACTS_REQUIRED")
    facts = deepcopy(work["facts"])
    if work["id"] == "project":
        require(set(incoming) == {"release_date", "qa_signoff"}, "UNKNOWN_FIELD")
        dates = {key: date.fromisoformat(value) for key, value in incoming.items()}
        require(dates["qa_signoff"] <= dates["release_date"], "RELEASE_BEFORE_QA")
        require(all(2020 <= d.year <= 2040 for d in dates.values()), "DATE_RANGE")
        facts.update({key: value.isoformat() for key, value in dates.items()})
    elif work["id"] == "research":
        require(set(incoming) == {"passed", "total"}, "UNKNOWN_FIELD")
        require(all(type(v) is int for v in incoming.values()), "INTEGER_REQUIRED")
        require(1 <= incoming["total"] <= 100000 and 0 <= incoming["passed"] <= incoming["total"], "INVALID_COUNTS")
        facts.update(incoming)
    else:
        require(set(incoming) == {"venue", "registration"}, "UNKNOWN_FIELD")
        require(incoming["venue"] in ("Cedar Hall", "North Hall", "South Hall"), "UNKNOWN_VENUE")
        require(incoming["registration"] in ("phone", "paper"), "UNKNOWN_POLICY")
        facts.update(incoming)
    return facts


def make_input(work, incoming, language="tr"):
    facts = facts_for(work, incoming)
    version = work["source_version"] + (facts != work["facts"])
    events = deepcopy(work["events"])
    if work["id"] == "project":
        text = (f"Author-confirmed fictional project facts: {json.dumps(facts, sort_keys=True)}. "
                "QA starts three calendar days before sign-off. Keep scope, ownership and exclusions unchanged.")
        sources = [source(work["source_id"], text, version)]
        task = "Bring this project's connected documents up to date with the confirmed facts. Preserve every correct section and exact section headings. Do not send the handoff."
    elif work["id"] == "research":
        text = (f"Author-confirmed corrected fictional results for this SAME cohort: {json.dumps(facts, sort_keys=True)}. "
                "The authored continuation threshold is 75%. Compute the percentage to one decimal place and update the conclusion. Method and limitations are unchanged.")
        sources = [source(work["source_id"], text, version)]
        task = "Update the findings and their continuation decisions across the three existing documents. Preserve method, limitations and exact section headings. This is fictional descriptive evidence, not observed user productivity."
    else:
        sources = deepcopy(work["sources"])
        for record in sources:
            if record["source_id"] == "s-venue":
                record.update(source("s-venue", f"Confirmed fictional volunteer orientation: 2026-11-03 at 10:00 in {facts['venue']}. Duration 45 minutes. No prior experience is required.", version))
        if facts["registration"] != work["facts"]["registration"]:
            text = ("For volunteer-onboarding participants ONLY, require printed signed consent from https://example.invalid/volunteer/consent.pdf; mobile RSVP is optional and cannot replace paper consent. Other projects and operator paperwork retain their current policies."
                    if facts["registration"] == "paper" else
                    "Revoke the volunteer-onboarding paper-consent exception. Restore the phone-friendly default with mobile RSVP and no required participant printing. Keep other projects and internal coordinator paperwork unchanged.")
            sequence=len(events)+1
            record=source(f"ui-decision-{sequence}",text)
            if facts["registration"] == "paper":
                events.append(preference_event(record,sequence,"set","volunteer-onboarding",
                    "Printed signed consent is required; mobile RSVP is optional and does not replace paper consent."))
            else:
                known,revoked=validate_events(events)
                active=[e for key,e in known.items() if key not in revoked and e["decision"]["operation"]=="set"
                        and e["decision"]["scope"]["project_id"]=="volunteer-onboarding"]
                require(bool(active),"PREFERENCE_EXCEPTION_NOT_FOUND")
                events.append(preference_event(record,sequence,"revoke","volunteer-onboarding",
                    target=active[-1]["decision"]["event_id"]))
        validate_events(events)
        expected_url="https://example.invalid/volunteer/"+("consent.pdf" if facts["registration"]=="paper" else "rsvp")
        require(any(expected_url in record["text"] for record in sources+events),"MISSING_REGISTRATION_LINK_SOURCE")
        task = "Reconcile the four supplied documents with the current sources and the complete chronological decisions. Apply the latest volunteer-only decision; preserve unrelated work."
    data = {"task": task, "input_contract_version":"connected_work_v3_complete_scoped_decision_sources",
            "state": deepcopy(work["state"]), "state_sha256": digest(work["state"]),
            "sources": sources, "user_feedback_chronological": events}
    validate_input(data)
    return data, {"facts": facts, "source_version": version, "events": events}, language


def request(data, model, language):
    instruction = SYSTEM + ("\nWrite your brief reason in Turkish. Keep document bodies in their original English." if language == "tr" else "\nWrite your reason and documents in English.")
    return {"model": model, "messages": [{"role": "system", "content": instruction},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False, sort_keys=True)}],
            "format": schema(data), "think": False, "stream": True,
            "options": {"temperature": 0, "seed": 17, "num_ctx": 12288, "num_predict": 2300}, "keep_alive": "5m"}


def inspect(work, draft, facts):
    checks = []
    old = {d["artifact_id"]: d for d in work["state"]["documents"]}
    new = {d["artifact_id"]: d for d in draft["documents"]}
    def check(name, passed, detail):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})
    check("identity", set(old) == set(new) and work["state"]["package_id"] == draft["package_id"], "Belge ve proje kimlikleri aynı.")
    if set(old) != set(new):
        return checks
    for ident, snippets in work["protected"].items():
        intact = new[ident] == old[ident] if work["id"] == "volunteer" else all(s in new[ident]["body"] for s in snippets)
        check("protected:"+ident, intact, "Korunacak içerik: "+old[ident]["title"])
    if work["id"] == "project":
        release, qa = facts["release_date"], facts["qa_signoff"]
        start = (date.fromisoformat(qa)-timedelta(days=3)).isoformat()
        for ident in new:
            check("dates:"+ident, release in new[ident]["body"] and qa in new[ident]["body"], "Güncel teslim ve kalite tarihleri: "+new[ident]["title"])
            allowed = {release, qa} | ({start} if ident == "work-plan" else set())
            check("date_set:"+ident, set(re.findall(r"\d{4}-\d{2}-\d{2}",new[ident]["body"])) == allowed, "Belgede eski veya ek bir tarih kalmadı.")
        check("qa_start", start in new["work-plan"]["body"], "Kalite başlangıcı: "+start)
    elif work["id"] == "research":
        rate = f"{100*facts['passed']/facts['total']:.1f}%"
        for ident, doc in new.items():
            check("counts:"+ident, all(re.search(r"(?<!\d)"+str(facts[k])+r"(?!\d)",doc["body"]) for k in ("passed","total")) and rate in doc["body"], "Sayı ve yüzde dayanağı: "+rate)
            expected = "threshold is met" if facts["passed"]*100 >= facts["total"]*75 else "threshold is not met"
            decision = doc["body"].partition("DECISION:\n")[2].split("\n\n", 1)[0].casefold()
            opposite = "threshold is not met" if expected == "threshold is met" else "threshold is met"
            check("decision:"+ident, expected in decision and opposite not in decision, "Tanımlı %75 eşiği ile kararın eşleşmesi.")
    else:
        for ident in ("volunteer-message", "volunteer-faq"):
            value = new[ident]["body"]
            check("venue:"+ident, all(v in value for v in (facts["venue"],"2026-11-03","10:00","45")), "Mekân, gün, saat ve süre: "+new[ident]["title"])
            check("old_venue:"+ident, all(v not in value for v in ("North Hall","Cedar Hall","South Hall") if v != facts["venue"]), "Katılımcı belgesinde başka mekân kalmadı.")
            url = "https://example.invalid/volunteer/"+("consent.pdf" if facts["registration"]=="paper" else "rsvp")
            check("link:"+ident, url in value, "Seçilen kayıt yolunun bağlantısı. Zorunluluk/isteğe bağlılık anlamı ayrıca okunmalı.")
    return checks


def atomic(path, value):
    path = Path(path)
    tmp = path.with_name(path.name+".tmp")
    with tmp.open("w", encoding="utf8") as file:
        json.dump(value, file, ensure_ascii=False, indent=2)
        file.write("\n"); file.flush(); os.fsync(file.fileno())
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    descriptor = os.open(str(path.parent), os.O_RDONLY)
    try: os.fsync(descriptor)
    finally: os.close(descriptor)


class Store:
    def __init__(self, folder):
        self.folder = Path(folder); self.folder.mkdir(parents=True, exist_ok=True)
        self.path = self.folder/"workspace.json"; self.lock = threading.RLock(); self.poisoned = False
        if not self.path.exists():
            atomic(self.path, {"schema": 1, "kind": "fictional_development_workspace", "works": starters(), "audit": []})
        self.value = json.loads(self.path.read_text())
        self.verify()
        # A lost process cannot silently repeat an already dispatched request.
        for work in self.value["works"].values():
            if work["pending"] and work["pending"]["status"] == "running":
                work["pending"].update(status="interrupted", error="PROCESS_RESTART_NO_RETRY")
                self.record(work, "interrupted", {"job_id": work["pending"]["id"]})

    def verify(self):
        require(not self.poisoned, "STORE_WRITE_FAILED_RESTART_REQUIRED")
        require(self.value["schema"]==1 and self.value["kind"]=="fictional_development_workspace", "STORE_IDENTITY")
        require(set(self.value["works"])==set(TITLES), "WORK_IDENTITIES")
        prev = None; latest = {}
        for sequence, event in enumerate(self.value["audit"], 1):
            require(event["sequence"]==sequence and event["previous"]==prev and event["sha256"]==digest({k:v for k,v in event.items() if k!="sha256"}), "AUDIT_CHAIN")
            prev=event["sha256"]
            latest[event["work_id"]] = event
        for key, work in self.value["works"].items():
            require(work["id"]==key, "WORK_IDENTITY")
            validate_input({"state":work["state"],"state_sha256":digest(work["state"]),"sources":[],"user_feedback_chronological":[]})
            if key in latest:
                require(latest[key]["workspace_sha256"]==digest(work), "WORKSPACE_AUDIT_BINDING")

    def record(self, work, action, detail):
        events=self.value["audit"]
        event={"sequence":len(events)+1,"at":stamp(),"work_id":work["id"],"action":action,"detail":detail,
               "revision":work["revision"],"state_sha256":digest(work["state"]),"workspace_sha256":digest(work),"previous":events[-1]["sha256"] if events else None}
        event["sha256"]=digest(event);events.append(event)
        try: atomic(self.path,self.value)
        except OSError:
            self.poisoned=True
            raise

    def current(self, ident, revision=None):
        require(not self.poisoned,"STORE_WRITE_FAILED_RESTART_REQUIRED")
        require(ident in self.value["works"], "UNKNOWN_PROJECT")
        work=self.value["works"][ident]
        if revision is not None: require(type(revision) is int and work["revision"]==revision,"STALE_WORKSPACE")
        return work

    def view(self):
        with self.lock:
            self.verify()
            return deepcopy({"kind": self.value["kind"],"works":self.value["works"],"audit_count":len(self.value["audit"]),
                             "human_benefit_measured":False})

    def begin(self, ident, revision, facts, language, provider="local_ollama", provider_contract=None):
        with self.lock:
            work=self.current(ident,revision)
            require(not work["pending"],"REVIEW_OR_DISCARD_EXISTING_DRAFT")
            require(not any(w["pending"] and w["pending"]["status"]=="running" for w in self.value["works"].values()),"MODEL_BUSY")
            require(language in ("tr","en"),"LANGUAGE")
            require(provider in ("local_ollama","nebius_token_factory"),"PROVIDER_IDENTITY")
            data, transition, language=make_input(work,facts,language)
            job={"id":uuid.uuid4().hex,"status":"running","started_at":stamp(),"input":data,"transition":transition,
                 "base_revision":revision,"reason":None,"checks":[],"language":language,"provider":provider,"manual_edits":0}
            if provider_contract is not None: job["provider_contract"]=provider_contract
            work["pending"]=job;self.record(work,"generation_started",{"job_id":job["id"],"input_sha256":digest(data)})
            return deepcopy(job)

    def finish(self, ident, job_id, raw=None, usage=None, error=None):
        with self.lock:
            work=self.current(ident); job=work["pending"]
            require(job and job["id"]==job_id and job["status"]=="running","JOB_IDENTITY")
            job["finished_at"]=stamp();job["usage"]=usage
            if raw is not None: job["raw_response"]=raw
            try:
                require(error is None, error or "MODEL_ERROR")
                if job["provider"] == "nebius_token_factory":
                    require(usage.get("provider") == job["provider"] and usage.get("external_calls") == 1,
                            "PROVIDER_RESPONSE_IDENTITY")
                require(usage["done_reason"]=="stop","INCOMPLETE_MODEL_RESPONSE")
                native=decode(raw);bound=bind_proposal(job["input"],native,work["state"]);receipt=propose(job["input"],bound)
                job.update(status="needs_review",proposal=native,draft=receipt["draft_state"],reason=native["reason"],receipt=receipt,
                           checks=inspect(work,receipt["draft_state"],job["transition"]["facts"]),check_version=CHECK_VERSION)
            except (ValueError,TypeError,KeyError,AttributeError) as exc:
                job.update(status="blocked",error=str(exc) if re.fullmatch(r"[A-Z_]+",str(exc)) else "INVALID_MODEL_RESULT")
            self.record(work,"generation_finished",{"job_id":job_id,"status":job["status"],"raw_sha256":digest(raw),"usage":usage})

    def recheck(self, ident, revision, job_id):
        with self.lock:
            work=self.current(ident,revision);job=work["pending"]
            require(job and job["id"]==job_id and job["status"]=="needs_review","DRAFT_IDENTITY")
            job.setdefault("previous_checks",[]).append({"version":job.get("check_version","anchor_checks_v1"),"checks":deepcopy(job["checks"])})
            job.update(checks=inspect(work,job["draft"],job["transition"]["facts"]),check_version=CHECK_VERSION)
            self.record(work,"draft_rechecked",{"job_id":job_id,"check_version":CHECK_VERSION,"draft_unchanged":True})

    def edit(self, ident, revision, job_id, bodies):
        with self.lock:
            work=self.current(ident,revision);job=work["pending"]
            require(job and job["id"]==job_id and job["status"]=="needs_review","DRAFT_IDENTITY")
            require(isinstance(bodies,dict) and set(bodies)=={d["artifact_id"] for d in work["state"]["documents"]},"DOCUMENT_IDENTITY")
            proposal={"action":"noop","reason":"Explicit operator draft edit; raw model output is retained.","edits":[]}
            refs=[r["source_id"] for r in job["input"]["sources"]+job["input"]["user_feedback_chronological"]]
            for doc in work["state"]["documents"]:
                if bodies[doc["artifact_id"]]!=doc["body"]:
                    proposal["edits"].append({"artifact_id":doc["artifact_id"],"body":bodies[doc["artifact_id"]],"source_refs":refs})
            if proposal["edits"]: proposal["action"]="edit"
            receipt=propose(job["input"],bind_proposal(job["input"],proposal,work["state"]))
            job.setdefault("previous_checks",[]).append({"version":job.get("check_version"),
                "phase":"before_operator_edit","checks":deepcopy(job["checks"])})
            job.update(draft=receipt["draft_state"],operator_proposal=proposal,checks=inspect(work,receipt["draft_state"],job["transition"]["facts"]),check_version=CHECK_VERSION,manual_edits=job["manual_edits"]+1)
            self.record(work,"operator_draft_edit",{"job_id":job_id,"draft_sha256":digest(job["draft"]),"edit_rounds":job["manual_edits"]})

    def accept(self, ident, revision, job_id, reviewed, reviewer="operator_ui"):
        with self.lock:
            work=self.current(ident,revision);job=work["pending"]
            require(reviewed is True and reviewer in ("operator_ui","assistant_qa"),"EXPLICIT_REVIEW_REQUIRED")
            require(job and job["id"]==job_id and job["status"]=="needs_review","DRAFT_IDENTITY")
            require(job["input"]["state_sha256"]==digest(work["state"]),"STALE_DRAFT")
            require(job["proposal"]["action"]!="ask" or "operator_proposal" in job,"CLARIFICATION_REQUIRED")
            require(all(c["passed"] for c in inspect(work,job["draft"],job["transition"]["facts"])),"DRAFT_CHECKS_FAILED")
            before={k:deepcopy(work[k]) for k in ("state","facts","source_version","events")}
            work["state"]=deepcopy(job["draft"]);work.update(deepcopy(job["transition"]));work["revision"]+=1
            work["history"].append({"before":before,"after_sha256":digest(work["state"]),"job":deepcopy(job),"reviewer":reviewer})
            work["pending"]=None
            self.record(work,"draft_accepted",{"job_id":job_id,"reviewer":reviewer,"manual_edits":job["manual_edits"],"new_revision":work["revision"]})

    def discard(self, ident, revision, job_id):
        with self.lock:
            work=self.current(ident,revision);job=work["pending"]
            require(job and job["id"]==job_id and job["status"]!="running","DRAFT_IDENTITY")
            folder=self.folder/"discarded";folder.mkdir(exist_ok=True);atomic(folder/(job_id+".json"),job)
            work["pending"]=None;self.record(work,"draft_discarded",{"job_id":job_id,"retained_record_sha256":digest(job)})

    def undo(self, ident, revision):
        with self.lock:
            work=self.current(ident,revision)
            require(not work["pending"] and work["history"],"NOTHING_TO_UNDO")
            history=work["history"][-1]
            require(digest(work["state"])==history["after_sha256"],"UNDO_STATE_CHANGED")
            old_revision=work["revision"]
            work.update(deepcopy(history["before"]));work["history"].pop();work["revision"]=old_revision+1
            archive=self.folder/"undone";archive.mkdir(exist_ok=True);atomic(archive/(history["job"]["id"]+".json"),history)
            self.record(work,"undo",{"job_id":history["job"]["id"],"restored_state_sha256":digest(work["state"])})
