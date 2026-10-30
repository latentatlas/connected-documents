"""Export the accepted snapshot only, never a pending draft."""
from copy import deepcopy
import io
import json
import zipfile

from .core import digest, require, stamp


def package(store, ident, revision):
    with store.lock:
        store.verify()
        work=deepcopy(store.current(ident,revision))
        require(bool(work["history"]),"REVIEW_BEFORE_EXPORT")
        last=work["history"][-1]
        require(last["after_sha256"]==digest(work["state"]),"EXPORT_STATE_BINDING")
        if last["job"]["provider"] == "nebius_token_factory":
            from .nebius_provider import verify_call
            verify_call(store.folder/"calls"/last["job"]["id"],last["job"])
    manifest={"kind":"fictional_reviewed_document_packet","project":ident,"revision":revision,
        "exported_at":stamp(),"state_sha256":digest(work["state"]),"reviewer":last["reviewer"],
        "provider":last["job"]["provider"],"model":(last["job"].get("usage") or {}).get("model"),
        "job_id":last["job"]["id"],"operator_edit_rounds":last["job"]["manual_edits"],
        "human_benefit_measured":False,"external_publication":False,
        "request_sha256":(last["job"].get("usage") or {}).get("request_sha256"),
        "provider_response_sha256":(last["job"].get("usage") or {}).get("provider_response_sha256"),
        "files":[{"path":d["artifact_id"]+".txt","title":d["title"],"version":d["version"],
                  "body_sha256":d["body_sha256"]} for d in work["state"]["documents"]]}
    memory=io.BytesIO()
    with zipfile.ZipFile(memory,"w",zipfile.ZIP_DEFLATED) as output:
        for doc in work["state"]["documents"]:
            output.writestr(doc["artifact_id"]+".txt",doc["body"])
        output.writestr("manifest.json",json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")
        output.writestr("READ_ME.txt","Fictional demonstration documents. Review example.invalid links before any real use.\n"
            "These files match the accepted workspace snapshot exactly. A pending draft is excluded.\n"
            "Reviewer: "+last["reviewer"]+". Assistant QA is not independent human review.\n"
            "Provider: "+last["job"]["provider"]+". Model: "+str(manifest["model"])+".\n"
            "Model call provenance is recorded in the manifest; raw responses remain in the local audit workspace.\n"
            "No human productivity improvement is established by this export.\n")
    return memory.getvalue(),manifest
