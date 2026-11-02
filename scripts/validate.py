"""Demo assertion gate for CI."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from oci_service_mesh_router import Router, UnroutableError, load_config, validate

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
failed = 0
def check(name, cond):
    global failed
    print(f"{'PASS' if cond else 'FAIL'} {name}")
    failed += 0 if cond else 1

bad = validate(load_config(EXAMPLES / "mesh-config-broken.json"))
rules = {f["rule"] for f in bad}
check("broken config flags weight sum 90", "MESH002" in rules)
check("broken config flags shadowed header route", "MESH001" in rules)
check("broken config flags unknown backend", "MESH003" in rules)
check("broken config flags disabled ingress mTLS", "MESH006" in rules)
good = validate(load_config(EXAMPLES / "mesh-config.json"))
check("clean config has no errors", not any(f["severity"] == "error" for f in good))
try:
    Router(load_config(EXAMPLES / "mesh-config-broken.json"), "web-api")
    check("broken config cannot build a router", False)
except UnroutableError:
    check("broken config cannot build a router", True)

router = Router(load_config(EXAMPLES / "mesh-config.json"), "web-api")
plain = router.replay([{"id": f"req-{i:05d}"} for i in range(1000)])
check("1000 catch-all requests split near 90/10",
      abs(plain["observed"].get("stable-v1", 0) - 0.9) <= 0.04)
check("no misroutes on valid config", plain["misrouted"] == 0)
beta = router.replay([{"id": f"b{i}", "headers": {"x-beta-tester": "true"}} for i in range(50)])
check("beta header routes 100% to canary", beta["counts"] == {"canary-v2": 50})
again = router.replay([{"id": f"req-{i:05d}"} for i in range(1000)])
check("replay is deterministic", again["counts"] == plain["counts"])
print(f"validate: {'all checks passed' if not failed else str(failed) + ' check(s) failed'}")
sys.exit(1 if failed else 0)
