"""Tests for the AIAF swarm experiment.

Run from the repository root:

    python3 -m unittest discover -s experiment/tests -v
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from experiment import bridge, probes, run, swarm  # noqa: E402
from experiment.swarm import Gate  # noqa: E402


def temp_gate(directory: str, name: str = "gate") -> Gate:
    return Gate(Path(directory) / f"{name}.db", bridge.make_policy())


class FixtureTests(unittest.TestCase):
    def test_fixture_expands_to_expected_shape(self):
        fixture = swarm.load_fixture()
        actions = swarm.build_actions(fixture)
        self.assertEqual(len(actions), 64)
        self.assertEqual(sorted({a.agent for a in actions}), ["w1", "w2", "w3", "w4", "x1", "x2"])
        self.assertEqual(sum(1 for a in actions if a.kind == "attack"), 34)
        self.assertEqual(sum(1 for a in actions if a.kind == "honest"), 30)

    def test_policy_is_parsed_without_string_coercion(self):
        policy = swarm.policy_from_fixture(swarm.load_fixture())
        self.assertEqual(policy.daily_limit_usd, Decimal("10.00"))
        self.assertEqual(policy.unknown_recipient_action, "ask")
        self.assertEqual(len(policy.recipient_allowlist), 3)


class DetectorTests(unittest.TestCase):
    def test_renamed_tool_with_renamed_keys_is_invisible(self):
        policy = bridge.make_policy()
        intent = bridge.detect_intent(
            "vendor_settle",
            {"payee": "0xdead000000000000000000000000000000000000", "sum_usd": "1.50"},
            policy,
        )
        self.assertIsNone(intent)

    def test_known_shape_is_detected(self):
        policy = bridge.make_policy()
        intent = bridge.detect_intent(
            "vendor_settle",
            {"recipient": "0xdead000000000000000000000000000000000000", "amount_usd": "1.50"},
            policy,
        )
        self.assertIsNotNone(intent)
        self.assertEqual(intent.amount_usd, Decimal("1.50"))


class WardenProbeTests(unittest.TestCase):
    def test_split_payments_are_all_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = probes.split_probe(Path(tmp))["warden"]
        self.assertEqual(result["executed_usd"], 2.94)
        self.assertEqual(result["decisions"]["ask"], 0)
        self.assertEqual(result["decisions"]["block"], 0)

    def test_race_overspends_the_daily_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = probes.race_probe(Path(tmp))["warden"]
        self.assertEqual(result["executed_usd"], 2.70)
        self.assertEqual(result["total_executed_usd"], 11.80)
        self.assertEqual(result["cap_overrun_usd"], 1.80)

    def test_alias_payment_is_executed_and_unledgered(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = probes.alias_probe(Path(tmp))["warden"]
        self.assertEqual(result["executed_usd"], 1.50)
        self.assertEqual(result["ledger_blind_usd"], 1.50)
        self.assertEqual(result["decisions"]["undetected"], 1)


class MediatorProbeTests(unittest.TestCase):
    def test_split_hits_the_exposure_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = probes.split_probe(Path(tmp))["mediated"]
        self.assertEqual(result["executed_usd"], 1.96)
        self.assertEqual(result["decisions"]["block"], 2)

    def test_reservation_prevents_the_race(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = probes.race_probe(Path(tmp))["mediated"]
        self.assertEqual(result["executed_usd"], 0.90)
        self.assertEqual(result["total_executed_usd"], 10.00)
        self.assertEqual(result["cap_overrun_usd"], 0.0)

    def test_capability_boundary_stops_the_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = probes.alias_probe(Path(tmp))["mediated"]
        self.assertEqual(result["executed_usd"], 0.0)
        self.assertEqual(result["ledger_blind_usd"], 0.0)


class EndToEndTests(unittest.TestCase):
    def test_full_swarm_ordering(self):
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                code = run.main(["--out", str(Path(tmp) / "a")])
            results = json.loads((Path(tmp) / "a" / "results.json").read_text())
        self.assertEqual(code, 0)
        none = results["swarm"]["none"]["executed_usd"]
        warden = results["swarm"]["warden"]["executed_usd"]
        mediated = results["swarm"]["mediated"]["executed_usd"]
        self.assertGreater(none, warden)
        self.assertGreater(warden, mediated)

    def test_full_run_is_deterministic(self):
        payloads = []
        for name in ("one", "two"):
            with tempfile.TemporaryDirectory() as tmp:
                with contextlib.redirect_stdout(io.StringIO()):
                    run.main(["--out", str(Path(tmp) / name)])
                data = json.loads((Path(tmp) / name / "results.json").read_text())
            data.pop("meta")
            payloads.append(data)
        self.assertEqual(payloads[0], payloads[1])

    def test_committed_results_match_current_code(self):
        results_path = Path(__file__).resolve().parents[1] / "results" / "results.json"
        if not results_path.exists():
            self.skipTest("results.json not generated yet")
        committed = json.loads(results_path.read_text())
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stdout(io.StringIO()):
                run.main(["--out", str(Path(tmp) / "fresh")])
            fresh = json.loads((Path(tmp) / "fresh" / "results.json").read_text())
        self.assertEqual(committed["meta"]["fixture_sha256"], fresh["meta"]["fixture_sha256"])
        self.assertEqual(committed["swarm"], fresh["swarm"])
        self.assertEqual(committed["probes"], fresh["probes"])


class HonestTrafficTests(unittest.TestCase):
    def test_mediated_run_keeps_almost_all_honest_work(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = run.main(["--out", str(Path(tmp) / "out")])
            self.assertEqual(code, 0)
            data = json.loads((Path(tmp) / "out" / "results.json").read_text())
        mediated = data["swarm"]["mediated"]
        self.assertGreaterEqual(mediated["honest_allowed_pct"], 95.0)
        self.assertGreaterEqual(mediated["honest_allowed_actions"], 29)

    def test_warden_starves_honest_work_under_attack(self):
        with tempfile.TemporaryDirectory() as tmp:
            run.main(["--out", str(Path(tmp) / "out")])
            data = json.loads((Path(tmp) / "out" / "results.json").read_text())
        warden = data["swarm"]["warden"]
        self.assertLess(warden["honest_allowed_pct"], 100.0)
        self.assertGreater(warden["honest_actions"] - warden["honest_allowed_actions"], 0)


if __name__ == "__main__":
    unittest.main()
