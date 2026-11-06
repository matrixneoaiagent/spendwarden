"""SpendWarden — a spend policy firewall and ledger for Hermes agents.

The plugin adds four tools and one ``pre_tool_call`` hook. It never holds a
key, never signs, and never sends a transaction. It only decides whether a
proposed payment fits the user's policy and records what happened.
"""

from __future__ import annotations

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
    ctx.register_command(
        "spend",
        handler=service.slash_report,
        description="Show SpendWarden spend, remaining budget, and recent decisions",
        args_hint="[today|week|month|all]",
    )
    log.info("SpendWarden registered (ledger=%s)", ledger.path)
