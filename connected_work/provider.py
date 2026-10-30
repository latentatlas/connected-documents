"""Explicit provider routing; a failed Nemotron call never falls back locally."""
from . import local_provider, nebius_provider


class Provider:
    def __init__(self, name, control=None):
        if name == "nebius":
            self.backend = nebius_provider.Client(control)
            self.name = "nebius_token_factory"
            self.model = nebius_provider.MODEL
            self.contract = nebius_provider.CONTRACT
        elif name == "local":
            self.backend = None
            self.name = "local_ollama"
            self.model = local_provider.MODEL
            self.contract = None
        else:
            raise ValueError("PROVIDER_IDENTITY")

    def status(self):
        base = {"provider": self.name, "model": self.model, "request_contract": self.contract}
        if self.backend:
            return base | self.backend.status()
        return base | {"external_calls": 0, "generation_available": True, "provider_block": None}

    def preflight(self, workspace):
        if self.backend:
            self.backend.preflight(workspace)

    def run_job(self, store, ident, job):
        if not self.backend:
            return local_provider.run_job(store, ident, job)
        try:
            raw, usage = self.backend.generate(job, store.folder / "calls" / job["id"])
        except Exception as exc:
            code = str(exc) if isinstance(exc, ValueError) else "NEBIUS_PROVIDER_UNAVAILABLE"
            store.finish(ident, job["id"], error=code)
        else:
            store.finish(ident, job["id"], raw=raw, usage=usage)
