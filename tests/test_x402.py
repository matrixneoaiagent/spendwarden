from __future__ import annotations

import base64
import json
import sys
import time
import unittest
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spendwarden.policy import Policy  # noqa: E402
from spendwarden.x402 import X402Error, inspect_challenge, inspect_payment, load_header  # noqa: E402

BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
PAY_TO = "0x1111111111111111111111111111111111111111"


def policy(**overrides):
    base = dict(
        mode="enforce",
        recipient_allowlist=(PAY_TO,),
        asset_allowlist=("USDC",),
        network_allowlist=("base",),
    )
    base.update(overrides)
    return Policy(**base)


def evaluate(intent, pol, _today=0, _month=0):
    from spendwarden.policy import evaluate as real_evaluate

    return real_evaluate(intent, pol, 0, 0)


def challenge(amount="250000", network="base", pay_to=PAY_TO, asset=BASE_USDC, **extra):
    return {
        "x402Version": 1,
        "accepts": [
            {
                "scheme": "exact",
                "network": network,
                "maxAmountRequired": amount,
                "resource": "https://api.example.com/market-data",
                "description": "one market data call",
                "mimeType": "application/json",
                "payTo": pay_to,
                "maxTimeoutSeconds": 60,
                "asset": asset,
                "extra": {"name": "USD Coin", "version": "2"},
            }
        ],
    }


class X402Tests(unittest.TestCase):
    def test_decode_base64_challenge(self):
        raw = base64.b64encode(json.dumps(challenge()).encode()).decode()
        result = inspect_challenge(raw, policy(), evaluate)
        self.assertTrue(result["ok"])
        self.assertEqual(result["terms"]["network"], "base")
        self.assertEqual(result["terms"]["asset"], "USDC")
        self.assertEqual(result["terms"]["amount_usd"], 0.25)
        self.assertEqual(result["terms"]["payTo"], PAY_TO)
        self.assertEqual(result["decision"]["action"], "allow")

    def test_json_string_challenge(self):
        result = inspect_challenge(json.dumps(challenge()), policy(), evaluate)
        self.assertEqual(result["terms"]["amount_usd"], 0.25)

    def test_preferred_network(self):
        doc = challenge()
        doc["accepts"].append(
            {
                **doc["accepts"][0],
                "network": "tempo",
                "asset": "OUSD",
                "maxAmountRequired": "100000000000000000",
            }
        )
        result = inspect_challenge(doc, policy(network_allowlist=("base", "tempo"), asset_allowlist=("USDC", "OUSD")), evaluate, preferred_network="tempo")
        self.assertEqual(result["terms"]["network"], "tempo")
        self.assertEqual(result["options_count"], 2)

    def test_unknown_recipient_asks(self):
        result = inspect_challenge(challenge(pay_to="0x2222222222222222222222222222222222222222"), policy(), evaluate)
        self.assertEqual(result["decision"]["action"], "ask")

    def test_bad_scheme_asks(self):
        doc = challenge()
        doc["accepts"][0]["scheme"] = "upto"
        result = inspect_challenge(doc, policy(), evaluate)
        self.assertEqual(result["decision"]["action"], "ask")
        self.assertTrue(any("scheme" in warning for warning in result["warnings"]))

    def test_zero_payto_asks(self):
        result = inspect_challenge(challenge(pay_to="0x0000000000000000000000000000000000000000"), policy(), evaluate)
        self.assertEqual(result["decision"]["action"], "ask")

    def test_http_resource_warns(self):
        doc = challenge()
        doc["accepts"][0]["resource"] = "http://api.example.com/data"
        result = inspect_challenge(doc, policy(), evaluate)
        self.assertTrue(any("HTTPS" in warning for warning in result["warnings"]))

    def test_signed_payment_expired(self):
        payload = {
            "x402Version": 1,
            "scheme": "exact",
            "network": "base",
            "payload": {
                "signature": "0x" + "11" * 65,
                "authorization": {
                    "from": "0x3333333333333333333333333333333333333333",
                    "to": PAY_TO,
                    "value": "250000",
                    "validAfter": "0",
                    "validBefore": str(int(time.time()) - 10),
                    "nonce": "0x" + "22" * 32,
                },
            },
        }
        result = inspect_payment(payload, policy(), evaluate, asset_hint="USDC")
        self.assertEqual(result["decision"]["action"], "block")
        self.assertTrue(result["terms"]["expired"])

    def test_bad_base64_raises(self):
        with self.assertRaises(X402Error):
            load_header("not-base64-%%%")


if __name__ == "__main__":
    unittest.main()
