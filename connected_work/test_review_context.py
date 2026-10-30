from copy import deepcopy
import unittest
from .core import starters, make_input, digest
from .review_context import context_for, explain

class ReviewContext(unittest.TestCase):
    def test_live_preview_uses_bound_source_without_mutating_saved_facts(self):
        w=starters()["research"];before=digest(w)
        out=context_for(w,{"passed":33,"total":40})
        self.assertIn("82.5",out["calculations"][0][0])
        self.assertIn("karşılanıyor",out["calculations"][1][0])
        self.assertIn('"passed": 33',out["sources"][0]["text"])
        self.assertEqual(digest(w),before);self.assertFalse(out["semantic_correctness_confirmed"])

    def test_date_boundary_and_equal_threshold(self):
        out=context_for(starters()["project"],{"release_date":"2026-12-03","qa_signoff":"2026-12-01"})
        self.assertIn("2026-11-28",out["calculations"][0][0])
        out=context_for(starters()["research"],{"passed":3,"total":4})
        self.assertIn("karşılanıyor",out["calculations"][1][0])

    def test_other_project_identity_remains_distinct_and_protected(self):
        w=starters()["volunteer"];out=context_for(w)
        self.assertEqual([d["targeted"] for d in out["documents"]],[True,True,False,False])
        self.assertNotEqual(out["documents"][0]["project_id"],out["documents"][-1]["project_id"])
        inp,transition,_=make_input(w,w["facts"]);bad=deepcopy(w["state"])
        bad["documents"][-1]["project_id"]=bad["package_id"]
        with self.assertRaisesRegex(ValueError,"REVIEW_DOCUMENT_IDENTITY"):explain("volunteer",inp,transition["facts"],bad)

    def test_altered_snapshot_and_wrong_document_are_rejected(self):
        w=starters()["research"];inp,transition,_=make_input(w,{k:w["facts"][k] for k in ("passed","total")})
        bad=deepcopy(w["state"]);bad["documents"][0]["body"]="forged"
        with self.assertRaisesRegex(ValueError,"REVIEW_BODY_BINDING"):explain("research",inp,transition["facts"],bad)
        with self.assertRaisesRegex(ValueError,"REVIEW_DOCUMENT_IDENTITIES"):explain("project",inp,transition["facts"])

if __name__=="__main__":unittest.main()
