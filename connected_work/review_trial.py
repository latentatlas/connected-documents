"""Local, fixed-output formative review study. No inference or customer data.

Authored fault challenges and healthy controls; never presented as native model
failure rates. The server keeps scoring keys out of the standard participant view.
"""
from copy import deepcopy
from datetime import date, timedelta
import io
import json
from pathlib import Path
import re
import threading
import time
import uuid
import zipfile

from .core import atomic, digest, require, stamp

VERSION = "review_comparison_v2_2026_10_30"
SITE = Path(__file__).parent / "site"


def case(family, variant):
    require(family in ("project", "research") and variant in ("a", "b"), "TRIAL_CASE_IDENTITY")
    ident = family + "-" + variant
    defective = variant == "a"
    if family == "project":
        release, signoff = (("2026-11-19", "2026-11-17") if variant == "a" else ("2026-12-16", "2026-12-14"))
        old_release = (date.fromisoformat(release)-timedelta(days=7)).isoformat()
        old_signoff = (date.fromisoformat(signoff)-timedelta(days=7)).isoformat()
        qa_start = (date.fromisoformat(signoff)-timedelta(days=3)).isoformat()
        old_start = (date.fromisoformat(old_signoff)-timedelta(days=3)).isoformat()
        owner = "Uygulama ekibi"; scope = "Çevrimdışı kullanım kapsam dışıdır."
        title = "Atlas teslimi" if variant == "a" else "Liman teslimi"
        sources = [{"id": ident+"-decision-v2", "title": "Onaylanmış tarih değişikliği", "text": f"{title}: teslim {release}, kalite onayı {signoff}. Kalite çalışması onaydan 3 takvim günü önce başlar."},
                   {"id": ident+"-scope-v1", "title": "Değişmeyen sorumluluk ve kapsam", "text": f"Sorumlu: {owner}. {scope} Bu karar sorumluluğu ve kapsamı değiştirmez."}]
        definitions = [("brief", "Müşteriye teslim bilgisi", "Müşteri", "Teslimi ve kapsamı kendi takvimine işler.", ["release", "signoff", "scope", "owner"]),
                       ("plan", "Ekibin iş planı", "Uygulama ve test ekibi", "Kalite çalışmasının başlangıcını ve onayını planlar.", ["release", "qa_start", "signoff", "owner"]),
                       ("handoff", "Devir listesi", "İşi devralan ekip", "Teslim tarihini, sorumlu ekibi ve kapsamı doğrular.", ["release", "signoff", "scope", "owner"])]
        expected = dict(release=release,signoff=signoff,qa_start=qa_start,scope=scope,owner=owner)
        before = dict(expected,release=old_release,signoff=old_signoff,qa_start=old_start)
        labels = {"release":"Teslim tarihi","signoff":"Kalite onayı","qa_start":"Kalite başlangıcı","scope":"Kapsam","owner":"Sorumlu ekip"}
        calculated = [f"Kalite başlangıcı: {signoff} − 3 takvim günü = {qa_start}"]
        summary = f"Teslim {release}; kalite onayı {signoff}. Kapsam ve sorumlu ekip aynı kalmalı."
        faults = {"brief.release":old_release,"plan.qa_start":old_start,"handoff.owner":"Destek ekibi"} if defective else {}
    else:
        passed, total = ((26,40) if variant=="a" else (34,40))
        old_passed = 32 if variant=="a" else 28
        rate = f"{100*passed/total:.1f}"; old_rate=f"{100*old_passed/total:.1f}"
        decision = "Eşik karşılanıyor; devam edilebilir." if passed*100>=total*75 else "Eşik karşılanmıyor; yeniden değerlendirin."
        old_decision = "Eşik karşılanıyor; devam edilebilir." if old_passed*100>=total*75 else "Eşik karşılanmıyor; yeniden değerlendirin."
        limitation = "Bu küçük kurgusal örneklemden genel başarı iddiası çıkarılamaz."
        title = "A senaryosu araştırması" if variant=="a" else "B senaryosu araştırması"
        sources=[{"id":ident+"-counts-v2","title":"Aynı çalışmanın düzeltilmiş sayıları","text":f"{title}: başarılı görev {passed}, toplam görev {total}. Önceki sayılar bu kayıtla değiştirilmiştir."},
                 {"id":ident+"-method-v1","title":"Değişmeyen hesap, karar ve sınır","text":f"Yüzde = başarılı ÷ toplam × 100; bir ondalık basamakla yazın. Devam eşiği %75'tir; eşitlik eşiği karşılar. {limitation}"}]
        definitions=[("note","Teknik sonuç notu","Araştırmacı","Sayıları ve yüzde hesabını denetler.",["passed","total","rate","decision","limitation"]),
                     ("brief","Yönetici özeti","Proje sorumlusu","Devam kararını değerlendirir.",["passed","total","rate","decision","limitation"]),
                     ("talk","Sunum notları","Sunumu yapan kişi","Aynı sonucu ve sınırlılıkları dinleyicilere aktarır.",["passed","total","rate","decision","limitation"])]
        expected=dict(passed=str(passed),total=str(total),rate=rate,decision=decision,limitation=limitation)
        before=dict(expected,passed=str(old_passed),rate=old_rate,decision=old_decision)
        labels={"passed":"Başarılı görev","total":"Toplam görev","rate":"Başarı yüzdesi (%)","decision":"Sonuca bağlı karar","limitation":"Yorumun sınırı"}
        calculated=[f"{passed} ÷ {total} × 100 = %{rate}",f"%75 eşiği: {decision}"]
        summary=f"Aynı çalışmanın sonucu {passed}/{total}. Yüzde ve karar buna uymalı; yorumun sınırı korunmalı."
        faults={"note.rate":old_rate,"brief.decision":old_decision,"talk.limitation":"Bu sonuç tüm kullanıcılar için başarıyı kanıtlar."} if defective else {}
    documents=[]
    for doc_id, doc_title, audience, purpose, keys in definitions:
        fields=[]
        for key in keys:
            field_id=doc_id+"."+key
            fields.append({"id":field_id,"label":labels[key],"before":before[key],"initial":faults.get(field_id,expected[key]),
                           "expected":expected[key],"required":before[key]!=expected[key],
                           "type":"date" if key in ("release","signoff","qa_start") else "decision" if key=="decision" else "text",
                           "source_ids":[s["id"] for s in sources]})
            if key=="decision":
                fields[-1]["options"]=["Eşik karşılanıyor; devam edilebilir.","Eşik karşılanmıyor; yeniden değerlendirin."]
        documents.append({"id":ident+"-"+doc_id,"title":doc_title,"audience":audience,"purpose":purpose,"fields":fields})
    return {"id":ident,"family":family,"variant":variant,"title":title,"summary":summary,"sources":sources,
            "calculations":calculated,"documents":documents,"fixture_kind":"authored_fault_challenge" if defective else "authored_healthy_control",
            "native_model_output":False,"initial_defects":len(faults)}


