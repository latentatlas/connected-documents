"""Bounded Nebius/NVIDIA transport with durable reservations and no retries."""
import json
import os
from pathlib import Path
import stat
import time
import urllib.request

from .core import atomic, digest, request, require, stamp, validate_input
from execution.nebius_guard.budget import (
    Ledger, accounted_attempt, evidence, file_sha, money, sha, timestamp, utcnow,
)

MODEL = "nvidia/nemotron-3-super-120b-a12b"
ENDPOINT = "https://api.tokenfactory.nebius.com/v1/chat/completions"
ROOT = Path(__file__).resolve().parents[1]
SECRET_PATH = ROOT / "work/local-secrets/nebius.env"
MAX_OUTPUT = 4096
PROMPT_V2 = "nebius_documents_v2_complete_links_no_rewrites"
CONTRACT = "nebius_documents_v3_reasoning"


def read(path):
    return json.loads(Path(path).read_text())


def payload(job):
    validate_input(job["input"])
    local = request(job["input"], MODEL, job["language"])
    messages = local["messages"]
    messages[0]["content"] += "\nReturn only JSON matching this schema:\n" + json.dumps(local["format"], ensure_ascii=False)
    version=job.get("provider_contract", "nebius_documents_v1")
    require(version in ("nebius_documents_v1", PROMPT_V2, CONTRACT), "UNKNOWN_PROVIDER_CONTRACT")
    if version in (PROMPT_V2, CONTRACT):
        messages[0]["content"] += (
            "\nBefore returning JSON, compare each proposed body with the current body. "
            "If the body is identical, REMOVE that edit. If all current documents already agree "
            "with the sources and active decisions, return action=noop and edits=[]; do not echo them as edits. "
            "When a source or active decision supplies a required registration/consent URL, "
            "include that exact URL in every affected participant document so the instruction is usable. "
            "Preserve unrelated documents and operator-only instructions. "
            + ("The reason field MUST be Turkish; document bodies remain English." if job["language"]=="tr"
               else "The reason field and document bodies must be English."))
    return {"model": MODEL, "messages": messages, "temperature": 0,
            "max_tokens": MAX_OUTPUT, "stream": False,
            "chat_template_kwargs": {"enable_thinking": version == CONTRACT},
            "response_format": {"type": "json_object"}}


def input_allowance(data):
    # Conservative UTF-8 byte bound plus chat-template overhead, not token count.
    return len(json.dumps(data["messages"], ensure_ascii=False).encode()) + 2048


def reservation(data):
    return (input_allowance(data) * money("0.30") + MAX_OUTPUT * money("0.90")) / money("1000000") * money("1.25")


def load_secret():
    info = SECRET_PATH.lstat()
    require(stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o600
            and info.st_uid == os.getuid() and info.st_nlink == 1, "UNSAFE_CREDENTIAL_FILE")
    lines = SECRET_PATH.read_text().splitlines()
    require(len(lines) == 1 and lines[0].startswith("NEBIUS_API_KEY="), "CREDENTIAL_FILE_FORMAT")
    secret = lines[0].split("=", 1)[1]
    require(bool(secret) and not any(c.isspace() for c in secret), "CREDENTIAL_FILE_FORMAT")
    return secret


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def send(data, secret):
    req = urllib.request.Request(ENDPOINT, json.dumps(data).encode(),
        {"Content-Type": "application/json", "Authorization": "Bearer " + secret}, method="POST")
    with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(req, timeout=180) as response:
        raw = response.read(2000001)
    require(len(raw) <= 2000000, "NEBIUS_RESPONSE_SIZE")
    return json.loads(raw)


