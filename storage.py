"""SQLite ledger for SpendWarden.

One file, two tables: ``entries`` is the spend ledger; ``events`` is the
decision log (checks, blocks, approvals, x402 inspections). Amounts are
integer micro-USD. Every write is its own short transaction so the plugin is
safe to call from the agent loop and from a hook. The journal uses DELETE
rather than WAL: Hermes may run against a SQLite build with the WAL-reset
corruption bug, and this database is small enough that DELETE is plenty.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ISO = "%Y-%m-%dT%H:%M:%S+00:00"


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime(ISO)


def period_start(period: str) -> str:
    now = datetime.now(timezone.utc)
    period = (period or "today").lower()
    if period == "all":
        return "1970-01-01T00:00:00+00:00"
    if period == "week":
        from datetime import timedelta

        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start = start - timedelta(days=start.weekday())
        return start.strftime(ISO)
    if period == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).strftime(ISO)
    return now.replace(hour=0, minute=0, second=0, microsecond=0).strftime(ISO)


def next_reset_iso(period: str) -> str:
    now = datetime.now(timezone.utc)
    if period == "month":
        year, month = (now.year + 1, 1) if now.month == 12 else (now.year, now.month + 1)
        return datetime(year, month, 1, tzinfo=timezone.utc).strftime(ISO)
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta

    return (tomorrow + timedelta(days=1)).strftime(ISO)


@dataclass
class Entry:
    amount_micro: int
    asset: str = ""
    network: str = ""
    recipient: str = ""
    purpose: str = ""
    tool_name: str = ""
    session_id: str = ""
    task_id: str = ""
    tx_hash: str = ""
    payment_id: str = ""
    metadata: dict[str, Any] | None = None
    status: str = "spent"


class Ledger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=DELETE")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def _init(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS entries (
                    id TEXT PRIMARY KEY,
                    payment_id TEXT UNIQUE,
                    created_at TEXT NOT NULL,
                    amount_micro INTEGER NOT NULL,
                    asset TEXT NOT NULL DEFAULT '',
                    network TEXT NOT NULL DEFAULT '',
                    recipient TEXT NOT NULL DEFAULT '',
                    purpose TEXT NOT NULL DEFAULT '',
                    tool_name TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL DEFAULT '',
                    task_id TEXT NOT NULL DEFAULT '',
                    tx_hash TEXT NOT NULL DEFAULT '',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    status TEXT NOT NULL DEFAULT 'spent'
                );
                CREATE INDEX IF NOT EXISTS idx_entries_created ON entries(created_at);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    action TEXT NOT NULL,
                    receipt TEXT NOT NULL DEFAULT '',
                    amount_micro INTEGER,
                    asset TEXT NOT NULL DEFAULT '',
                    network TEXT NOT NULL DEFAULT '',
                    recipient TEXT NOT NULL DEFAULT '',
                    tool_name TEXT NOT NULL DEFAULT '',
                    session_id TEXT NOT NULL DEFAULT '',
                    task_id TEXT NOT NULL DEFAULT '',
                    reasons TEXT NOT NULL DEFAULT '[]',
                    metadata TEXT NOT NULL DEFAULT '{}'
                );
                CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
                """
            )

    def spent_since(self, start_iso: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(amount_micro), 0) AS total FROM entries "
                "WHERE status IN ('spent', 'over_budget', 'unapproved') AND created_at >= ?",
                (start_iso,),
            ).fetchone()
            return int(row["total"] or 0)

    def record_event(
        self,
        *,
        kind: str,
        action: str,
        receipt: str = "",
        amount_micro: int | None = None,
        asset: str = "",
        network: str = "",
        recipient: str = "",
        tool_name: str = "",
        session_id: str = "",
        task_id: str = "",
        reasons: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events (created_at, kind, action, receipt, amount_micro, asset, "
                "network, recipient, tool_name, session_id, task_id, reasons, metadata) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    now_iso(),
                    kind,
                    action,
                    receipt,
                    amount_micro,
                    asset,
                    network,
                    recipient,
                    tool_name,
                    session_id,
                    task_id,
                    json.dumps(reasons or [], ensure_ascii=False),
                    json.dumps(metadata or {}, ensure_ascii=False, default=str),
                ),
            )

    def record_spend(self, entry: Entry) -> tuple[dict[str, Any], bool]:
        """Insert a spend. Returns ``(row, duplicate)``.

        The unique ``payment_id`` is the idempotency key: a retry after a
        timeout cannot double-count a payment.
        """
        with self._connect() as conn:
            if entry.payment_id:
                existing = conn.execute(
                    "SELECT * FROM entries WHERE payment_id = ?", (entry.payment_id,)
                ).fetchone()
                if existing:
                    return dict(existing), True
            conn.execute("BEGIN IMMEDIATE")
            try:
                if entry.payment_id:
                    existing = conn.execute(
                        "SELECT * FROM entries WHERE payment_id = ?", (entry.payment_id,)
                    ).fetchone()
                    if existing:
                        conn.commit()
                        return dict(existing), True
                entry_id = str(uuid.uuid4())
                created = now_iso()
                conn.execute(
                    "INSERT INTO entries (id, payment_id, created_at, amount_micro, asset, network, "
                    "recipient, purpose, tool_name, session_id, task_id, tx_hash, metadata, status) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        entry_id,
                        entry.payment_id or None,
                        created,
                        int(entry.amount_micro),
                        entry.asset,
                        entry.network,
                        entry.recipient,
                        entry.purpose,
                        entry.tool_name,
                        entry.session_id,
                        entry.task_id,
                        entry.tx_hash,
                        json.dumps(entry.metadata or {}, ensure_ascii=False, default=str),
                        entry.status,
                    ),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            row = conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,)).fetchone()
            return dict(row), False

    def recent_entries(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM entries ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (max(1, min(int(limit), 50)),),
            ).fetchall()
            return [dict(row) for row in rows]

    def report(self, period: str = "today", limit: int = 10) -> dict[str, Any]:
        start = period_start(period)
        with self._connect() as conn:
            total = conn.execute(
                "SELECT COALESCE(SUM(amount_micro), 0) AS total, COUNT(*) AS count "
                "FROM entries WHERE status IN ('spent', 'over_budget', 'unapproved') AND created_at >= ?",
                (start,),
            ).fetchone()
            top = conn.execute(
                "SELECT recipient, COUNT(*) AS count, COALESCE(SUM(amount_micro), 0) AS total "
                "FROM entries WHERE status IN ('spent', 'over_budget', 'unapproved') AND created_at >= ? "
                "GROUP BY recipient ORDER BY total DESC LIMIT 5",
                (start,),
            ).fetchall()
            decisions = conn.execute(
                "SELECT action, COUNT(*) AS count FROM events "
                "WHERE created_at >= ? AND kind IN ('check', 'hook', 'x402') "
                "GROUP BY action",
                (start,),
            ).fetchall()
            recent = conn.execute(
                "SELECT * FROM entries WHERE created_at >= ? "
                "ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (start, max(1, min(int(limit), 50))),
            ).fetchall()
            status_rows = conn.execute(
                "SELECT status, COUNT(*) AS count FROM entries WHERE created_at >= ? GROUP BY status",
                (start,),
            ).fetchall()
        return {
            "period": (period or "today").lower(),
            "start": start,
            "total_micro": int(total["total"] or 0),
            "count": int(total["count"] or 0),
            "top_recipients": [dict(row) for row in top],
            "decisions": {row["action"]: row["count"] for row in decisions},
            "status_counts": {row["status"]: row["count"] for row in status_rows},
            "recent": [dict(row) for row in recent],
        }
