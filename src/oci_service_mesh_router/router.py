"""Deterministic traffic replay through a validated mesh config.

Routes are evaluated in order (first match wins), then weighted backends are
chosen by hashing the request id - so replays are reproducible and tests are
stable, while the distribution still follows the configured weights.
"""
from __future__ import annotations

import hashlib

from .mesh import blocking, validate


class UnroutableError(ValueError):
    pass


class Router:
    def __init__(self, config: dict, service: str):
        findings = validate(config)
        if blocking(findings):
            raise UnroutableError(
                "config has blocking errors: " + "; ".join(f["message"] for f in findings if f["severity"] == "error"))
        self.config = config
        self.service = next((v for v in config["virtual_services"] if v.get("name") == service), None)
        if self.service is None:
            raise UnroutableError(f"virtual service {service!r} not in config")

    def route(self, request: dict) -> str:
        headers = {str(k).lower(): str(v) for k, v in (request.get("headers") or {}).items()}
        for route in self.service["routes"]:
            match = route.get("match_headers") or {}
            if match and all(headers.get(str(k).lower()) == str(v) for k, v in match.items()):
                return self._pick(route, request)
        for route in self.service["routes"]:
            if not (route.get("match_headers")):
                return self._pick(route, request)
        raise UnroutableError("no route matched and no catch-all route exists")

    @staticmethod
    def _pick(route: dict, request: dict) -> str:
        backs = route["backends"]
        digest = int(hashlib.sha256(str(request.get("id", "")).encode()).hexdigest(), 16)
        slot = digest % 100
        acc = 0
        for b in backs:
            acc += b["weight"]
            if slot < acc:
                return b["name"]
        return backs[-1]["name"]

    def replay(self, requests: list[dict]) -> dict:
        counts, misrouted = {}, 0
        for req in requests:
            try:
                backend = self.route(req)
                counts[backend] = counts.get(backend, 0) + 1
            except UnroutableError:
                misrouted += 1
        total = len(requests)
        expected = {}
        for route in self.service["routes"]:
            if not (route.get("match_headers")):
                expected = {b["name"]: b["weight"] / 100 for b in route["backends"]}
        return {"requests": total, "misrouted": misrouted, "counts": counts,
                "observed": {b: round(c / total, 4) for b, c in counts.items()} if total else {},
                "expected_catch_all": expected}
