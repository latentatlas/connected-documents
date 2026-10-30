"""Same comparison and fixtures; version/hash metadata belongs to the host."""
import json

from experiments.continuous_transfer_v1.design import (
    ARMS, STEPS, MODEL, MODEL_DIGEST, SYSTEM as OLD_SYSTEM,
    fixtures, make_input, resolved_view, validate_events,
)
from .adapter import schema


OLD_CONTRACT = "Copy\nthe exact supplied artifact ID, version and body hash."
NEW_CONTRACT = ("Select exact supplied artifact IDs. The host binds each edit to the\n"
                "version and body hash from this saved request snapshot and checks that\n"
                "the current state has not changed. Do not return version or hash fields.")
assert OLD_SYSTEM.count(OLD_CONTRACT) == 1
SYSTEM = OLD_SYSTEM.replace(OLD_CONTRACT, NEW_CONTRACT)


def request(data):
    return {"model": MODEL, "messages": [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False, sort_keys=True)}],
            "format": schema(data), "think": False, "stream": True,
            "options": {"temperature": 0, "seed": 17, "num_ctx": 8192, "num_predict": 1400},
            "keep_alive": "3m"}
