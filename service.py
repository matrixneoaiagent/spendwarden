"""SpendWarden service: tools, hook, and human-readable reports."""

from __future__ import annotations

import json
import logging
import secrets
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from .policy import (
    Decision,
    Policy,
    SpendIntent,
    atomic_to_usd,
    detect_intent,
    evaluate,
    from_micro,
    normalize_asset,
    normalize_network,
    normalize_recipient,
    to_micro,
    usd,
)
from .storage import Entry, Ledger, next_reset_iso, period_start
from .x402 import X402Error, inspect_challenge, inspect_payment

log = logging.getLogger(__name__)


def _money(micro: int | None) -> float:
    return usd(int(micro or 0))


def _parse_usd(value: Any) -> Decimal:
    text = str(value).strip().replace("$", "").replace(",", "").replace("_", "")
    return Decimal(text).quantize(Decimal("0.000001"))


class SpendWarden:
    def __init__(self, ledger: Ledger, config_get: Callable[[str, Any], Any]):
        self.ledger = ledger
        self.config_get = config_get

    # ------------------------------------------------------------------ policy
    def policy(self) -> Policy:
        return Policy.from_config(self.config_get)

    def _totals(self) -> tuple[int, int]:
        return (
            self.ledger.spent_since(period_start("today")),
            self.ledger.spent_since(period_start("month")),
        )

    @staticmethod
    def _receipt() -> str:
        return "SW-" + secrets.token_hex(3).upper()

    def _evaluate(self, intent: SpendIntent) -> tuple[Decision, Policy, int, int]:
        policy = self.policy()
        today, month = self._totals()
        decision = evaluate(intent, policy, today, month, self._receipt())
        return decision, policy, today, month

    # --------------------------------------------------------------- formatting
    @staticmethod
    def describe(intent: SpendIntent, decision: Decision, policy: Policy) -> str:
        amount = intent.amount_usd
        amount_text = f"${usd(amount):,.2f}" if amount is not None else "an unpriced amount"
        where = intent.recipient or "(no recipient)"
        what = intent.asset or "an unspecified asset"
        if intent.network:
            what += f" on {intent.network}"
        head = f"{amount_text} in {what} to {where}"
        reasons = "; ".join(decision.reasons)
        if decision.action == "block":
            return (
                f"SpendWarden blocked {head}. Reasons: {reasons}. "
                "Adjust the policy or make this payment in a separate, explicitly approved step."
            )
        if decision.action == "ask":
            return (
                f"SpendWarden needs approval for {head}. Reasons: {reasons}. "
                "Approve this call only if the recipient and amount are what you expect."
            )
        return f"SpendWarden allows {head}. Reasons: {reasons}."

    def _result(
        self,
        intent: SpendIntent,
        decision: Decision,
        policy: Policy,
        today: int,
        month: int,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        remaining_today = max(0, to_micro(policy.daily_limit_usd) - today)
        remaining_month = max(0, to_micro(policy.monthly_limit_usd) - month)
        capacity_today = max(0, remaining_today - (to_micro(intent.amount_usd) if intent.amount_usd else 0))
        capacity_month = max(0, remaining_month - (to_micro(intent.amount_usd) if intent.amount_usd else 0))
        result: dict[str, Any] = {
            "ok": True,
            "decision": decision.to_dict(),
            "intent": {
                "amount_usd": usd(intent.amount_usd) if intent.amount_usd is not None else None,
                "asset": intent.asset,
                "network": intent.network,
                "recipient": intent.recipient,
                "purpose": intent.purpose,
                "source": intent.source,
                "tool_name": intent.tool_name,
            },
            "policy": {
                "mode": policy.mode,
                "daily_limit_usd": usd(policy.daily_limit_usd),
                "monthly_limit_usd": usd(policy.monthly_limit_usd),
                "per_call_limit_usd": usd(policy.per_call_limit_usd),
                "approval_threshold_usd": usd(policy.approval_threshold_usd),
                "recipient_allowlist": list(policy.recipient_allowlist),
                "asset_allowlist": list(policy.asset_allowlist),
                "network_allowlist": list(policy.network_allowlist),
            },
            "spent": {
                "today_usd": _money(today),
                "month_usd": _money(month),
            },
            "remaining": {
                "today_usd": _money(remaining_today),
                "month_usd": _money(remaining_month),
                "after_this_today_usd": _money(capacity_today),
                "after_this_month_usd": _money(capacity_month),
                "daily_reset_at": next_reset_iso("today"),
                "monthly_reset_at": next_reset_iso("month"),
            },
            "message": self.describe(intent, decision, policy),
        }
        if extra:
            result.update(extra)
        return result

    # ------------------------------------------------------------------- tools
    def tool_check(self, args: dict[str, Any], **kwargs: Any) -> str:
        try:
            intent = self._intent_from_args(args, tool_name="spend_check")
            decision, policy, today, month = self._evaluate(intent)
            self.ledger.record_event(
                kind="check",
                action=decision.action,
                receipt=decision.receipt,
                amount_micro=to_micro(intent.amount_usd) if intent.amount_usd else None,
                asset=intent.asset,
                network=intent.network,
                recipient=intent.recipient,
                tool_name="spend_check",
                session_id=str(kwargs.get("session_id") or ""),
                task_id=str(kwargs.get("task_id") or ""),
                reasons=decision.reasons,
                metadata={"purpose": intent.purpose},
            )
            return json.dumps(self._result(intent, decision, policy, today, month), ensure_ascii=False)
        except Exception as exc:  # tool handlers must never raise
            log.exception("spend_check failed")
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    def tool_record(self, args: dict[str, Any], **kwargs: Any) -> str:
        try:
            intent = self._intent_from_args(args, tool_name="spend_record")
            decision, policy, today, month = self._evaluate(intent)
            approved = bool(args.get("approved"))
            if intent.amount_usd is None:
                return json.dumps(
                    {"ok": False, "error": "unpriced", "message": "A spend record needs a USD amount."},
                    ensure_ascii=False,
                )
            payment_id = str(args.get("payment_id") or args.get("tx_hash") or "").strip()
            if not payment_id:
                return json.dumps(
                    {
                        "ok": False,
                        "error": "idempotency_key_required",
                        "message": "Provide payment_id or tx_hash so a retry cannot double-count this payment.",
                    },
                    ensure_ascii=False,
                )

            if decision.action == "block":
                status = "over_budget"
                warning = "recorded despite a policy block: " + "; ".join(decision.reasons)
            elif decision.action == "ask" and not approved:
                status = "unapproved"
                warning = "recorded without approval: " + "; ".join(decision.reasons)
            else:
                status = "spent"
                warning = ""

            entry = Entry(
                amount_micro=to_micro(intent.amount_usd),
                asset=intent.asset,
                network=intent.network,
                recipient=intent.recipient,
                purpose=intent.purpose,
                tool_name=intent.tool_name,
                session_id=str(kwargs.get("session_id") or ""),
                task_id=str(kwargs.get("task_id") or ""),
                tx_hash=str(args.get("tx_hash") or ""),
                payment_id=payment_id,
                metadata={
                    "approved": approved,
                    "decision_receipt": decision.receipt,
                    "policy_action": decision.action,
                    "policy_reasons": decision.reasons,
                    "source": intent.source,
                },
                status=status,
            )
            row, duplicate = self.ledger.record_spend(entry)
            today_after = self.ledger.spent_since(period_start("today"))
            month_after = self.ledger.spent_since(period_start("month"))
            self.ledger.record_event(
                kind="record",
                action=decision.action,
                receipt=decision.receipt,
                amount_micro=entry.amount_micro,
                asset=entry.asset,
                network=entry.network,
                recipient=entry.recipient,
                tool_name="spend_record",
                session_id=entry.session_id,
                task_id=entry.task_id,
                reasons=[status, *decision.reasons],
                metadata={"payment_id": payment_id, "tx_hash": entry.tx_hash, "duplicate": duplicate, "status": status},
            )
            return json.dumps(
                {
                    "ok": True,
                    "duplicate": duplicate,
                    "status": row.get("status", status),
                    "warning": warning,
                    "decision": decision.to_dict(),
                    "entry": row,
                    "receipt": decision.receipt,
                    "spent": {"today_usd": _money(today_after), "month_usd": _money(month_after)},
                    "remaining": {
                        "today_usd": _money(max(0, to_micro(policy.daily_limit_usd) - today_after)),
                        "month_usd": _money(max(0, to_micro(policy.monthly_limit_usd) - month_after)),
                    },
                },
                ensure_ascii=False,
            )
        except Exception as exc:
            log.exception("spend_record failed")
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    def tool_report(self, args: dict[str, Any], **kwargs: Any) -> str:
        try:
            period = str(args.get("period") or "today").lower()
            limit = int(args.get("limit") or 10)
            report = self.ledger.report(period, limit)
            report["ok"] = True
            policy = self.policy()
            today, month = self._totals()
            report["policy"] = {
                "mode": policy.mode,
                "daily_limit_usd": usd(policy.daily_limit_usd),
                "monthly_limit_usd": usd(policy.monthly_limit_usd),
                "per_call_limit_usd": usd(policy.per_call_limit_usd),
                "approval_threshold_usd": usd(policy.approval_threshold_usd),
            }
            report["remaining"] = {
                "today_usd": _money(max(0, to_micro(policy.daily_limit_usd) - today)),
                "month_usd": _money(max(0, to_micro(policy.monthly_limit_usd) - month)),
            }
            report["total_usd"] = _money(report.pop("total_micro"))
            for row in report["top_recipients"]:
                row["total_usd"] = _money(row.pop("total"))
            for row in report["recent"]:
                row["amount_usd"] = _money(row.pop("amount_micro"))
            return json.dumps(report, ensure_ascii=False, default=str)
        except Exception as exc:
            log.exception("spend_report failed")
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    def tool_x402(self, args: dict[str, Any], **kwargs: Any) -> str:
        try:
            challenge = args.get("challenge") or args.get("header") or args.get("payload")
            if not challenge:
                return json.dumps({"ok": False, "error": "challenge is required"}, ensure_ascii=False)
            policy = self.policy()

            def evaluate_with_totals(intent: SpendIntent, pol: Policy, _today: int, _month: int) -> Decision:
                today, month = self._totals()
                return evaluate(intent, pol, today, month, self._receipt())

            mode = str(args.get("mode") or "challenge").lower()
            if mode == "payment":
                result = inspect_payment(
                    challenge,
                    policy,
                    evaluate_with_totals,
                    now=int(datetime.now(timezone.utc).timestamp()),
                    asset_hint=str(args.get("asset") or ""),
                )
            else:
                result = inspect_challenge(
                    challenge,
                    policy,
                    evaluate_with_totals,
                    preferred_network=str(args.get("network") or "") or None,
                )
            decision = result.get("decision") or {}
            self.ledger.record_event(
                kind="x402",
                action=str(decision.get("action") or "unknown"),
                receipt=str(decision.get("receipt") or ""),
                amount_micro=to_micro(Decimal(str(result["terms"].get("amount_usd")))) if result.get("terms", {}).get("amount_usd") is not None else None,
                asset=str(result.get("terms", {}).get("asset") or ""),
                network=str(result.get("terms", {}).get("network") or ""),
                recipient=str(result.get("terms", {}).get("payTo") or result.get("terms", {}).get("to") or ""),
                tool_name="x402_inspect",
                session_id=str(kwargs.get("session_id") or ""),
                task_id=str(kwargs.get("task_id") or ""),
                reasons=list(decision.get("reasons") or []),
                metadata={"mode": mode, "resource": result.get("terms", {}).get("resource")},
            )
            policy_block = {
                "mode": policy.mode,
                "daily_limit_usd": usd(policy.daily_limit_usd),
                "monthly_limit_usd": usd(policy.monthly_limit_usd),
                "per_call_limit_usd": usd(policy.per_call_limit_usd),
                "approval_threshold_usd": usd(policy.approval_threshold_usd),
                "recipient_allowlist": list(policy.recipient_allowlist),
            }
            result["policy"] = policy_block
            return json.dumps(result, ensure_ascii=False, default=str)
        except X402Error as exc:
            return json.dumps({"ok": False, "error": f"x402 decode failed: {exc}"}, ensure_ascii=False)
        except Exception as exc:
            log.exception("x402_inspect failed")
            return json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False)

    # -------------------------------------------------------------------- hook
    def pre_tool_call(
        self,
        tool_name: str,
        args: dict[str, Any],
        task_id: str = "",
        **kwargs: Any,
    ) -> dict[str, str] | None:
        try:
            policy = self.policy()
            intent = detect_intent(
                tool_name,
                args,
                policy,
                session_id=str(kwargs.get("session_id") or ""),
                task_id=task_id,
            )
            if intent is None:
                return None
            decision, policy, today, month = self._evaluate(intent)
            self.ledger.record_event(
                kind="hook",
                action=decision.action,
                receipt=decision.receipt,
                amount_micro=to_micro(intent.amount_usd) if intent.amount_usd else None,
                asset=intent.asset,
                network=intent.network,
                recipient=intent.recipient,
                tool_name=tool_name,
                session_id=str(kwargs.get("session_id") or ""),
                task_id=task_id,
                reasons=decision.reasons,
                metadata={"purpose": intent.purpose, "mode": policy.mode},
            )
            if policy.mode != "enforce":
                return None
            if decision.action == "block":
                return {"action": "block", "message": self.describe(intent, decision, policy)}
            if decision.action == "ask":
                return {"action": "approve", "message": self.describe(intent, decision, policy)}
            return None
        except Exception:
            log.exception("SpendWarden hook failed")
            try:
                fail_closed = self.policy().fail_closed
            except Exception:
                fail_closed = False
            if fail_closed:
                return {
                    "action": "block",
                    "message": "SpendWarden failed closed because its policy check errored. Fix the plugin before retrying.",
                }
            return None

    # ------------------------------------------------------------- slash command
    def slash_report(self, raw_args: str) -> str:
        period = (raw_args or "today").strip().lower() or "today"
        if period not in {"today", "week", "month", "all"}:
            return "Usage: /spend [today|week|month|all]"
        try:
            report = json.loads(self.tool_report({"period": period, "limit": 5}))
            if not report.get("ok", True):
                return f"SpendWarden error: {report.get('error')}"
            lines = [
                f"SpendWarden · {period}",
                f"Spent: ${report['total_usd']:.2f} across {report['count']} payment(s)",
                f"Today remaining: ${report['remaining']['today_usd']:.2f} · Month remaining: ${report['remaining']['month_usd']:.2f}",
                f"Mode: {report['policy']['mode']} · per-call ${report['policy']['per_call_limit_usd']:.2f} · approval at ${report['policy']['approval_threshold_usd']:.2f}",
            ]
            decisions = report.get("decisions") or {}
            if decisions:
                lines.append(
                    "Decisions: "
                    + ", ".join(f"{key} {value}" for key, value in sorted(decisions.items()))
                )
            if report.get("top_recipients"):
                lines.append("Top recipients:")
                for row in report["top_recipients"][:3]:
                    lines.append(f"  {row['recipient'][:16]}…  ${row['total_usd']:.2f}  ({row['count']})")
            return "\n".join(lines)
        except Exception as exc:
            log.exception("/spend failed")
            return f"SpendWarden error: {exc}"

    # ------------------------------------------------------------------ helpers
    def _intent_from_args(self, args: dict[str, Any], tool_name: str) -> SpendIntent:
        if not isinstance(args, dict):
            raise ValueError("arguments must be an object")
        amount_usd: Decimal | None = None
        raw_amount = ""
        asset = normalize_asset(str(args.get("asset") or ""))
        network = normalize_network(str(args.get("network") or ""))
        recipient = normalize_recipient(str(args.get("recipient") or args.get("payTo") or args.get("to") or ""))

        if args.get("amount_usd") not in (None, ""):
            amount_usd = _parse_usd(args["amount_usd"])
            raw_amount = str(args["amount_usd"])
        elif args.get("amount_atomic") not in (None, ""):
            if not asset:
                raise ValueError("amount_atomic requires an asset")
            amount_usd = atomic_to_usd(args["amount_atomic"], asset)
            raw_amount = str(args["amount_atomic"])
        elif args.get("amount") not in (None, ""):
            try:
                amount_usd = _parse_usd(args["amount"])
                raw_amount = str(args["amount"])
            except (InvalidOperation, ValueError) as exc:
                raise ValueError(f"invalid amount: {args['amount']!r}") from exc
        elif args.get("maxAmountRequired") not in (None, ""):
            if not asset:
                raise ValueError("maxAmountRequired requires an asset")
            amount_usd = atomic_to_usd(args["maxAmountRequired"], asset)
            raw_amount = str(args["maxAmountRequired"])

        if amount_usd is None:
            raise ValueError("provide amount_usd or amount_atomic + asset")
        return SpendIntent(
            amount_usd=amount_usd,
            asset=asset,
            network=network,
            recipient=recipient,
            purpose=str(args.get("purpose") or args.get("description") or "")[:240],
            tool_name=tool_name,
            source="tool",
            raw_amount=raw_amount,
        )
