#!/usr/bin/env python3
"""A deterministic, no-network demo of SpendWarden.

Run from the repository root:

    python3 demo/demo.py

For a screen recording, keep the default pauses. Use --fast in CI.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import tempfile
import textwrap
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from spendwarden.service import SpendWarden  # noqa: E402
from spendwarden.storage import Ledger  # noqa: E402

PAY_TO = "0x1111111111111111111111111111111111111111"
BASE_USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
RESET = "\033[0m"


def line(text: str = "") -> None:
    print(text, flush=True)


def step(number: int, title: str, pause: float) -> None:
    line()
    line(f"{CYAN}{'─' * 68}{RESET}")
    line(f"{BOLD}{number}. {title}{RESET}")
    line(f"{CYAN}{'─' * 68}{RESET}")
    time.sleep(pause)


def show_decision(result: dict, pause: float) -> None:
    decision = result["decision"]
    color = {"allow": GREEN, "ask": YELLOW, "block": RED}.get(decision["action"], RESET)
    line(f"  decision : {color}{decision['action'].upper()}{RESET}  ({decision['receipt']})")
    for reason in decision["reasons"]:
        line(f"  reason   : {reason}")
    line(f"  today    : ${result['spent']['today_usd']:.2f} spent, ${result['remaining']['today_usd']:.2f} left")
    line(f"  month    : ${result['spent']['month_usd']:.2f} spent, ${result['remaining']['month_usd']:.2f} left")
    time.sleep(pause)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fast", action="store_true", help="no pauses (CI)")
    args = parser.parse_args()
    pause = 0.0 if args.fast else 0.7

    tmp = tempfile.TemporaryDirectory()
    ledger = Ledger(Path(tmp.name) / "ledger.db")
    config = {
        "mode": "enforce",
        "daily_limit_usd": 2.0,
        "monthly_limit_usd": 20.0,
        "per_call_limit_usd": 1.0,
        "approval_threshold_usd": 0.30,
        "recipient_allowlist": [PAY_TO],
        "asset_allowlist": ["USDC", "OUSD"],
        "network_allowlist": ["base", "tempo"],
        "watch_terminal": True,
    }
    service = SpendWarden(ledger, lambda key, default=None: config.get(key, default))

    line(f"{BOLD}SpendWarden{RESET} — a spend policy firewall for agents that can move money")
    line(f"{DIM}policy: $2/day · $1/call · approval at $0.30 · enforce mode{RESET}")
    time.sleep(pause)

    step(1, "A small payment to an allowlisted x402 endpoint", pause)
    check = json.loads(
        service.tool_check(
            {
                "amount_usd": 0.25,
                "asset": "USDC",
                "network": "base",
                "recipient": PAY_TO,
                "purpose": "market data call",
            }
        )
    )
    show_decision(check, pause * 1.5)

    step(2, "The agent tries a $5.00 transfer — blocked before the wallet runs", pause)
    block = service.pre_tool_call(
        "wallet_send",
        {"amount": 5.0, "asset": "USDC", "network": "base", "recipient": PAY_TO},
        task_id="demo",
    )
    line(f"  hook says: {RED}{block['action'].upper()}{RESET}")
    line(textwrap.fill(block["message"], width=72, initial_indent="  ", subsequent_indent="  "))
    time.sleep(pause * 1.5)

    step(3, "A $0.75 payment is inside the cap but above the approval line", pause)
    ask = service.pre_tool_call(
        "wallet_send",
        {"amount": 0.75, "asset": "USDC", "network": "base", "recipient": PAY_TO},
        task_id="demo",
    )
    line(f"  hook says: {YELLOW}{ask['action'].upper()}{RESET}")
    line(f"  {ask['message']}")
    time.sleep(pause * 1.5)

    step(4, "The $0.25 payment succeeds; the ledger records it once", pause)
    record = json.loads(
        service.tool_record(
            {
                "amount_usd": 0.25,
                "asset": "USDC",
                "network": "base",
                "recipient": PAY_TO,
                "purpose": "market data call",
                "payment_id": "demo-payment-1",
                "tx_hash": "0x" + "ab" * 32,
            }
        )
    )
    line(f"  receipt  : {GREEN}{record['receipt']}{RESET}")
    line(f"  duplicate: {record['duplicate']}")
    line(f"  today    : ${record['spent']['today_usd']:.2f} spent")
    retry = json.loads(
        service.tool_record(
            {
                "amount_usd": 0.25,
                "asset": "USDC",
                "network": "base",
                "recipient": PAY_TO,
                "purpose": "market data call",
                "payment_id": "demo-payment-1",
            }
        )
    )
    line(f"  retry    : {DIM}duplicate={retry['duplicate']} — the ledger did not double-count{RESET}")
    time.sleep(pause * 1.5)

    step(5, "Decode an x402 challenge without signing anything", pause)
    challenge = {
        "x402Version": 1,
        "accepts": [
            {
                "scheme": "exact",
                "network": "base",
                "maxAmountRequired": "250000",
                "resource": "https://api.example.com/market-data",
                "description": "one market data call",
                "payTo": PAY_TO,
                "maxTimeoutSeconds": 60,
                "asset": BASE_USDC,
                "extra": {"name": "USD Coin", "version": "2"},
            }
        ],
    }
    header = base64.b64encode(json.dumps(challenge).encode()).decode()
    inspected = json.loads(service.tool_x402({"challenge": header}))
    terms = inspected["terms"]
    line(f"  network  : {terms['network']}")
    line(f"  asset    : {terms['asset']} ({terms['amount_atomic']} atomic)")
    line(f"  amount   : ${terms['amount_usd']:.2f}")
    line(f"  payTo    : {terms['payTo']}")
    line(f"  resource : {terms['resource']}")
    decision = inspected["decision"]
    line(f"  decision : {GREEN}{decision['action'].upper()}{RESET}  ({decision['receipt']})")
    time.sleep(pause * 1.5)

    step(6, "What the user sees with /spend", pause)
    for row in service.slash_report("today").splitlines():
        line(f"  {row}")
    time.sleep(pause)

    line()
    line(f"{GREEN}{BOLD}No key. No signature. No network. Just a check before the money moves.{RESET}")
    line()
    tmp.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
