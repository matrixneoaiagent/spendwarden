from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spendwarden.policy import (  # noqa: E402
    Policy,
    SpendIntent,
    atomic_to_usd,
    detect_intent,
    evaluate,
    intent_from_command,
    to_micro,
)


def make_policy(**overrides):
    base = dict(
        mode="enforce",
        daily_limit_usd=Decimal("5.00"),
        monthly_limit_usd=Decimal("50.00"),
        per_call_limit_usd=Decimal("2.00"),
        approval_threshold_usd=Decimal("0.50"),
        recipient_allowlist=("0x1111111111111111111111111111111111111111",),
        asset_allowlist=("USDC", "USDT", "OUSD"),
        network_allowlist=("base", "tempo", "bsc"),
    )
    base.update(overrides)
    return Policy(**base)


class PolicyTests(unittest.TestCase):
    def test_allow_small_allowlisted_payment(self):
        decision = evaluate(
            SpendIntent(Decimal("0.25"), "USDC", "base", "0x1111111111111111111111111111111111111111"),
            make_policy(),
            0,
            0,
        )
        self.assertEqual(decision.action, "allow")

    def test_block_over_per_call(self):
        decision = evaluate(SpendIntent(Decimal("5.00"), "USDC", "base", ""), make_policy(), 0, 0)
        self.assertEqual(decision.action, "block")
        self.assertTrue(any("per-call" in reason for reason in decision.reasons))

    def test_ask_at_threshold(self):
        decision = evaluate(
            SpendIntent(Decimal("0.50"), "USDC", "base", "0x1111111111111111111111111111111111111111"),
            make_policy(),
            0,
            0,
        )
        self.assertEqual(decision.action, "ask")

    def test_unknown_recipient_asks(self):
        decision = evaluate(
            SpendIntent(Decimal("0.25"), "USDC", "base", "0x2222222222222222222222222222222222222222"),
            make_policy(),
            0,
            0,
        )
        self.assertEqual(decision.action, "ask")
        self.assertTrue(any("allowlist" in reason for reason in decision.reasons))

    def test_unknown_recipient_blocks_when_configured(self):
        decision = evaluate(
            SpendIntent(Decimal("0.25"), "USDC", "base", "0x2222222222222222222222222222222222222222"),
            make_policy(unknown_recipient_action="block"),
            0,
            0,
        )
        self.assertEqual(decision.action, "block")

    def test_asset_and_network_blocks(self):
        asset = evaluate(SpendIntent(Decimal("0.25"), "DAI", "base", ""), make_policy(), 0, 0)
        network = evaluate(SpendIntent(Decimal("0.25"), "USDC", "solana", ""), make_policy(), 0, 0)
        self.assertEqual(asset.action, "block")
        self.assertEqual(network.action, "block")

    def test_daily_budget(self):
        decision = evaluate(
            SpendIntent(Decimal("0.25"), "USDC", "base", ""),
            make_policy(daily_limit_usd=Decimal("1.00")),
            to_micro(Decimal("0.90")),
            0,
        )
        self.assertEqual(decision.action, "block")
        self.assertTrue(any("daily" in reason for reason in decision.reasons))

    def test_monthly_budget(self):
        decision = evaluate(
            SpendIntent(Decimal("0.25"), "USDC", "base", ""),
            make_policy(monthly_limit_usd=Decimal("2.00")),
            0,
            to_micro(Decimal("1.90")),
        )
        self.assertEqual(decision.action, "block")
        self.assertTrue(any("monthly" in reason for reason in decision.reasons))

    def test_unpriced_asks(self):
        decision = evaluate(SpendIntent(None, "USDC", "base", ""), make_policy(), 0, 0)
        self.assertEqual(decision.action, "ask")

    def test_atomic_conversion(self):
        self.assertEqual(atomic_to_usd("250000", "USDC"), Decimal("0.250000"))
        self.assertEqual(atomic_to_usd("250000000000000000", "OUSD"), Decimal("0.250000"))
        self.assertIsNone(atomic_to_usd("1", "ETH"))

    def test_detect_tool_intent(self):
        policy = make_policy()
        intent = detect_intent(
            "wallet_send",
            {
                "amount": "0.25",
                "asset": "USDC",
                "network": "base",
                "recipient": "0x1111111111111111111111111111111111111111",
                "purpose": "data",
            },
            policy,
        )
        self.assertIsNotNone(intent)
        self.assertEqual(intent.amount_usd, Decimal("0.250000"))
        self.assertEqual(intent.recipient, "0x1111111111111111111111111111111111111111")

    def test_detect_ignores_unrelated_tool(self):
        intent = detect_intent("read_file", {"path": "/tmp/x", "amount": 1}, make_policy())
        self.assertIsNone(intent)

    def test_terminal_cast_value(self):
        intent = intent_from_command(
            "cast send 0x2222222222222222222222222222222222222222 --value 1000000000000000 --rpc-url $RPC",
            make_policy(),
        )
        self.assertIsNotNone(intent)
        self.assertEqual(intent.recipient, "0x2222222222222222222222222222222222222222")
        self.assertIsNone(intent.amount_usd)

    def test_terminal_erc20_transfer(self):
        intent = intent_from_command(
            'cast send 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 "transfer(address,uint256)" '
            "0x2222222222222222222222222222222222222222 250000",
            make_policy(),
        )
        self.assertIsNotNone(intent)
        self.assertEqual(intent.amount_usd, Decimal("0.250000"))


if __name__ == "__main__":
    unittest.main()
