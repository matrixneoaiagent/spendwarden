"""Keep the paper's headline numbers tied to the generated results.

If the harness is re-run during the hackathon and a metric moves, this test
fails, which is the signal to update the paper rather than ship stale numbers.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))



class PaperConsistencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.results = json.loads((ROOT / "experiment" / "results" / "results.json").read_text())
        cls.paper = (ROOT / "docs" / "PAPER.md").read_text()

    def test_full_swarm_figures(self):
        for name in ("none", "warden", "mediated"):
            s = self.results["swarm"][name]
            for key in ("executed_usd", "attack_executed_usd", "cap_overrun_usd"):
                self.assertIn(f"${s[key]:,.2f}", self.paper, f"{name}.{key}")
            if s["attack_containment_pct"] is not None:
                self.assertIn(f"{s['attack_containment_pct']:.1f}%", self.paper, f"{name} containment")
            self.assertIn(f"{s['honest_allowed_actions']}/{s['honest_actions']}", self.paper, f"{name} honest")

    def test_probe_figures(self):
        probes = self.results["probes"]
        for name in ("split", "race", "alias"):
            for scenario in ("none", "warden", "mediated"):
                value = probes[name][scenario]["executed_usd"]
                self.assertIn(f"${value:,.2f}", self.paper, f"{name}.{scenario}")
            over = probes[name]["warden"]["cap_overrun_usd"]
            if over:
                self.assertIn(f"+${over:,.2f}", self.paper, f"{name} overrun")

    def test_ledger_blind_and_starved_honest_work_are_quoted(self):
        warden = self.results["swarm"]["warden"]
        self.assertIn(f"${warden['ledger_blind_usd']:,.2f}", self.paper)
        denied = warden["honest_actions"] - warden["honest_allowed_actions"]
        self.assertIn(str(denied), self.paper)


if __name__ == "__main__":
    unittest.main()
