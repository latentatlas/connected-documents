"""Contract tests with explicitly fabricated model responses; no provider calls."""
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from .core import Store, body, digest, inspect, make_input
from .export import package
from experiments.cross_use_case_v1.cases import project
from experiments.cross_use_case_v1.engine import initial_state, source


class Workflow(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)
        self.store=Store(self.folder)

    def draft(self):
        rules,old,facts,*_=project()
        job=self.store.begin("project",1,{k:facts[k] for k in ("release_date","qa_signoff")},"tr")
        target=initial_state(rules,source(old["source_id"],2,facts))
        proposal={"action":"edit","reason":"FABRICATED CONTRACT TEST RESPONSE, NOT A MODEL RESULT.","edits":[
            {"artifact_id":d["artifact_id"],"body":body(d["blocks"]),"source_refs":[old["source_id"]]} for d in target["documents"]]}
        raw=json.dumps(proposal)
        self.store.finish("project",job["id"],raw=raw,usage={"done_reason":"stop","model":"fabricated-test-response"})
        return job,raw

    def test_review_export_restart_undo_chain(self):
        before=deepcopy(self.store.current("project")["state"])
        other=deepcopy(self.store.current("research"))
        with self.assertRaisesRegex(ValueError,"REVIEW_BEFORE_EXPORT"): package(self.store,"project",1)
        job,raw=self.draft()
        self.assertEqual(before,self.store.current("project")["state"])
        with self.assertRaisesRegex(ValueError,"EXPLICIT_REVIEW_REQUIRED"):
            self.store.accept("project",1,job["id"],False)
        self.store.accept("project",1,job["id"],True,"assistant_qa")
        saved=deepcopy(self.store.current("project")["state"])
        payload,manifest=package(self.store,"project",2)
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            for doc in saved["documents"]:
                self.assertEqual(archive.read(doc["artifact_id"]+".txt").decode(),doc["body"])
        self.assertEqual(manifest["reviewer"],"assistant_qa")
        self.assertEqual(other,self.store.current("research"))
        restarted=Store(self.folder)
        self.assertEqual(saved,restarted.current("project")["state"])
        restarted.undo("project",2)
        self.assertEqual(before,restarted.current("project")["state"])
        self.assertEqual(restarted.current("project")["revision"],3)
        record=json.loads((self.folder/"undone"/(job["id"]+".json")).read_text())
        self.assertEqual(record["job"]["raw_response"],raw)
        restarted.verify()

    def test_source_and_model_binding_reject_wrong_target(self):
        job,_=self.draft()
        self.store.discard("project",1,job["id"])
        job=self.store.begin("project",1,{"release_date":"2026-11-19","qa_signoff":"2026-11-17"},"en")
        raw=json.dumps({"action":"edit","reason":"test","edits":[{"artifact_id":"research-note","body":"wrong target","source_refs":["release-decision-a"]}]})
        self.store.finish("project",job["id"],raw=raw,usage={"done_reason":"stop"})
        self.assertEqual(self.store.current("project")["pending"]["status"],"blocked")
        self.assertEqual(self.store.current("project")["revision"],1)
        self.assertEqual(self.store.current("project")["pending"]["raw_response"],raw)

    def test_bad_input_never_dispatches_or_changes_audit(self):
        before=digest(self.store.value)
        for facts in ({"release_date":"2026-11-01","qa_signoff":"2026-11-17"},
                      {"release_date":"2026-11-19","qa_signoff":"2026-11-17","other":1}):
            with self.assertRaises(ValueError): self.store.begin("project",1,facts,"tr")
        for facts in ({"passed":45,"total":40},{"passed":1,"total":0},{"passed":True,"total":40}):
            with self.assertRaises(ValueError): self.store.begin("research",1,facts,"tr")
        self.assertEqual(before,digest(self.store.value))

    def test_decision_check_handles_case_without_accepting_opposite(self):
        from experiments.cross_use_case_v1.cases import research
        rules,old,facts,*_=research()
        state=initial_state(rules,source(old["source_id"],2,facts))
        w=self.store.current("research");draft=deepcopy(w["state"])
        for doc,target in zip(draft["documents"],state["documents"]):
            doc["body"]=body(target["blocks"]).replace("threshold is not met","threshold is NOT met")
            doc["body_sha256"]=digest(doc["body"])
        self.assertTrue(all(c["passed"] for c in inspect(w,draft,facts)))
        draft["documents"][0]["body"]=draft["documents"][0]["body"].replace("threshold is NOT met","threshold is met")
        self.assertFalse(next(c["passed"] for c in inspect(w,draft,facts) if c["name"]=="decision:research-note"))

    def test_scoped_choices_share_one_validated_event_contract(self):
        from experiments.continuous_transfer_v1.design import validate_events, resolved_view
        work=deepcopy(self.store.current("volunteer"))
        first,transition,_=make_input(work,{"venue":"Cedar Hall","registration":"paper"})
        known,revoked=validate_events(first["user_feedback_chronological"])
        self.assertEqual(len(known),2);self.assertEqual(revoked,set())
        self.assertTrue(any("https://example.invalid/volunteer/consent.pdf" in r["text"] for r in first["sources"]+first["user_feedback_chronological"]))
        selected=resolved_view(work["state"],first["user_feedback_chronological"])
        self.assertIn("Printed signed consent",next(x["active_value"] for x in selected["scopes"] if x["scope"]=={"project_id":"volunteer-onboarding","audience":"participants"}))
        work.update(transition)
        second,_,_=make_input(work,{"venue":"Cedar Hall","registration":"phone"})
        known,revoked=validate_events(second["user_feedback_chronological"])
        self.assertEqual(revoked,{"event-ui-decision-2"})
        selected=resolved_view(work["state"],second["user_feedback_chronological"])
        self.assertIn("Phone-friendly",next(x["active_value"] for x in selected["scopes"] if x["scope"]=={"project_id":"volunteer-onboarding","audience":"participants"}))
        # resolved_view is a contract oracle here; it is NOT supplied to the model.
        self.assertNotIn("resolved_preference_view",first)
        broken=deepcopy(self.store.current("volunteer"));broken["sources"]=[]
        with self.assertRaisesRegex(ValueError,"MISSING_REGISTRATION_LINK_SOURCE"):
            make_input(broken,{"venue":"Cedar Hall","registration":"phone"})

    def test_manual_repair_preserves_native_response(self):
        job,raw=self.draft()
        w=self.store.current("project");bodies={d["artifact_id"]:d["body"] for d in w["pending"]["draft"]["documents"]}
        good=deepcopy(bodies)
        bodies["project-brief"]=bodies["project-brief"].replace("Offline mode is excluded.","Offline mode is included.")
        self.store.edit("project",1,job["id"],bodies)
        with self.assertRaisesRegex(ValueError,"DRAFT_CHECKS_FAILED"):
            self.store.accept("project",1,job["id"],True)
        self.store.edit("project",1,job["id"],good)
        self.store.accept("project",1,job["id"],True,"assistant_qa")
        record=self.store.current("project")["history"][-1]
        self.assertEqual(record["job"]["raw_response"],raw)
        self.assertEqual(record["job"]["manual_edits"],2)
        self.assertEqual(record["reviewer"],"assistant_qa")

    def test_stale_and_cross_job_requests_fail(self):
        job,_=self.draft()
        with self.assertRaisesRegex(ValueError,"STALE_WORKSPACE"):
            self.store.accept("project",0,job["id"],True)
        with self.assertRaisesRegex(ValueError,"DRAFT_IDENTITY"):
            self.store.accept("project",1,"different-job",True)
        self.store.accept("project",1,job["id"],True,"assistant_qa")
        with self.assertRaisesRegex(ValueError,"STALE_WORKSPACE"):
            package(self.store,"project",1)

    def test_restart_running_job_interrupts_without_retry(self):
        job=self.store.begin("project",1,{"release_date":"2026-11-19","qa_signoff":"2026-11-17"},"tr")
        with self.assertRaisesRegex(ValueError,"MODEL_BUSY"):
            self.store.begin("research",1,{"passed":26,"total":40},"tr")
        restarted=Store(self.folder)
        self.assertEqual(restarted.current("project")["pending"]["status"],"interrupted")
        self.assertFalse((self.folder/"calls").exists())
        restarted.discard("project",1,job["id"])
        self.assertTrue((self.folder/"discarded"/(job["id"]+".json")).exists())
        restarted.verify()

    def test_audit_catches_mutation_and_failed_write_stops_reads(self):
        self.draft()
        self.store.current("project")["facts"]["release_date"]="2026-12-01"
        with self.assertRaisesRegex(ValueError,"WORKSPACE_AUDIT_BINDING"): self.store.view()
        fresh=Store(self.folder)
        with patch("connected_work.core.atomic",side_effect=OSError("test disk failure")):
            with self.assertRaises(OSError): fresh.discard("project",1,fresh.current("project")["pending"]["id"])
        # The first write in discard is the archive; the main store remains intact.
        self.assertEqual(fresh.current("project")["revision"],1)
        job=fresh.current("project")["pending"]
        with patch("connected_work.core.atomic",side_effect=OSError("test disk failure")):
            with self.assertRaises(OSError): fresh.accept("project",1,job["id"],True,"assistant_qa")
        with self.assertRaisesRegex(ValueError,"STORE_WRITE_FAILED_RESTART_REQUIRED"): fresh.view()


if __name__=="__main__": unittest.main()
