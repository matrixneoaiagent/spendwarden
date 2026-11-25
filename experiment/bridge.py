"""Bridge from the experiment harness to SpendWarden's real policy engine.

The experiment deliberately imports ``policy.py`` and ``storage.py`` from the
repository root by path. That keeps the plugin untouched, avoids installing
Hermes, and means the numbers in the paper come from the same deterministic
code path the plugin uses at runtime (``detect_intent`` + ``evaluate``).

Only the Hermes registration layer (``__init__.py``) and the tool wrappers
(``service.py``, which uses relative imports) are bypassed. ``Gate`` below
reproduces the check/record order of ``service.SpendWarden`` with a
deterministic receipt so runs are byte-reproducible.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]


def _load(module_name: str, filename: str):
    path = REPO_ROOT / filename
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:  # pragma: no cover - corrupt checkout
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_policy = _load("spendwarden_policy", "policy.py")
_storage = _load("spendwarden_storage", "storage.py")

Policy = _policy.Policy
SpendIntent = _policy.SpendIntent
Decision = _policy.Decision
detect_intent = _policy.detect_intent
evaluate = _policy.evaluate
to_micro = _policy.to_micro
usd = _policy.usd
human_usd = _policy.human_usd
Ledger = _storage.Ledger
Entry = _storage.Entry
period_start = _storage.period_start

DEFAULT_POLICY = dict(
    mode="enforce",
    daily_limit_usd=Decimal("10.00"),
    monthly_limit_usd=Decimal("100.00"),
    per_call_limit_usd=Decimal("2.00"),
    approval_threshold_usd=Decimal("0.50"),
    unknown_recipient_action="ask",
)

ASSET = "USDC"
NETWORK = "base"


def receipt_for(payment_id: str) -> str:
    """Deterministic stand-in for the service's random SW-XXXXXX receipt."""
    return "SW-" + hashlib.sha256(payment_id.encode()).hexdigest()[:6].upper()


def make_policy(**overrides: Any) -> Policy:
    values = dict(DEFAULT_POLICY)
    values.update(overrides)
    return Policy(**values)


class Gate:
    """A single-wallet SpendWarden gate: check, then execute, then record."""

    def __init__(self, db_path: str | Path, policy: Policy | None = None):
        self.ledger = Ledger(db_path)
        self.policy = policy or make_policy()

    def totals(self) -> tuple[int, int]:
        return (
            self.ledger.spent_since(period_start("today")),
            self.ledger.spent_since(period_start("month")),
        )

    def inspect(self, tool_name: str, args: dict[str, Any]) -> tuple[SpendIntent | None, Decision | None]:
        """Run the plugin's real detector and policy evaluation for one call.

        Returns ``(None, None)`` when the detector finds no payment intent.
        In the real plugin that call is allowed through: the hook only sees
        payment-shaped calls. That blind spot is one of the things we measure.
        """
        intent = detect_intent(tool_name, args, self.policy)
        if intent is None:
            return None, None
        today, month = self.totals()
        payment_id = str(args.get("payment_id") or args.get("tx_hash") or "")
        decision = evaluate(intent, self.policy, today, month, receipt=receipt_for(payment_id))
        return intent, decision

    def record(self, intent: SpendIntent, decision: Decision, payment_id: str, approved: bool = False) -> str:
        """Record an executed payment with the same status rules as the plugin."""
        if decision.action == "block":
            status = "over_budget"
        elif decision.action == "ask" and not approved:
            status = "unapproved"
        else:
            status = "spent"
        self.ledger.record_spend(
            Entry(
                amount_micro=to_micro(intent.amount_usd),
                asset=intent.asset,
                network=intent.network,
                recipient=intent.recipient,
                purpose=intent.purpose,
                tool_name=intent.tool_name,
                payment_id=payment_id,
                metadata={
                    "approved": approved,
                    "decision_receipt": decision.receipt,
                    "policy_action": decision.action,
                    "policy_reasons": decision.reasons,
                    "source": "experiment",
                },
                status=status,
            )
        )
        return status
