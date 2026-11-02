# oci-ootb-service-mesh-canary-router

An **offline model of OCI Service Mesh** traffic management: it validates a mesh-style configuration (virtual services, ordered route rules, weighted backends, mTLS policy) and replays a request stream through it deterministically, so a canary rollout config can be proven before it ever touches a cluster. Modeled on Oracle Cloud Infrastructure (OCI) **Service Mesh**, the built-in service that adds mTLS, telemetry and traffic management to microservices without application changes.

> **No OCI tenancy, cluster or sidecar is needed or contacted.** Configs and requests are synthetic; the value is in the mesh semantics - route order, weight math, mTLS policy - implemented as real runnable code and verified in CI.

## Why this models the real service

- OCI Service Mesh is itself **free**: per [Oracle's Service Mesh page](https://www.oracle.com/cloud/cloud-native/service-mesh/), "OCI Service Mesh is a free, Oracle-managed service" (checked 2026-11-03). Its concepts - virtual services, route rules, ingress gateways, mTLS - are documented in the [Service Mesh overview](https://docs.oracle.com/en-us/iaas/Content/service-mesh/overview.htm).
- The two failure classes this tool catches are the ones that bite in real rollouts: a catch-all route ordered before header routes (first match wins, so the header route is silently dead) and weights that do not sum to 100; plus unknown backends and mTLS disabled on an internet-facing ingress port.

## What it does

| Rule | Severity | Meaning |
| --- | --- | --- |
| MESH001 | error | catch-all route ordered before header-matched routes, shadowing them |
| MESH002 | error | backend weights do not sum to 100 (or are not non-negative integers) |
| MESH003 | error | route references a backend not in the backends list |
| MESH004 | error | duplicate backend name |
| MESH005 | error | virtual service with no routes |
| MESH006 | error/warn | mTLS DISABLED (error) or unknown policy (warn) on an ingress port |

A config with any error finding cannot build a `Router` - the same posture as a mesh rejecting an invalid config. Routing is then **first-match-wins by route order**, and weighted backends are chosen by hashing the request id, so replays are exactly reproducible while the distribution follows the configured weights.

## Quickstart

```bash
python scripts/demo.py        # validate a broken + a clean config, replay 1050 requests
python scripts/validate.py    # assertion gate used in CI
python -m unittest discover -s tests -v
```

The demo shows the broken config's 4 blocking errors, then replays 1000 plain requests (observed 91.2/8.8 vs configured 90/10) plus 50 beta-tester requests that go 100% to the canary via the header route.

## Honest limits

- Offline model: no real proxy, sidecar, TLS handshake or telemetry; distribution is hash-based and deterministic, not statistical sampling.
- Header matching is exact-string equality only (no regex, path or method matching).
- mTLS checks are config-level; nothing here proves encryption in a real deployment.

## References

- Oracle, [Service Mesh](https://www.oracle.com/cloud/cloud-native/service-mesh/): "OCI Service Mesh is a free, Oracle-managed service" (checked 2026-11-03).
- Oracle, [Service Mesh overview](https://docs.oracle.com/en-us/iaas/Content/service-mesh/overview.htm): virtual services, route rules, ingress gateways, mTLS policy.
