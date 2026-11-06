from __future__ import annotations

import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spendwarden.service import SpendWarden  # noqa: E402
from spendwarden.storage import Ledger  # noqa: E402

PAY_TO = "0x1111111111111111111111111111111111111111"


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ledger = Ledger(Path(self.tmp.name) / "ledger.db")
        self.cfg = {
            "mode": "enforce",
            "daily_limit_usd": 5.0,
            "monthly_limit_usd": 50.0,
            "per_call_limit_usd": 2.0,
            "approval_threshold_usd": 0.5,
            "recipient_allowlist": [PAY_TO],
            "asset_allowlist": ["USDC", "USDT", "OUSD"],
            "network_allowlist": ["base", "tempo", "bsc"],
            "watch_terminal": True,
        }

        def get(key, default=None):
            return self.cfg.get(key, default)

        self.service = SpendWarden(self.ledger, get)
        self.args = {
            "amount_usd": 0.25,
            "asset": "USDC",
            "network": "base",
            "recipient": PAY_TO,
            "purpose": "test",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_check_allows(self):
        result = json.loads(self.service.tool_check(self.args))
        self.assertTrue(result["ok"])
        self.assertEqual(result["decision"]["action"], "allow")
        self.assertEqual(result["remaining"]["today_usd"], 5.0)

    def test_check_blocks_over_per_call(self):
        args = dict(self.args, amount_usd=3.0)
        result = json.loads(self.service.tool_check(args))
        self.assertEqual(result["decision"]["action"], "block")

    def test_record_and_idempotency(self):
        args = dict(self.args, payment_id="pay-1", tx_hash="0xabc")
        first = json.loads(self.service.tool_record(args))
        self.assertTrue(first["ok"])
        self.assertFalse(first["duplicate"])
        self.assertEqual(first["spent"]["today_usd"], 0.25)
        second = json.loads(self.service.tool_record(args))
        self.assertTrue(second["ok"])
        self.assertTrue(second["duplicate"])
        self.assertEqual(second["spent"]["today_usd"], 0.25)

    def test_record_requires_idempotency_key(self):
        result = json.loads(self.service.tool_record(self.args))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "idempotency_key_required")

    def test_record_requires_approval(self):
        args = dict(self.args, amount_usd=0.75, payment_id="pay-2")
        result = json.loads(self.service.tool_record(args))
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "approval_required")
        approved = json.loads(self.service.tool_record(dict(args, approved=True)))
        self.assertTrue(approved["ok"])

    def test_report(self):
        self.service.tool_record(dict(self.args, payment_id="pay-3"))
        result = json.loads(self.service.tool_report({"period": "today"}))
        self.assertTrue(result["ok"])
        self.assertEqual(result["total_usd"], 0.25)
        self.assertEqual(result["count"], 1)
        self.assertEqual(result["top_recipients"][0]["recipient"], PAY_TO)

    def test_hook_blocks_in_enforce(self):
        directive = self.service.pre_tool_call(
            "wallet_send",
            {"amount": 3.0, "asset": "USDC", "network": "base", "recipient": PAY_TO},
            task_id="t1",
        )
        self.assertEqual(directive["action"], "block")

    def test_hook_asks_in_enforce(self):
        directive = self.service.pre_tool_call(
            "wallet_send",
            {"amount": 0.75, "asset": "USDC", "network": "base", "recipient": PAY_TO},
            task_id="t1",
        )
        self.assertEqual(directive["action"], "approve")

    def test_hook_allows_in_enforce(self):
        directive = self.service.pre_tool_call(
            "wallet_send",
            {"amount": 0.25, "asset": "USDC", "network": "base", "recipient": PAY_TO},
            task_id="t1",
        )
        self.assertIsNone(directive)

    def test_hook_observes_only(self):
        self.cfg["mode"] = "observe"
        directive = self.service.pre_tool_call(
            "wallet_send",
            {"amount": 3.0, "asset": "USDC", "network": "base", "recipient": PAY_TO},
            task_id="t1",
        )
        self.assertIsNone(directive)

    def test_hook_ignores_unrelated_tool(self):
        directive = self.service.pre_tool_call("read_file", {"path": "/tmp/x"}, task_id="t1")
        self.assertIsNone(directive)

    def test_slash_report(self):
        self.service.tool_record(dict(self.args, payment_id="pay-4"))
        text = self.service.slash_report("today")
        self.assertIn("SpendWarden", text)
        self.assertIn("0.25", text)


if __name__ == "__main__":
    unittest.main()
