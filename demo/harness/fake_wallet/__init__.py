"""Demo-only wallet tool.

This registers a ``wallet_send`` tool that writes a marker file instead of
sending funds. It exists so a demo can prove that SpendWarden's pre_tool_call
hook stops the call before the tool handler runs.
"""

from __future__ import annotations

import json
import os

SCHEMA = {
    "name": "wallet_send",
    "description": "Demo-only: pretend to send a stablecoin transfer.",
    "parameters": {
        "type": "object",
        "properties": {
            "amount": {"type": "number"},
            "asset": {"type": "string"},
            "network": {"type": "string"},
            "recipient": {"type": "string"},
        },
        "required": ["amount", "asset", "network", "recipient"],
    },
}


def wallet_send(args: dict, **kwargs) -> str:
    marker = os.environ.get("SPENDWARDEN_WALLET_MARKER", "/tmp/spendwarden-wallet-ran")
    with open(marker, "a") as fh:
        fh.write(json.dumps(args) + "\n")
    return json.dumps({"ok": True, "tx_hash": "0x" + "de" * 32, "demo": True})


def register(ctx):
    ctx.register_tool(
        name="wallet_send",
        toolset="fake-wallet",
        schema=SCHEMA,
        handler=wallet_send,
    )
