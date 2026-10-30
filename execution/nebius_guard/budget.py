"""Local, persistent pre-dispatch reservations. This is NOT a provider billing cap."""
import datetime as dt
from decimal import Decimal, InvalidOperation
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile


class Blocked(ValueError):
    pass


def need(condition, code):
    if not condition:
        raise Blocked(code)


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def timestamp(value):
    try:
        result = dt.datetime.fromisoformat(value)
        need(result.tzinfo is not None, "TIMEZONE_REQUIRED")
        return result
    except (TypeError, ValueError):
        raise Blocked("INVALID_TIMESTAMP") from None


def money(value):
    # JSON strings only: do not silently round floats or accept booleans/NaN.
    need(type(value) is str, "MONEY_MUST_BE_DECIMAL_STRING")
    try:
        result = Decimal(value)
    except InvalidOperation:
        raise Blocked("INVALID_MONEY") from None
    need(result.is_finite() and result >= 0, "INVALID_MONEY")
    need(result.as_tuple().exponent >= -12 and result <= Decimal("1000000"), "MONEY_RANGE")
    return result


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    allow_nan=False).encode()).hexdigest()


def file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def accounted_attempt(attempt):
    """A reconciled format failure stays failed; only its known cost is resolved."""
    return attempt.get("status") == "settled" or (
        attempt.get("status") == "stopped"
        and attempt.get("reconciliation", {}).get("kind") in ("known_cost_json_failure", "known_cost_output_failure")
        and attempt.get("actual_usd") is not None
        and (attempt.get("error") == {"type": "JSONDecodeError"}
             or attempt.get("error") in (
                 {"type": "Blocked", "reason": "INCOMPLETE_COMPLETION"},
                 {"type": "Blocked", "reason": "DRAFT_STRUCTURE_BLOCKED"}))
    )


def evidence(record):
    need(isinstance(record, dict), "EVIDENCE_REQUIRED")
    path = Path(record.get("path", ""))
    need(path.is_file() and not path.is_symlink(), "EVIDENCE_FILE_MISSING")
    need(file_sha(path) == record.get("sha256"), "EVIDENCE_HASH_MISMATCH")


def private_directory(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.lstat()
    need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
         and stat.S_IMODE(info.st_mode) == 0o700, "UNSAFE_CONTROL_DIRECTORY")


def atomic_json(path, data):
    path = Path(path)
    fd, name = tempfile.mkstemp(prefix=".ledger-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Ledger:
    """Lock covers reserve -> HTTP -> settle. No automatic reset/retry/release."""
    def __init__(self, directory, binding, clock=utcnow):
        self.directory, self.binding, self.clock = Path(directory), binding, clock
        self.path = self.directory / "ledger.json"

    def __enter__(self):
        private_directory(self.directory)
        fd = os.open(self.directory / "lock", os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        self.lock = os.fdopen(fd, "r+")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if self.path.exists() or self.path.is_symlink():
                info = self.path.lstat()
                need(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                     and stat.S_IMODE(info.st_mode) == 0o600, "UNSAFE_LEDGER_FILE")
                self.data = json.loads(self.path.read_text())
                need(self.data.get("schema") == 1 and self.data.get("binding") == self.binding,
                     "LEDGER_BINDING_MISMATCH")
                need(isinstance(self.data.get("attempts"), list), "CORRUPT_LEDGER")
            else:
                self.data = {"schema": 1, "binding": self.binding, "attempts": []}
            return self
        except BlockingIOError:
            self.lock.close()
            raise Blocked("ANOTHER_CALL_IN_PROGRESS") from None
        except BaseException:
            self.lock.close()
            raise

    def __exit__(self, *args):
        self.lock.close()

    def reserve(self, policy, credit, request_id, allowance, request_sha):
        current = self.clock()
        for key in ("account_access_verified", "billing_behavior_reviewed",
                    "credit_only_execution_authorized", "model_available_verified"):
            need(policy.get(key) is True, "NOT_VERIFIED:" + key)
        need(policy.get("authorization_reference"), "AUTHORIZATION_REFERENCE_REQUIRED")
        price_age = current - timestamp(policy.get("price_verified_at"))
        need(dt.timedelta(0) <= price_age <= dt.timedelta(hours=1), "PRICE_CHECK_STALE")
        evidence(policy.get("price_evidence"))
        need(credit.get("source") == "authenticated_nebius_console", "LIVE_CONSOLE_OBSERVATION_REQUIRED")
        for key in ("account_id", "organization", "project"):
            need(credit.get(key) == policy.get(key) and policy.get(key), "CREDIT_IDENTITY_MISMATCH:" + key)
        need(credit.get("billing_active") is True and credit.get("credit_eligible_for_model") is True,
             "CREDIT_ACCESS_NOT_VERIFIED")
        need(credit.get("balance_consistent") is True, "CONFLICTING_BALANCE_EVIDENCE")
        evidence(credit.get("balance_evidence"))
        evidence(credit.get("expiry_evidence"))
        observed = timestamp(credit.get("observed_at"))
        need(dt.timedelta(0) <= current - observed <= dt.timedelta(seconds=120), "CREDIT_CHECK_STALE")
        expiry = credit.get("expiry")
        need(isinstance(expiry, dict), "CREDIT_EXPIRY_UNKNOWN")
        if expiry.get("kind") == "non_expiring":
            need(expiry.get("expires_at") is None, "CONFLICTING_EXPIRY")
        else:
            need(expiry.get("kind") == "expires_at", "CREDIT_EXPIRY_UNKNOWN")
            need(timestamp(expiry.get("expires_at")) > current + dt.timedelta(hours=1), "CREDIT_EXPIRING")

        attempts = self.data["attempts"]
        need(all(accounted_attempt(a) for a in attempts), "UNRESOLVED_ATTEMPT")
        need(len(attempts) < 12, "CALL_LIMIT")
        need(not any(a["request_id"] == request_id for a in attempts), "DUPLICATE_REQUEST")
        if attempts:
            need(observed > timestamp(attempts[-1]["finished_at"]), "FRESH_BALANCE_AFTER_PREVIOUS_CALL_REQUIRED")
        committed = sum((money(a["reserved_usd"]) for a in attempts), Decimal(0))
        budget, floor = money(policy["run_budget_usd"]), money(policy["untouched_credit_usd"])
        need(Decimal(0) < budget <= Decimal("0.10"), "RUN_BUDGET_EXCEEDS_APPROVED_DESIGN")
        need(floor >= Decimal("0.25"), "CREDIT_RESERVE_TOO_SMALL")
        need(allowance > 0 and committed + allowance <= budget, "RUN_BUDGET_EXHAUSTED")
        # Deliberately double-reserve earlier calls even if console has already deducted them.
        free = min(money(credit["free_credit_usd"]), money(credit["account_balance_usd"]))
        need(free >= committed + allowance + floor, "INSUFFICIENT_FREE_CREDIT")
        attempt = {"request_id": request_id, "request_sha256": request_sha,
                   "reserved_at": current.isoformat(), "reserved_usd": str(allowance),
                   "credit_observation": credit, "status": "reserved", "actual_usd": None}
        attempts.append(attempt)
        atomic_json(self.path, self.data)  # Durable BEFORE any network dispatch.
        return attempt

    def finish(self, attempt, actual, error):
        attempt.update({"finished_at": self.clock().isoformat(),
                        "actual_usd": str(actual) if actual is not None else None,
                        "status": "stopped" if error else "settled", "error": error})
        # The reservation stays committed even when actual cost was smaller.
        atomic_json(self.path, self.data)
