"""Offline model of OCI Service Mesh config: virtual services, routes, mTLS.

OCI Service Mesh is a free, Oracle-managed service mesh: virtual services
hold ordered route rules (first match wins), weighted backends split traffic,
and mTLS policy governs service-to-service encryption. This module validates
such a configuration; it never contacts OCI or any mesh.
"""
from __future__ import annotations

import json
from pathlib import Path

MTLS_POLICIES = {"STRICT", "PERMISSIVE", "DISABLED"}


class MeshError(ValueError):
    pass


def load_config(path) -> dict:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        assert isinstance(raw.get("virtual_services"), list), "missing 'virtual_services'"
        return raw
    except (OSError, json.JSONDecodeError, AssertionError) as e:
        raise MeshError(f"cannot load mesh config {path}: {e}") from e


def validate(config: dict) -> list[dict]:
    """Config findings: severity 'error' blocks use, 'warn' needs review."""
    findings = []

    def add(sev, rule, where, msg):
        findings.append({"severity": sev, "rule": rule, "where": where, "message": msg})

    backends = {b.get("name") for b in config.get("backends", [])}
    if len(backends) != len(config.get("backends", [])):
        add("error", "MESH004", "backends", "duplicate backend name in backends list")
    for vs in config["virtual_services"]:
        name = vs.get("name", "?")
        routes = vs.get("routes", [])
        if not routes:
            add("error", "MESH005", name, "virtual service has no routes")
        for i, route in enumerate(routes):
            where = f"{name}/route-{i}({route.get('name', '?')})"
            headers = route.get("match_headers") or {}
            weights = [b.get("weight") for b in route.get("backends", [])]
            total = sum(w for w in weights if isinstance(w, int))
            if any(not isinstance(w, int) or w < 0 for w in weights):
                add("error", "MESH002", where, "backend weights must be non-negative integers")
            elif total != 100:
                add("error", "MESH002", where,
                    f"backend weights sum to {total}, must be 100")
            for b in route.get("backends", []):
                if b.get("name") not in backends:
                    add("error", "MESH003", where, f"unknown backend {b.get('name')!r}")
            if not headers and i < len(routes) - 1:
                later = any((r.get("match_headers") for r in routes[i + 1:]))
                if later:
                    add("error", "MESH001", where,
                        "catch-all route appears before header-matched routes and shadows them (first match wins)")
    for port in config.get("ingress_ports", []):
        if str(port.get("mtls", "STRICT")).upper() == "DISABLED":
            add("error", "MESH006", f"ingress port {port.get('port', '?')}",
                "mTLS DISABLED on an internet-facing ingress port - traffic arrives unencrypted")
        elif str(port.get("mtls", "")).upper() not in MTLS_POLICIES:
            add("warn", "MESH006", f"ingress port {port.get('port', '?')}",
                f"unknown mTLS policy {port.get('mtls')!r}")
    return findings


def blocking(findings: list[dict]) -> bool:
    return any(f["severity"] == "error" for f in findings)