CATALOG={f+"-"+v:case(f,v) for f in ("project","research") for v in ("a","b")}


def plan(cohort):
    require(type(cohort) is int and 0<=cohort<4,"TRIAL_COHORT")
    rows=[{"case":"project-a","condition":"standard"},{"case":"research-a","condition":"assisted"},
          {"case":"project-b","condition":"assisted"},{"case":"research-b","condition":"standard"}]
    if cohort%2:
        for row in rows: row["condition"]="assisted" if row["condition"]=="standard" else "standard"
    return list(reversed(rows)) if cohort>=2 else rows


def protocol():
    files=[Path(__file__),Path(__file__).with_name("server.py"),SITE/"trial.js",SITE/"trial.html",SITE/"trial.css",SITE/"style.css"]
    return {"version":VERSION,"catalog_sha256":digest(CATALOG),"case_hashes":{k:digest(v) for k,v in CATALOG.items()},
        "instrument_sha256":{str(p.relative_to(Path(__file__).parent)):digest(p.read_text()) for p in files},
        "question":"Does source-linked review improve final field accuracy or lower review burden compared with equal-information standard review?",
        "scope":"Two authored Turkish structured-document jobs; fixed outputs, not Nemotron reliability or end-to-end generation.",
        "scoring_contract":"Source-preserved text and ISO dates use normalized exact matching; numbers allow equivalent decimal formatting. Decision fields offer the same two choices in both conditions. This is contracted field accuracy, not semantic grading of arbitrary prose.",
        "conditions":{"standard":"Sources, prior and editable draft fields; identical navigation and save controls.",
                      "assisted":"The same facts and drafts, plus derived calculations, per-field comparison and protection hints."},
        "sequence_plans":[plan(i) for i in range(4)],"cohort_allocation":"Cyclic by participant session creation; QA excluded. Not random sampling.",
        "defects":{"project-a":3,"research-a":3,"project-b":0,"research-b":0},
        "primary_outcomes":["remaining_initial_defects","introduced_errors","final_required_errors","final_protected_errors"],
        "secondary_outcomes":["final_field_edits","field_save_events","visible_unpaused_seconds_proxy","wall_seconds_including_breaks","effort_1_to_7"],
        "hypothesis":"Lower errors without greater burden, or lower burden without worse accuracy; report per task and person. No significance claim from a small pilot.",
        "controls":"Both methods receive identical source facts and identical starting drafts for each fixture. Each person sees each fixture once; reverse condition and order across four cohorts. No accuracy feedback before all four tasks finish.",
        "assistance":"Record instruction/content help as self-report; no external AI assistance during the comparison.",
        "timing":"Onboarding separate. Task timing starts before reading task context. Visibility heartbeat is a proxy, not verified attention; gaps, reloads and pauses are flagged. Setup cost of configuring this product is not measured.",
        "privacy":"Local pseudonymous session code, fictional field values and interaction/timing summaries only. No names, email, free-text feedback, IP logging, external calls or automatic public export. Review retention 30 days after collection; no automatic deletion.",
        "claims_not_supported":["general reliability","natural model error rate","population benefit","setup-inclusive time savings","independent replication"],
        "at_protocol_freeze_human_sessions_completed":0}


