"""One bounded request to the pinned, loopback-only local model. No retries."""
import json
import time
import urllib.request
from pathlib import Path

from .core import atomic, digest, require, request, stamp

MODEL = "qwen3.6-27b-q4-local:latest"
MODEL_DIGEST = "0004b3d1d08363b7305f94ca53c3a9a1bcb02e98430df0e0897dc23e8121fbc6"
ENDPOINT = "http://127.0.0.1:11434"


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("LOCAL_PROVIDER_REDIRECT_BLOCKED")


def opener():
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())


def metadata():
    with opener().open(ENDPOINT+"/api/tags", timeout=5) as response:
        data = json.loads(response.read(2000000))
    matches = [item for item in data.get("models", []) if item.get("name") == MODEL]
    require(len(matches)==1 and matches[0].get("digest")==MODEL_DIGEST, "LOCAL_MODEL_IDENTITY")
    return {"provider":"local_ollama","model":MODEL,"digest":MODEL_DIGEST,"external_calls":0}


def generate(job, folder, timeout=240):
    folder=Path(folder);folder.mkdir(parents=True, exist_ok=False)
    meta=metadata();payload=request(job["input"], MODEL, job["language"])
    atomic(folder/"request.json", payload)
    atomic(folder/"attempt.json", {"job_id":job["id"],"started_at":stamp(),"model":meta,
        "endpoint":ENDPOINT+"/api/chat","request_sha256":digest(payload),"auto_retry":False})
    started=time.monotonic();chunks=[];count=0
    req=urllib.request.Request(ENDPOINT+"/api/chat",json.dumps(payload).encode(),{"Content-Type":"application/json"},method="POST")
    try:
        with opener().open(req, timeout=timeout) as response, (folder/"raw-stream.jsonl").open("wb") as stream:
            while True:
                require(time.monotonic()-started < timeout, "LOCAL_MODEL_DEADLINE")
                line=response.readline(200001)
                if not line: break
                count+=len(line)
                require(len(line)<=200000 and count<=2000000, "LOCAL_MODEL_RESPONSE_SIZE")
                stream.write(line);stream.flush()
                if not line.strip(): continue
                chunk=json.loads(line)
                require(chunk.get("model")==MODEL and "error" not in chunk,"LOCAL_MODEL_RESPONSE_IDENTITY")
                chunks.append(chunk)
                if chunk.get("done") is True: break
        require(chunks and chunks[-1].get("done") is True,"LOCAL_MODEL_INCOMPLETE")
        raw="".join(chunk.get("message",{}).get("content","") for chunk in chunks)
        require(len(raw)<=50000,"LOCAL_MODEL_RESPONSE_SIZE")
        final=chunks[-1]
        usage={"model":MODEL,"model_digest":MODEL_DIGEST,"done_reason":final.get("done_reason"),
            "model_wall_seconds":round(time.monotonic()-started,3),"prompt_tokens":final.get("prompt_eval_count"),
            "output_tokens":final.get("eval_count"),"external_calls":0,"human_time_measured":False}
        atomic(folder/"response.json",{"raw_content":raw,"usage":usage})
        return raw,usage
    except Exception as exc:
        atomic(folder/"failure.json",{"error_type":type(exc).__name__,"elapsed_seconds":round(time.monotonic()-started,3),"no_retry":True})
        raise


def run_job(store, ident, job):
    try:
        raw,usage=generate(job,store.folder/"calls"/job["id"])
    except Exception as exc:
        # Keep the dispatch record; never silently replay a failed request.
        error=str(exc) if isinstance(exc,ValueError) else "LOCAL_PROVIDER_UNAVAILABLE"
        store.finish(ident,job["id"],error=error)
    else:
        store.finish(ident,job["id"],raw=raw,usage=usage)
