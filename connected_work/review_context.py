"""Read-only explanations derived from the same identity-bound source snapshot.

These describe the configured task, not an LLM's reasoning or a semantic verdict.
No model dispatch, accepted-state mutation or extra source facts.
"""
from copy import deepcopy
from datetime import date, timedelta

from .core import digest, make_input, require
from experiments.thesis_transfer_v1.adapter import validate_input


ROLES = {
    "project": {
        "project-brief": (["Proje özeti", "Project brief"], ["Proje sahibi", "Project owner"], ["Kapsamı ve teslim taahhüdünü takip eder.", "Tracks scope and the delivery commitment."]),
        "work-plan": (["İş planı", "Work plan"], ["Uygulama ve test ekibi", "Delivery and QA team"], ["Testlerin ne zaman başlayacağını ve tamamlanacağını planlar.", "Plans when testing starts and finishes."]),
        "handoff-note": (["Devir notu", "Handoff note"], ["İşi devralan ekip", "Receiving team"], ["Teslimin hangi tarihte ve hangi koşullarla yapılacağını kontrol eder.", "Checks the handoff date and conditions."]),
    },
    "research": {
        "research-note": (["Sonuç notu", "Result note"], ["Araştırmacı", "Researcher"], ["Sonucun sayılarını, hesabını ve yöntemini kontrol eder.", "Checks the counts, calculation and method."]),
        "progress-brief": (["İlerleme özeti", "Progress brief"], ["Proje sorumlusu", "Project lead"], ["Sonuca bağlı devam kararını değerlendirir.", "Reviews the continuation decision based on the result."]),
        "presentation-notes": (["Sunum notları", "Speaking notes"], ["Sunumu yapan kişi", "Presenter"], ["Aynı sonucu ve sınırlılıkları dinleyicilere aktarır.", "Communicates the same result and limitations."]),
    },
    "volunteer": {
        "volunteer-message": (["Gönüllü daveti", "Volunteer invitation"], ["Gönüllü", "Volunteer"], ["Nereye gideceğini ve nasıl hazırlanacağını öğrenir.", "Learns where to go and how to prepare."]),
        "volunteer-faq": (["Sık sorulan sorular", "Volunteer FAQ"], ["Gönüllü ve destek ekibi", "Volunteers and support team"], ["Kayıt ve hazırlık sorularına tutarlı yanıt verir.", "Answers registration and preparation questions consistently."]),
        "coordinator-checklist": (["Ekibin kontrol listesi", "Internal checklist"], ["Koordinatör", "Coordinator"], ["İç operasyonun ayrı kurallarını uygular.", "Follows separate internal operating rules."]),
        "workshop-invite": (["Başka etkinliğin daveti", "Other event invitation"], ["Başka etkinliğin katılımcısı", "Participant in another event"], ["Bu değişikliğin kapsamı dışındaki etkinliğe hazırlanır.", "Prepares for an event outside this change's scope."]),
    },
}