def response_usage(raw, data, elapsed, native):
    require(isinstance(raw, dict) and raw.get("model") == MODEL, "RESPONSE_MODEL_MISMATCH")
    tokens = raw.get("usage", {})
    require(all(type(tokens.get(k)) is int and tokens[k] >= 0
                for k in ("prompt_tokens", "completion_tokens", "total_tokens")), "USAGE_MISSING")
    require(tokens["total_tokens"] == tokens["prompt_tokens"] + tokens["completion_tokens"], "USAGE_MISMATCH")
    require(tokens["prompt_tokens"] <= input_allowance(data) and tokens["completion_tokens"] <= MAX_OUTPUT, "TOKEN_BOUND_EXCEEDED")
    cost = (tokens["prompt_tokens"] * money("0.30") + tokens["completion_tokens"] * money("0.90")) / money("1000000")
    require(cost <= reservation(data), "RESERVATION_EXCEEDED")
    require(len(raw.get("choices", [])) == 1, "NEBIUS_CHOICE_COUNT")
    choice = raw["choices"][0]
    require(choice.get("finish_reason") == "stop", "INCOMPLETE_MODEL_RESPONSE")
    content = choice.get("message", {}).get("content")
    require(isinstance(content, str) and 0 < len(content) <= 50000, "NEBIUS_CONTENT_MISSING")
    require(not choice["message"].get("refusal") and not choice["message"].get("tool_calls"), "NEBIUS_UNEXPECTED_RESPONSE")
    usage = {"provider": "nebius_token_factory", "model": MODEL, "done_reason": "stop",
             "model_wall_seconds": elapsed, "prompt_tokens": tokens["prompt_tokens"],
             "output_tokens": tokens["completion_tokens"], "external_calls": 1 if native else 0,
             "transport": "provider" if native else "offline_test_double",
             "fresh_model_execution_verified": native,
             "request_sha256": digest(data), "provider_response_sha256": digest(raw),
             "token_rate_estimate_usd": str(cost), "human_time_measured": False}
    return content, usage, cost


