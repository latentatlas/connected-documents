from collections import Counter
from copy import deepcopy
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from .core import digest
from .review_trial import TrialStore,CATALOG,plan,score

class ReviewTrial(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.folder=Path(temp.name);self.clock=1000.
        self.store=TrialStore(self.folder,clock=lambda:self.clock)
        self.s=self.store.create("assistant_qa",True,"new")

    def cmd(self,action,**payload):
        self.s=self.store.command(self.s["id"],self.s["revision"],action,payload);return self.s

    def start(self):
        self.cmd("ready");self.cmd("start")

    def save_all(self,repair=False):
        f=CATALOG[self.s["fixture"]["id"]]
        for d in f["documents"]:
            self.cmd("save",case=f["id"],document=d["id"],answers={v["id"]:v["expected"] if repair else v["initial"] for v in d["fields"]},reviewed=True)

    def test_balanced_conditions_and_true_defect_opportunities(self):
        seen=Counter()
        for n in range(4):
            p=plan(n)
            self.assertEqual(len({r["case"] for r in p}),4)
            for condition in ("standard","assisted"):
                tasks=[CATALOG[r["case"]] for r in p if r["condition"]==condition]
                self.assertEqual({t["family"] for t in tasks},{"project","research"})
                self.assertEqual(sorted(t["initial_defects"] for t in tasks),[0,3])
            for r in p:seen[(r["case"],r["condition"])]+=1
        self.assertEqual(set(seen.values()),{2})
        for f in CATALOG.values():
            answers={v["id"]:v["initial"] for d in f["documents"] for v in d["fields"]}
            result=score(f,answers);self.assertEqual(result["remaining_initial_defects"],f["initial_defects"])
            if f["initial_defects"]:self.assertEqual((result["final_required_errors"],result["final_protected_errors"]),(2,1))

    def test_standard_has_equal_source_but_no_scoring_key_or_hidden_results(self):
        self.start();f=self.s["fixture"]
        self.assertEqual(f["sources"],CATALOG[f["id"]]["sources"])
        self.assertNotIn("initial_defects",f);self.assertNotIn("calculations",f)
        for d in f["documents"]:
            for field in d["fields"]:
                self.assertNotIn("expected",field);self.assertNotIn("matches",field)
        self.assertNotIn("results",self.s)
        with self.assertRaisesRegex(ValueError,"TRIAL_COMPLETE_BEFORE_EXPORT"):self.store.export(self.s["id"])
        for fixture in CATALOG.values():
            for doc in fixture["documents"]:
                for field in doc["fields"]:
                    if field["type"]=="decision":
                        self.assertEqual(len(field["options"]),2)
                        self.assertIn(field["initial"],field["options"])
                        self.assertIn(field["expected"],field["options"])

    def test_identity_stale_incomplete_and_cross_task_mutations_rejected(self):
        self.start();before=self.store.read(self.s["id"])
        with self.assertRaisesRegex(ValueError,"TRIAL_CASE_IDENTITY"):self.cmd("finish",case="research-a")
        with self.assertRaisesRegex(ValueError,"TRIAL_REVIEW_ALL_DOCUMENTS"):self.cmd("finish",case="project-a")
        with self.assertRaisesRegex(ValueError,"TRIAL_DOCUMENT_IDENTITY"):self.cmd("save",case="project-a",document="research-a-note",answers={},reviewed=True)
        with self.assertRaisesRegex(ValueError,"TRIAL_STALE_REVISION"):self.store.command(self.s["id"],1,"pause",{"case":"project-a"})
        self.assertEqual(before,self.store.read(self.s["id"]))

    def test_timing_excludes_pauses_hidden_gaps_and_marks_reload(self):
        self.clock+=8;self.start();self.assertEqual(self.s["onboarding_seconds"],8)
        self.clock+=15;self.cmd("activity",case="project-a",visible=False,reloaded=False)
        self.clock+=15;self.cmd("activity",case="project-a",visible=True,reloaded=False)
        self.clock+=5;self.cmd("pause",case="project-a")
        self.clock+=120;self.cmd("resume",case="project-a")
        self.clock+=60;self.cmd("activity",case="project-a",visible=True,reloaded=True)
        self.assertEqual(self.s["focus_seconds"],20)
        self.assertEqual(set(self.s["timing_flags"]),{"paused","unobserved_gap","reload"})

    def test_complete_save_restart_and_export_exact_answers_qa_excluded(self):
        self.start()
        for n in range(4):
            self.save_all(repair=n==0)
            self.cmd("finish",case=self.s["fixture"]["id"])
            self.assertNotIn("results",self.s)
            self.cmd("ratings",effort=3,ready="yes",help="none")
            if n<3:self.cmd("start")
        self.assertEqual(self.s["phase"],"complete");self.assertEqual(self.s["actor"],"assistant_qa")
        self.assertIn("insan denemesi veya fayda ölçümü değildir",self.s["claim"])
        self.assertEqual(self.s["results"][0]["result"]["final_wrong_fields"],0)
        self.assertEqual(self.s["results"][1]["result"]["final_wrong_fields"],3)
        restarted=TrialStore(self.folder,clock=lambda:self.clock)
        self.assertEqual(restarted.get(self.s["id"]),self.s)
        saved=restarted.read(self.s["id"])
        with zipfile.ZipFile(io.BytesIO(restarted.export(self.s["id"]))) as z:
            for row in saved["rounds"]:
                for doc in CATALOG[row["case"]]["documents"]:
                    expected="\n".join(v["label"]+": "+row["answers"][v["id"]] for v in doc["fields"])
                    self.assertEqual(z.read(row["case"]+"/"+doc["id"]+".txt").decode(),expected)
        # QA sessions never advance the participant sequence.
        self.assertEqual(self.store.create("participant",True,"new")["phase"],"onboarding")
        participants=[json.loads(p.read_text()) for p in self.folder.glob('*.json') if p.name!='protocol.json' and json.loads(p.read_text()).get('actor')=='participant']
        self.assertEqual(participants[0]["cohort"],0)
        self.assertTrue(any(e['detail'].get('changes') for e in saved['events']))

    def test_introduced_error_is_counted_and_not_hidden_by_fix(self):
        f=CATALOG["research-a"];answers={v["id"]:v["expected"] for d in f["documents"] for v in d["fields"]}
        answers["note.total"]="41"
        result=score(f,answers)
        self.assertEqual(result["remaining_initial_defects"],0);self.assertEqual(result["introduced_errors"],1)

    def test_tamper_or_instrument_change_stops_session(self):
        path=self.store.path(self.s["id"]);raw=json.loads(path.read_text());raw["prior_exposure"]="seen";path.write_text(json.dumps(raw))
        with self.assertRaisesRegex(ValueError,"TRIAL_STATE_BINDING"):self.store.get(self.s["id"])
        protocol=self.folder/"protocol.json";raw=json.loads(protocol.read_text());raw["scope"]="changed";protocol.write_text(json.dumps(raw))
        with self.assertRaisesRegex(ValueError,"TRIAL_INSTRUMENT_CHANGED_NEW_COHORT_REQUIRED"):self.store.create("participant",True,"new")

if __name__=="__main__":unittest.main()
