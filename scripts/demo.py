"""Visible demo: validate configs, then replay 1000 synthetic requests through the mesh."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from oci_service_mesh_router import Router, load_config, validate

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def show_validation(cfg_file):
    findings = validate(load_config(EXAMPLES / cfg_file))
    print(f"== validate {cfg_file}: {len(findings)} finding(s)")
    for f in findings:
        print(f"  [{f['severity'].upper():5}] {f['rule']} {f['where']}: {f['message']}")
    print()
    return findings


def main() -> int:
    bad = show_validation("mesh-config-broken.json")
    good = show_validation("mesh-config.json")
    assert any(f["severity"] == "error" for f in bad) and not any(f["severity"] == "error" for f in good)

    router = Router(load_config(EXAMPLES / "mesh-config.json"), "web-api")
    requests = [{"id": f"req-{i:05d}"} for i in range(1000)]
    requests += [{"id": f"beta-{i:03d}", "headers": {"x-beta-tester": "true"}} for i in range(50)]
    stats = router.replay(requests)
    print(f"== replay: {stats['requests']} requests through 'web-api'")
    print(f"  counts: {stats['counts']}  (misrouted: {stats['misrouted']})")
    beta = router.replay([{"id": f"b{i}", "headers": {"x-beta-tester": "true"}} for i in range(50)])
    plain = router.replay([{"id": f"req-{i:05d}"} for i in range(1000)])
    print(f"  beta-tester requests -> {beta['counts']} (header route: 100% canary)")
    print(f"  catch-all observed {plain['observed']} vs expected {plain['expected_catch_all']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