class Client:
    def __init__(self, control):
        require(control is not None, "NEBIUS_CONTROL_REQUIRED")
        self.control = Path(control).resolve()

    def configuration(self, workspace):
        auth = read(self.control / "authorization.json")
        policy = read(self.control / "policy.json")
        require(auth.get("authorized") is True and auth.get("scope") == "connected_work_nebius_v1", "AUTHORIZATION_SCOPE")
        require(auth["workspace"] == str(Path(workspace).resolve()), "WORKSPACE_SCOPE_MISMATCH")
        require(auth["model"] == policy["model"] == MODEL, "POLICY_MODEL_MISMATCH")
        require(auth["operational_cap_usd"] == policy["run_budget_usd"] == "0.10"
                and auth["max_calls"] == 12, "POLICY_BUDGET_MISMATCH")
        require(policy["input_usd_per_million"] == "0.30" and policy["output_usd_per_million"] == "0.90", "PRICE_CHANGED_REPLAN_REQUIRED")
        require(Path(policy["authorization_reference"]).resolve() == self.control / "authorization.json", "AUTHORIZATION_PATH")
        account = auth.get("account")
        require(isinstance(account, dict) and set(account) == {"account_id", "organization", "project"}
                and all(isinstance(v, str) and v.strip() for v in account.values()), "ACCOUNT_AUTHORIZATION_REQUIRED")
        require(all(policy.get(k) == v for k, v in account.items()), "ACCOUNT_IDENTITY")
        require(timestamp(auth["expires_at"]) > utcnow(), "EXECUTION_SCOPE_EXPIRED")
        credit = read(self.control / "credit.json")
        return auth, policy, credit

    def preflight(self, workspace):
        auth, policy, credit = self.configuration(workspace)
        require(policy.get("credit_only_execution_authorized") is True, "NEBIUS_EXECUTION_CLOSED")
        age = (utcnow() - timestamp(credit["observed_at"])).total_seconds()
        require(0 <= age <= 120, "CREDIT_CHECK_STALE")
        require(0 <= (utcnow() - timestamp(policy["price_verified_at"])).total_seconds() <= 3600, "PRICE_CHECK_STALE")
        evidence(policy["price_evidence"]); evidence(credit["balance_evidence"]); evidence(credit["expiry_evidence"])
        path = self.control / "spending-control/ledger.json"
        if path.exists():
            attempts = read(path)["attempts"]
            require(all(accounted_attempt(a) for a in attempts), "UNRESOLVED_ATTEMPT")
            require(len(attempts) < auth["max_calls"], "CALL_LIMIT")
            if attempts:
                require(timestamp(credit["observed_at"]) > timestamp(attempts[-1]["finished_at"]), "CREDIT_CHECK_STALE")
            require(sum((money(a["reserved_usd"]) for a in attempts), money("0")) < money(policy["run_budget_usd"]), "RUN_BUDGET_EXHAUSTED")
        return auth, policy, credit

    def status(self):
        try:
            auth = read(self.control / "authorization.json")
            self.preflight(auth["workspace"])
            block = None
        except Exception as exc:
            block = str(exc) if isinstance(exc, ValueError) else "NEBIUS_SETUP_REQUIRED"
        path = self.control / "spending-control/ledger.json"
        attempts = read(path)["attempts"] if path.exists() else []
        return {"generation_available": block is None, "provider_block": block,
                "external_calls": len(attempts), "budget_cap_usd": "0.10",
                "reserved_usd": str(sum((money(a["reserved_usd"]) for a in attempts), money("0"))),
                "provider_credit_only_stop_verified": False}

    def generate(self, job, folder, transport=None):
        transport = send if transport is None else transport
        native = transport is send
        folder = Path(folder)
        require(folder.name == job["id"] and folder.parent.name == "calls", "CALL_FOLDER_IDENTITY")
        workspace = folder.parent.parent.resolve()
        auth, policy, credit = self.preflight(workspace)
        require(job["provider"] == "nebius_token_factory", "JOB_PROVIDER_IDENTITY")
        data = payload(job)
        secret = load_secret() if native else "offline-test-key"
        binding = {"authorization_sha256": file_sha(self.control / "authorization.json"),
                   "workspace": str(workspace), "control": str(self.control),
                   "credential_sha256": sha(secret), "model": MODEL, "endpoint": ENDPOINT}
        with Ledger(self.control / "spending-control", binding) as ledger:
            require(len(ledger.data["attempts"]) < auth["max_calls"], "CALL_LIMIT")
            for old in ledger.data["attempts"]:
                for name, expected in old.get("artifacts", {}).items():
                    require(file_sha(workspace / "calls" / old["request_id"] / name) == expected, "CALL_ARTIFACT_CHANGED")
            require(not folder.exists(), "CALL_ALREADY_EXISTS")
            folder.mkdir(parents=True)
            atomic(folder / "request.json", data)
            atomic(folder / "preflight.json", {"authorization": auth, "policy": policy, "credit": credit})
            attempt = ledger.reserve(policy, credit, job["id"], reservation(data), sha(data))
            started = time.monotonic(); actual = None
            try:
                atomic(folder / "attempt.json", {"job_id": job["id"], "started_at": stamp(),
                    "endpoint": ENDPOINT, "request_sha256": digest(data),
                    "provider": "nebius_token_factory", "model": MODEL,
                    "transport": "provider" if native else "offline_test_double", "auto_retry": False})
                raw = transport(data, secret)
                atomic(folder / "raw_response.json", raw)
                content, usage, actual = response_usage(raw, data, round(time.monotonic()-started, 3), native)
                atomic(folder / "response.json", {"raw_content": content, "usage": usage})
                attempt["artifacts"] = {p.name: file_sha(p) for p in folder.iterdir() if p.is_file()}
                ledger.finish(attempt, actual, None)
            except BaseException as exc:
                failure = {"error_type": type(exc).__name__, "no_retry": True,
                           "elapsed_seconds": round(time.monotonic()-started, 3)}
                if isinstance(exc, ValueError) and str(exc).replace("_", "").isupper():
                    failure["code"] = str(exc)
                atomic(folder / "failure.json", failure)
                attempt["artifacts"] = {p.name: file_sha(p) for p in folder.iterdir() if p.is_file()}
                ledger.finish(attempt, actual, {"type": type(exc).__name__})
                raise
        return content, usage


