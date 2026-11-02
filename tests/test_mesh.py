"""Mesh validation rules and deterministic routing."""
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from oci_service_mesh_router import (MeshError, Router, UnroutableError,
                                     load_config, validate)

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def cfg(routes, backends=None, ports=None):
    return {"backends": backends or [{"name": "a"}, {"name": "b"}],
            "virtual_services": [{"name": "svc", "routes": routes}],
            "ingress_ports": ports or []}


def weighted(pairs):
    return {"name": "w", "backends": [{"name": n, "weight": w} for n, w in pairs]}


class ValidationTests(unittest.TestCase):
    def test_weights_must_sum_100(self):
        f = validate(cfg([weighted([("a", 80), ("b", 10)])]))
        self.assertIn("MESH002", {x["rule"] for x in f})

    def test_unknown_backend_flagged(self):
        f = validate(cfg([weighted([("a", 50), ("ghost", 50)])]))
        self.assertIn("MESH003", {x["rule"] for x in f})

    def test_catch_all_shadowing_header_route_flagged(self):
        routes = [weighted([("a", 100)]),
                  {"name": "hdr", "match_headers": {"x-b": "1"}, "backends": [{"name": "b", "weight": 100}]}]
        f = validate(cfg(routes))
        self.assertIn("MESH001", {x["rule"] for x in f})

    def test_header_route_first_is_fine(self):
        routes = [{"name": "hdr", "match_headers": {"x-b": "1"}, "backends": [{"name": "b", "weight": 100}]},
                  weighted([("a", 100)])]
        self.assertEqual([x for x in validate(cfg(routes)) if x["severity"] == "error"], [])

    def test_disabled_ingress_mtls_blocked(self):
        f = validate(cfg([weighted([("a", 100)])], ports=[{"port": 443, "mtls": "DISABLED"}]))
        self.assertIn("MESH006", {x["rule"] for x in f})
        f = validate(cfg([weighted([("a", 100)])], ports=[{"port": 443, "mtls": "STRICT"}]))
        self.assertNotIn("MESH006", {x["rule"] for x in f})

    def test_bad_config_file_rejected(self):
        with self.assertRaises(MeshError):
            load_config(EXAMPLES / "missing.json")


class RoutingTests(unittest.TestCase):
    def setUp(self):
        self.router = Router(load_config(EXAMPLES / "mesh-config.json"), "web-api")

    def test_header_route_wins_over_catch_all(self):
        self.assertEqual(self.router.route({"id": "x", "headers": {"X-Beta-Tester": "true"}}),
                         "canary-v2")

    def test_unknown_service_rejected(self):
        with self.assertRaises(UnroutableError):
            Router(load_config(EXAMPLES / "mesh-config.json"), "nope")

    def test_broken_config_cannot_route(self):
        with self.assertRaises(UnroutableError):
            Router(load_config(EXAMPLES / "mesh-config-broken.json"), "web-api")

    def test_distribution_follows_weights(self):
        stats = self.router.replay([{"id": f"r{i:05d}"} for i in range(2000)])
        self.assertLessEqual(abs(stats["observed"]["stable-v1"] - 0.9), 0.03)
        self.assertEqual(stats["misrouted"], 0)

    def test_deterministic_replay(self):
        reqs = [{"id": f"r{i}"} for i in range(200)]
        self.assertEqual(self.router.replay(reqs)["counts"], self.router.replay(reqs)["counts"])

    def test_no_catch_all_means_explicit_unroutable(self):
        c = cfg([{"name": "hdr", "match_headers": {"x-b": "1"},
                  "backends": [{"name": "a", "weight": 100}]}])
        r = Router(c, "svc")
        with self.assertRaises(UnroutableError):
            r.route({"id": "x"})


if __name__ == "__main__":
    unittest.main()
