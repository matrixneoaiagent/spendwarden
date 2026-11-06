"""SpendWarden — a spend policy firewall and ledger for Hermes agents.

The plugin adds four tools and one ``pre_tool_call`` hook. It never holds a
key, never signs, and never sends a transaction. It only decides whether a
proposed payment fits the user's policy and records what happened.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from . import schemas
from .service import SpendWarden
from .storage import Ledger

log = logging.getLogger(__name__)


def _data_dir() -> Path:
    try:
        from plugins.plugin_storage import plugin_data_dir

        return Path(plugin_data_dir("spendwarden"))
    except Exception:
        # Standalone/doctor fallback: keep state out of the install tree.
        import os

        home = Path(os.environ.get("HERMES_HOME") or (Path.home() / ".hermes"))
        path = home / "plugin-data" / "spendwarden"
        path.mkdir(parents=True, exist_ok=True)
        return path


def register(ctx):
    data_dir = _data_dir()
    ledger = Ledger(data_dir / "ledger.db")
    service = SpendWarden(ledger, ctx.get_config)

    ctx.register_tool(
        name="spend_check",
        toolset="spendwarden",
        schema=schemas.SPEND_CHECK,
        handler=service.tool_check,
    )
    ctx.register_tool(
        name="spend_record",
        toolset="spendwarden",
        schema=schemas.SPEND_RECORD,
        handler=service.tool_record,
    )
    ctx.register_tool(
        name="spend_report",
        toolset="spendwarden",
        schema=schemas.SPEND_REPORT,
        handler=service.tool_report,
    )
    ctx.register_tool(
        name="x402_inspect",
        toolset="spendwarden",
        schema=schemas.X402_INSPECT,
        handler=service.tool_x402,
    )

    ctx.register_hook("pre_tool_call", service.pre_tool_call)

    def _setup_cli(subparser):
        subs = subparser.add_subparsers(dest="spendwarden_command")
        report = subs.add_parser("report", help="Show spend totals and remaining budget")
        report.add_argument("--period", default="today", choices=["today", "week", "month", "all"])
        report.add_argument("--limit", type=int, default=10)
        subs.add_parser("policy", help="Show the active policy")
        receipts = subs.add_parser("receipts", help="Show recent recorded payments")
        receipts.add_argument("--limit", type=int, default=10)
        subparser.set_defaults(func=_cli)

    def _cli(args):
        sub = getattr(args, "spendwarden_command", None)
        if sub == "report":
            report = json.loads(service.tool_report({"period": args.period, "limit": args.limit}))
            if not report.get("ok"):
                print(f"SpendWarden error: {report.get('error')}")
                return
            print(f"SpendWarden · {report['period']}")
            print(f"Spent: ${report['total_usd']:.2f} across {report['count']} payment(s)")
            print(f"Today remaining: ${report['remaining']['today_usd']:.2f} · Month remaining: ${report['remaining']['month_usd']:.2f}")
            print(f"Mode: {report['policy']['mode']} · per-call ${report['policy']['per_call_limit_usd']:.2f} · approval at ${report['policy']['approval_threshold_usd']:.2f}")
            for row in report.get("recent", [])[: args.limit]:
                print(f"  {row['created_at']}  ${row['amount_usd']:.2f}  {row['recipient'][:20] or '(no recipient)'}")
        elif sub == "policy":
            policy = service.policy()
            print(f"mode: {policy.mode}")
            print(f"daily_limit_usd: {policy.daily_limit_usd}")
            print(f"monthly_limit_usd: {policy.monthly_limit_usd}")
            print(f"per_call_limit_usd: {policy.per_call_limit_usd}")
            print(f"approval_threshold_usd: {policy.approval_threshold_usd}")
            print(f"unknown_recipient_action: {policy.unknown_recipient_action}")
            print(f"recipient_allowlist: {list(policy.recipient_allowlist)}")
            print(f"asset_allowlist: {list(policy.asset_allowlist)}")
            print(f"network_allowlist: {list(policy.network_allowlist)}")
        elif sub == "receipts":
            for row in ledger.recent_entries(args.limit):
                print(f"{row['created_at']}  ${int(row['amount_micro']) / 1_000_000:.2f}  {row['recipient'][:24] or '(no recipient)'}  {row['purpose'][:50]}")
        else:
            print("Usage: hermes spendwarden <report|policy|receipts>")

    ctx.register_cli_command(
        name="spendwarden",
        help="SpendWarden spend policy and ledger",
        setup_fn=_setup_cli,
        handler_fn=_cli,
    )

    ctx.register_command(
        "spend",
        handler=service.slash_report,
        description="Show SpendWarden spend, remaining budget, and recent decisions",
        args_hint="[today|week|month|all]",
    )
    log.info("SpendWarden registered (ledger=%s)", ledger.path)