def verify_call(folder, job):
    """Replay native transport records without a key or any network access."""
    folder = Path(folder)
    data = read(folder / "request.json"); attempt = read(folder / "attempt.json")
    require(data == payload(job), "REQUEST_REPLAY_MISMATCH")
    require(attempt["endpoint"] == ENDPOINT and attempt["model"] == MODEL
            and attempt["provider"] == job["provider"] == "nebius_token_factory", "PROVIDER_IDENTITY")
    require(attempt["transport"] == "provider" and attempt["auto_retry"] is False, "NOT_NATIVE_TRANSPORT")
    require(attempt["request_sha256"] == digest(data), "SAVED_REQUEST_CHANGED")
    raw = read(folder / "raw_response.json")
    response = read(folder / "response.json")
    content, usage, _ = response_usage(raw, data, response["usage"]["model_wall_seconds"], True)
    require(response == {"raw_content": content, "usage": usage}, "RESPONSE_RECORD_CHANGED")
    require(content == job["raw_response"] and usage == job["usage"], "NATIVE_RESPONSE_CHANGED")
    return attempt


def verify_spending(workspace, control):
    """Historical reconciliation only; no freshness refresh, secret read or call."""
    workspace=Path(workspace).resolve();control=Path(control).resolve()
    ledger=read(control/"spending-control/ledger.json")
    auth=read(control/"authorization.json")
    require(ledger["binding"]["workspace"]==str(workspace)
            and ledger["binding"]["control"]==str(control),"LEDGER_SCOPE_MISMATCH")
    require(ledger["binding"]["authorization_sha256"]==file_sha(control/"authorization.json"),"AUTHORIZATION_CHANGED")
    rows=[]
    for attempt in ledger["attempts"]:
        folder=workspace/"calls"/attempt["request_id"]
        for name,expected in attempt["artifacts"].items():
            require(Path(name).name==name and file_sha(folder/name)==expected,"CALL_ARTIFACT_CHANGED")
        data=read(folder/"request.json");receipt=read(folder/"attempt.json")
        require(attempt["request_sha256"]==sha(data) and receipt["request_sha256"]==digest(data),"REQUEST_BINDING")
        require(receipt["transport"]=="provider" and receipt["endpoint"]==ENDPOINT,"NOT_NATIVE_TRANSPORT")
        row={"job_id":attempt["request_id"],"status":attempt["status"],"reserved_usd":attempt["reserved_usd"],"actual_usd":attempt["actual_usd"]}
        if attempt["status"]=="settled":
            response=read(folder/"response.json")
            content,usage,cost=response_usage(read(folder/"raw_response.json"),data,response["usage"]["model_wall_seconds"],True)
            require(response=={"raw_content":content,"usage":usage},"RESPONSE_RECORD_CHANGED")
            require(money(attempt["actual_usd"])==cost,"COST_BINDING")
            row.update(model=usage["model"],model_seconds=usage["model_wall_seconds"])
        rows.append(row)
    reserved=sum((money(row["reserved_usd"]) for row in rows),money("0"))
    require(reserved<=money(auth["operational_cap_usd"]) and len(rows)<=auth["max_calls"],"SCOPE_LIMIT")
    return {"new_external_calls":0,"native_attempts":len(rows),"rows":rows,
            "reserved_usd":str(reserved),"token_rate_estimate_usd":str(sum((money(row["actual_usd"]) for row in rows if row["actual_usd"] is not None),money("0"))),
            "unknown_cost_attempts":sum(row["actual_usd"] is None for row in rows),
            "not_provider_invoice":True,"provider_hard_stop_verified":False}
