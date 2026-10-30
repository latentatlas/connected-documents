"""Projection contract tests; fabricated data only, no provider calls."""
from copy import deepcopy
import unittest

from .core import digest
from .showcase import MODEL, project_case


class Showcase(unittest.TestCase):
    def example(self):
        def state(body):
            return {"package_id": "example", "documents": [{"artifact_id": "invitation",
                "title": "Fictional invitation", "project_id": "example", "version": 1,
                "body": body, "body_sha256": digest(body)}]}
        job = {"id": "test-job", "provider": "nebius_token_factory", "usage": {"model": MODEL},
            "status": "needs_review", "input": {"state": state("before")},
            "receipt": {"draft_state": state("native optional")}, "draft": state("reviewed correction"),
            "manual_edits": 1, "finished_at": "2026-10-30T00:00:00Z", "proposal": {"action": "edit"}}
        row = {"job_id": "test-job", "work": "volunteer", "disposition": "accepted",
            "provider_contract": "nebius_documents_v1", "native_checks": [{"passed": True}],
            "request_sha256": "request-hash", "native_response_sha256": "response-hash"}
        return job, row

    def test_native_text_and_correction_are_separate_even_when_checks_pass(self):
        job, row = self.example()
        job["raw_response"] = "PRIVATE_TEST_MARKER_NOT_FOR_BROWSER"
        result = project_case("volunteer-revoke", "volunteer", job, row, "assistant_qa")
        self.assertEqual(result["documents"][0]["native"], "native optional")
        self.assertEqual(result["documents"][0]["saved"], "reviewed correction")
        self.assertEqual(result["repaired_documents"], 1)
        self.assertEqual(result["checks_passed"], 1)
        self.assertNotIn("PRIVATE_TEST_MARKER_NOT_FOR_BROWSER", str(result))
        self.assertFalse(result["reasoning_enabled"])

    def test_wrong_work_or_package_is_rejected(self):
        job, row = self.example()
        with self.assertRaisesRegex(ValueError, "CASE_IDENTITY"):
            project_case("volunteer-revoke", "research", job, row, "assistant_qa")
        job["draft"]["package_id"] = "wrong"
        with self.assertRaisesRegex(ValueError, "PACKAGE_IDENTITY"):
            project_case("volunteer-revoke", "volunteer", job, row, "assistant_qa")

    def test_text_tampering_or_hidden_correction_is_rejected(self):
        job, row = self.example()
        bad = deepcopy(job);bad["draft"]["documents"][0]["body"] = "tampered"
        with self.assertRaisesRegex(ValueError, "DOCUMENT_CONTENT_BINDING"):
            project_case("volunteer-revoke", "volunteer", bad, row, "assistant_qa")
        job["manual_edits"] = 0
        with self.assertRaisesRegex(ValueError, "REPAIR_DISCLOSURE"):
            project_case("volunteer-revoke", "volunteer", job, row, "assistant_qa")

    def test_discarded_noop_is_preserved_without_claiming_new_acceptance(self):
        job, row = self.example();job["draft"] = deepcopy(job["input"]["state"])
        job["receipt"]["draft_state"] = deepcopy(job["input"]["state"])
        job["manual_edits"] = 0;job["proposal"]["action"] = "noop";row["disposition"] = "discarded";row["work"] = "research"
        result = project_case("research-noop", "research", job, row, None)
        self.assertEqual(result["changed_documents"], 0)
        self.assertEqual(result["disposition"], "discarded")
        self.assertIsNone(result["packet"])
        self.assertIsNone(result["reviewer"])

    def test_protected_other_project_keeps_its_own_identity(self):
        job, row = self.example()
        for state in (job["input"]["state"], job["receipt"]["draft_state"], job["draft"]):
            state["documents"].append({"artifact_id": "other-invite", "title": "Another project",
                "project_id": "another-project", "body": "protected", "body_sha256": digest("protected")})
        result = project_case("volunteer-revoke", "volunteer", job, row, "assistant_qa")
        self.assertEqual(result["documents"][1]["project_id"], "another-project")
        self.assertFalse(result["documents"][1]["changed"])
        job["draft"]["documents"][1]["project_id"] = "example"
        with self.assertRaisesRegex(ValueError, "DOCUMENT_CONTENT_BINDING"):
            project_case("volunteer-revoke", "volunteer", job, row, "assistant_qa")


if __name__ == "__main__":
    unittest.main()