def normalized(value):
    return " ".join(value.strip().split()).replace(",",".").casefold()


def correct(field,value):
    # Decimal formatting is not a semantic defect; preserve all other contracted text.
    if field["id"].endswith((".passed",".total",".rate")):
        try: return float(value.strip().replace(",",".").removesuffix("%"))==float(field["expected"])
        except ValueError: return False
    return normalized(value)==normalized(field["expected"])


def score(fixture,answers):
    fields=[f for d in fixture["documents"] for f in d["fields"]]
    require(set(answers)=={f["id"] for f in fields},"TRIAL_FIELD_IDENTITY")
    initial={f["id"] for f in fields if not correct(f,f["initial"])}
    wrong={f["id"] for f in fields if not correct(f,answers[f["id"]])}
    return {"initial_defects":len(initial),"remaining_initial_defects":len(initial&wrong),"introduced_errors":len(wrong-initial),
            "final_wrong_fields":len(wrong),"final_required_errors":sum(f["id"] in wrong and f["required"] for f in fields),
            "final_protected_errors":sum(f["id"] in wrong and not f["required"] for f in fields),
            "required_positions":sum(f["required"] for f in fields),"protected_positions":sum(not f["required"] for f in fields),
            "final_field_edits":sum(answers[f["id"]]!=f["initial"] for f in fields),"wrong_field_ids":sorted(wrong)}