def explain(work_id, data, facts, draft=None, mode="preview"):
    require(work_id in ROLES, "REVIEW_WORK_IDENTITY")
    validate_input(data)
    old = data["state"]
    require(set(ROLES[work_id]) == {d["artifact_id"] for d in old["documents"]}, "REVIEW_DOCUMENT_IDENTITIES")
    if draft is not None:
        require(old["package_id"] == draft["package_id"], "REVIEW_PACKAGE_IDENTITY")
        require([d["artifact_id"] for d in old["documents"]] == [d["artifact_id"] for d in draft["documents"]], "REVIEW_DOCUMENT_IDENTITIES")
        for before, after in zip(old["documents"], draft["documents"]):
            require(all(before.get(k) == after.get(k) for k in ("artifact_id", "project_id", "audience")), "REVIEW_DOCUMENT_IDENTITY")
            require(after["body_sha256"] == digest(after["body"]), "REVIEW_BODY_BINDING")
    sources = deepcopy(data["sources"] + data["user_feedback_chronological"])
    calculations = []
    if work_id == "project":
        start = (date.fromisoformat(facts["qa_signoff"]) - timedelta(days=3)).isoformat()
        expected = [f"Teslim: {facts['release_date']} · QA onayı: {facts['qa_signoff']}", f"Release: {facts['release_date']} · QA sign-off: {facts['qa_signoff']}"]
        calculations = [[f"QA başlangıcı = {facts['qa_signoff']} − 3 takvim günü = {start}", f"QA start = {facts['qa_signoff']} − 3 calendar days = {start}"]]
        preserve = ["Kapsam, sorumlular ve kapsam dışı özellikler aynı kalmalı.", "Scope, owners and excluded features must remain unchanged."]
    elif work_id == "research":
        rate = 100 * facts["passed"] / facts["total"]
        met = facts["passed"] * 100 >= facts["total"] * 75
        expected = [f"Aynı çalışma: {facts['passed']} / {facts['total']} · %{rate:.1f}", f"Same study: {facts['passed']} / {facts['total']} · {rate:.1f}%"]
        calculations = [[f"{facts['passed']} ÷ {facts['total']} × 100 = %{rate:.1f}", f"{facts['passed']} ÷ {facts['total']} × 100 = {rate:.1f}%"],
                        [f"%75 eşiği {'karşılanıyor' if met else 'karşılanmıyor'}. Karar bu hesaba bağlı.", f"The 75% threshold {'is met' if met else 'is not met'}. The decision follows this calculation."]]
        preserve = ["Yöntem, sınırlılıklar ve genelleme yapılmaması korunmalı.", "Preserve the method, limitations and restriction on generalization."]
    else:
        paper = facts["registration"] == "paper"
        expected = [f"Mekân: {facts['venue']} · " + ("Bu gönüllü grubu imzalı kâğıt onay getirmeli." if paper else "Telefondan kayıt; katılımcının çıktı alması gerekmiyor."),
                    f"Venue: {facts['venue']} · " + ("This volunteer group must bring signed paper consent." if paper else "Phone-friendly registration; no participant printing required.")]
        calculations = [["Yalnız gönüllü grubunun en son geçerli kararı uygulanır. İptal edilen kuraldan kalan ifadeleri ayrıca okuyun.", "Apply only the latest active volunteer decision. Read for wording left over from a revoked rule."]]
        preserve = ["Koordinatör belgesi ve başka etkinliğin daveti kelimesi kelimesine aynı kalmalı.", "The coordinator checklist and the other event invitation must remain word-for-word unchanged."]
    rows = []
    for index, doc in enumerate(old["documents"]):
        ident = doc["artifact_id"]
        title, audience, purpose = ROLES[work_id][ident]
        targeted = work_id != "volunteer" or ident in ("volunteer-message", "volunteer-faq")
        rows.append({"id": ident, "title": title, "audience": audience, "purpose": purpose,
                     "project_id": doc["project_id"], "targeted": targeted,
                     "changed": None if draft is None else doc["body"] != draft["documents"][index]["body"],
                     "expected": expected if targeted else ["Bu değişiklik uygulanmaz. Metnin tamamını koru.", "This change does not apply. Preserve all text."],
                     "source_ids": [s["source_id"] for s in sources] if targeted else []})
    return {"kind": "source_derived_review_context_v1", "work": work_id, "mode": mode,
            "snapshot_sha256": data["state_sha256"], "expected": expected, "calculations": calculations,
            "preserve": preserve, "documents": rows, "sources": sources,
            "semantic_correctness_confirmed": False}


def context_for(work, incoming=None):
    pending = work["pending"]
    if pending and pending.get("draft") is not None and incoming is None:
        return explain(work["id"], pending["input"], pending["transition"]["facts"], pending["draft"], "proposal")
    fields = {"project": ("release_date", "qa_signoff"), "research": ("passed", "total"), "volunteer": ("venue", "registration")}[work["id"]]
    selected = incoming if incoming is not None else {k: work["facts"][k] for k in fields}
    data, transition, _ = make_input(work, selected)
    return explain(work["id"], data, transition["facts"], None if incoming is not None else work["state"],
                   "preview" if incoming is not None else "saved")