class TrialStore:
    def __init__(self,folder,clock=time.time):
        self.folder=Path(folder);self.clock=clock;self.lock=threading.RLock()

    def freeze(self):
        self.folder.mkdir(parents=True,exist_ok=True)
        frozen=self.folder/"protocol.json"; current=protocol()
        if frozen.exists(): require(json.loads(frozen.read_text())==current,"TRIAL_INSTRUMENT_CHANGED_NEW_COHORT_REQUIRED")
        else: atomic(frozen,current)
        return digest(current)

    def path(self,ident):
        require(isinstance(ident,str) and re.fullmatch(r"[a-f0-9]{16}",ident) is not None,"TRIAL_SESSION_IDENTITY")
        return self.folder/(ident+".json")

    def read(self,ident):
        value=json.loads(self.path(ident).read_text())
        require(value["id"]==ident and value["protocol_sha256"]==self.freeze(),"TRIAL_PROTOCOL_IDENTITY")
        prev=None
        for n,event in enumerate(value["events"],1):
            require(event["n"]==n and event["previous"]==prev and event["sha256"]==digest({k:v for k,v in event.items() if k!="sha256"}),"TRIAL_AUDIT_CHAIN")
            prev=event["sha256"]
        require(value["events"][-1]["state_sha256"]==digest({k:v for k,v in value.items() if k!="events"}),"TRIAL_STATE_BINDING")
        return value

    def write(self,s,action,detail=None):
        event={"n":len(s["events"])+1,"at":stamp(),"action":action,"detail":detail or {},
               "state_sha256":digest({k:v for k,v in s.items() if k!="events"}),"previous":s["events"][-1]["sha256"] if s["events"] else None}
        event["sha256"]=digest(event);s["events"].append(event);atomic(self.path(s["id"]),s)

    def create(self,actor,consent,exposure):
        with self.lock:
            require(actor in ("participant","assistant_qa") and consent is True and exposure in ("new","seen"),"TRIAL_START_CONFIRMATION")
            frozen=self.freeze()
            count=sum(json.loads(p.read_text()).get("actor")=="participant" for p in self.folder.glob("*.json") if p.name!="protocol.json")
            s={"id":uuid.uuid4().hex[:16],"actor":actor,"prior_exposure":exposure,"protocol_sha256":frozen,
               "created_at":stamp(),"created_clock":self.clock(),"phase":"onboarding","revision":1,"cohort":count%4,
               "plan":plan(count%4),"rounds":[],"events":[],"onboarding_seconds":None}
            self.write(s,"session_started",{"explicit_local_participation":True});return self.view(s)

    def view(self,s):
        result={k:deepcopy(s[k]) for k in ("id","actor","phase","revision","prior_exposure","onboarding_seconds")}
        result["completed_rounds"]=sum("result" in r for r in s["rounds"])
        result["total_rounds"]=4
        result["retention_review"]="Katılım kayıtları bu bilgisayarda tutulur; 30 gün sonra saklama ihtiyacı yeniden değerlendirilmelidir."
        if s["phase"] in ("active","paused","ratings"):
            r=s["rounds"][-1];fixture=deepcopy(CATALOG[r["case"]]);assisted=r["condition"]=="assisted"
            for key in ("initial_defects","fixture_kind","variant"): fixture.pop(key)
            if not assisted: fixture.pop("calculations");fixture.pop("summary")
            for doc in fixture["documents"]:
                for f in doc["fields"]:
                    f["value"]=r["answers"][f["id"]]
                    if assisted: f["matches"]=correct(f,f["value"])
                    else:
                        for k in ("expected","required","source_ids"): f.pop(k)
                    f.pop("initial")
            result.update(fixture=fixture,condition=r["condition"],reviewed=r["reviewed"],round_index=len(s["rounds"]),
                          timing_flags=r["timing_flags"],focus_seconds=round(r["focus_seconds"],1))
        if s["phase"]=="complete":
            result["results"]=[{k:deepcopy(r[k]) for k in ("case","condition","result","ratings","focus_seconds","wall_seconds","timing_flags","field_save_events")} for r in s["rounds"]]
            result["saved_documents"]=[{"case":r["case"],"documents":[{"title":d["title"],"text":"\n".join(f["label"]+": "+r["answers"][f["id"]] for f in d["fields"])} for d in CATALOG[r["case"]]["documents"]]} for r in s["rounds"]]
            result["claim"]=("Teknik yazılım kontrolü; insan denemesi veya fayda ölçümü değildir." if s["actor"]=="assistant_qa" else
                             "Tek kişinin dört bağımlı görevi. Genel fayda, model üstünlüğü veya süre tasarrufu sonucu değildir.")
        return result

    def get(self,ident):
        with self.lock: return self.view(self.read(ident))

    def command(self,ident,revision,action,payload):
        with self.lock:
            s=self.read(ident);now=self.clock()
            detail={"case":payload.get("case")} if isinstance(payload,dict) else {}
            require(type(revision) is int and s["revision"]==revision,"TRIAL_STALE_REVISION")
            require(isinstance(payload,dict),"TRIAL_PAYLOAD")
            if action=="ready":
                require(s["phase"]=="onboarding" and not payload,"TRIAL_PHASE")
                s["onboarding_seconds"]=max(0,now-s["created_clock"]);s["phase"]="ready"
            elif action=="start":
                require(s["phase"]=="ready" and not payload and len(s["rounds"])<4,"TRIAL_PHASE")
                row=s["plan"][len(s["rounds"])];fixture=CATALOG[row["case"]]
                s["rounds"].append(dict(deepcopy(row),started_at=stamp(),started_clock=now,last_tick=now,focus_seconds=0,was_visible=True,
                    answers={f["id"]:f["initial"] for d in fixture["documents"] for f in d["fields"]},reviewed=[],field_save_events=0,timing_flags=[]))
                s["phase"]="active"
            elif action=="ratings":
                require(s["phase"]=="ratings" and set(payload)=={"effort","ready","help"},"TRIAL_PHASE")
                require(type(payload["effort"]) is int and 1<=payload["effort"]<=7 and payload["ready"] in ("yes","no","unsure") and payload["help"] in ("none","instructions","content"),"TRIAL_RATINGS")
                r=s["rounds"][-1];r["ratings"]=payload;r["result"]=score(CATALOG[r["case"]],r["answers"])
                s["phase"]="complete" if len(s["rounds"])==4 else "ready"
            else:
                require(s["phase"] in ("active","paused"),"TRIAL_PHASE")
                r=s["rounds"][-1];fixture=CATALOG[r["case"]]
                require(payload.get("case")==r["case"],"TRIAL_CASE_IDENTITY")
                elapsed=max(0,now-r["last_tick"])
                if elapsed>45 and s["phase"]=="active" and "unobserved_gap" not in r["timing_flags"]: r["timing_flags"].append("unobserved_gap")
                if s["phase"]=="active" and r["was_visible"] and elapsed<=45:r["focus_seconds"]+=elapsed
                r["last_tick"]=now
                if action=="activity":
                    require(set(payload)=={"case","visible","reloaded"} and type(payload["visible"]) is bool and type(payload["reloaded"]) is bool,"TRIAL_ACTIVITY")
                    r["was_visible"]=payload["visible"]
                    if payload["reloaded"] and "reload" not in r["timing_flags"]:r["timing_flags"].append("reload")
                elif action in ("pause","resume"):
                    require(set(payload)=={"case"} and s["phase"]==("active" if action=="pause" else "paused"),"TRIAL_PHASE")
                    s["phase"]="paused" if action=="pause" else "active";r["was_visible"]=action=="resume"
                    if "paused" not in r["timing_flags"]:r["timing_flags"].append("paused")
                elif action=="save":
                    require(s["phase"]=="active" and set(payload)=={"case","document","answers","reviewed"},"TRIAL_PAYLOAD")
                    doc=next((d for d in fixture["documents"] if d["id"]==payload["document"]),None)
                    require(doc is not None and set(payload["answers"])=={f["id"] for f in doc["fields"]},"TRIAL_DOCUMENT_IDENTITY")
                    require(type(payload["reviewed"]) is bool and all(isinstance(v,str) and 0<len(v)<=500 for v in payload["answers"].values()),"TRIAL_ANSWER_VALUE")
                    detail.update(document=doc["id"],reviewed=payload["reviewed"],changes={k:{"before":r["answers"][k],"after":v} for k,v in payload["answers"].items() if r["answers"][k]!=v})
                    r["field_save_events"]+=sum(r["answers"][k]!=v for k,v in payload["answers"].items())
                    r["answers"].update(payload["answers"])
                    r["reviewed"]=[d for d in r["reviewed"] if d!=doc["id"]]
                    if payload["reviewed"]:r["reviewed"].append(doc["id"])
                elif action=="finish":
                    require(s["phase"]=="active" and set(payload)=={"case"},"TRIAL_PHASE")
                    require(set(r["reviewed"])=={d["id"] for d in fixture["documents"]},"TRIAL_REVIEW_ALL_DOCUMENTS")
                    r["wall_seconds"]=max(0,now-r["started_clock"]);r["finished_at"]=stamp();s["phase"]="ratings"
                else:raise ValueError("TRIAL_UNKNOWN_ACTION")
            s["revision"]+=1;self.write(s,action,detail);return self.view(s)

    def export(self,ident):
        with self.lock:
            s=self.read(ident);require(s["phase"]=="complete","TRIAL_COMPLETE_BEFORE_EXPORT")
            buffer=io.BytesIO()
            with zipfile.ZipFile(buffer,"w",zipfile.ZIP_DEFLATED) as z:
                z.writestr("results.json",json.dumps(self.view(s),ensure_ascii=False,indent=2))
                z.writestr("protocol.json",json.dumps(protocol(),ensure_ascii=False,indent=2))
                for r in s["rounds"]:
                    for doc in CATALOG[r["case"]]["documents"]:
                        body="\n".join(f["label"]+": "+r["answers"][f["id"]] for f in doc["fields"])
                        z.writestr(r["case"]+"/"+doc["id"]+".txt",body)
                z.writestr("READ_ME.txt","Local formative study; fixed authored outputs, not native model error rates. QA is not human evidence. Participant telemetry is not authorized for public release.\n")
            return buffer.getvalue()
