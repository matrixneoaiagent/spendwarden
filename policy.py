"""Deterministic spending policy for SpendWarden.

This module is deliberately free of Hermes imports so it can be unit-tested
without a running agent. Money is handled as integer micro-USD (1e-6 USD) to
avoid binary-float rounding in budgets.
"""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Callable, Iterable

MICRO = Decimal("0.000001")

STABLE_SYMBOLS = {"USDC", "USDT", "OUSD", "DAI", "PYUSD", "USA", "USAT"}
ASSET_DECIMALS = {
    "USDC": 6,
    "USDT": 6,
    "OUSD": 18,
    "DAI": 18,
    "PYUSD": 6,
    "USA": 6,
    "USAT": 6,
    "ETH": 18,
    "BNB": 18,
    "SOL": 9,
    "NEAR": 24,
    "BTC": 8,
}
KNOWN_TOKEN_SYMBOLS = {
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": "USDC",
    "0x036cbd53842c5426634e7929541ec2318f3dcf7e": "USDC",
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": "USDC",
    "0xaf88d065e77c8cc2239327c5edb3a432268e5831": "USDC",
    "0x0b2c639c533813f4aa9d7837caf62653d097ff85": "USDC",
    "0x2791bca1f2de4661ed88a30c99a7a9449aa84174": "USDC",
    "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": "USDC",
}
NETWORK_ALIASES = {
    "eip155:8453": "base",
    "8453": "base",
    "base-mainnet": "base",
    "eip155:84532": "base-sepolia",
    "84532": "base-sepolia",
    "base-sepolia-testnet": "base-sepolia",
    "eip155:56": "bsc",
    "56": "bsc",
    "bnb": "bsc",
    "binance": "bsc",
    "eip155:1": "ethereum",
    "1": "ethereum",
    "eth": "ethereum",
    "eip155:42161": "arbitrum",
    "42161": "arbitrum",
    "eip155:10": "optimism",
    "10": "optimism",
    "eip155:137": "polygon",
    "137": "polygon",
    "eip155:42220": "celo",
    "42220": "celo",
    "solana-mainnet": "solana",
    "near-mainnet": "near",
}
DEFAULT_WATCHED_TOOLS = (
    "wallet_*",
    "x402_*",
    "*pay*",
    "*transfer*",
    "*swap*",
    "*bridge*",
    "*checkout*",
    "*purchase*",
    "*send*",
    "*withdraw*",
    "*deposit*",
    "*invoice*",
    "*tip*",
    "*buy*",
    "spend_*",
)
OWN_TOOLS = {"spend_check", "spend_record", "spend_report", "x402_inspect"}

_RECIPIENT_KEYS = ("payTo", "pay_to", "recipient", "destination", "to_address", "to")
_AMOUNT_KEYS = (
    "amount_usd",
    "usd_amount",
    "amount",
    "value",
    "maxAmountRequired",
    "max_amount_required",
    "price",
)
_ATOMIC_KEYS = ("amount_atomic", "atomic_amount", "maxAmountRequired", "max_amount_required")


def to_micro(value: Any) -> int:
    """Convert a USD number/string to integer micro-USD, rounding half-up."""
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid USD amount: {value!r}") from exc
    if dec.is_nan() or dec.is_infinite():
        raise ValueError(f"invalid USD amount: {value!r}")
    return int((dec / MICRO).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_micro(value: int | None) -> Decimal:
    return (Decimal(int(value or 0)) * MICRO).quantize(MICRO)


def usd(value: int | Decimal | float | str | None) -> float:
    """Display helper: micro-USD or Decimal -> float with 6 decimals."""
    if isinstance(value, int):
        dec = from_micro(value)
    elif isinstance(value, Decimal):
        dec = value
    else:
        dec = Decimal(str(value or 0))
    return float(dec.quantize(MICRO))


def normalize_network(value: str | None) -> str:
    if not value:
        return ""
    key = str(value).strip().lower()
    return NETWORK_ALIASES.get(key, key)


def normalize_asset(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip()
    if text.startswith("0x") and len(text) >= 42:
        return text.lower()
    return text.upper()


def normalize_recipient(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip()
    if text.startswith("0x"):
        return text.lower()
    return text


def asset_decimals(asset: str, explicit: int | None = None) -> int:
    if explicit is not None:
        return int(explicit)
    symbol = normalize_asset(asset)
    symbol = KNOWN_TOKEN_SYMBOLS.get(symbol.lower(), symbol)
    if symbol in ASSET_DECIMALS:
        return ASSET_DECIMALS[symbol]
    if any(stable in symbol for stable in STABLE_SYMBOLS):
        return 6
    return 18


def atomic_to_usd(amount: Any, asset: str, decimals: int | None = None) -> Decimal | None:
    """Convert an atomic token amount to USD for a stablecoin.

    Non-stable assets return None: without a price source we refuse to invent a
    USD value, and the policy asks a human instead.
    """
    symbol = normalize_asset(asset)
    symbol = KNOWN_TOKEN_SYMBOLS.get(symbol.lower(), symbol)
    if not any(stable in symbol for stable in STABLE_SYMBOLS):
        return None
    try:
        raw = int(str(amount).strip(), 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid atomic amount: {amount!r}") from exc
    scale = Decimal(10) ** asset_decimals(symbol, decimals)
    return (Decimal(raw) / scale).quantize(MICRO, rounding=ROUND_HALF_UP)


def human_usd(value: int | Decimal | float | None) -> str:
    return f"${usd(value):,.2f}" if value is not None else "$?"


@dataclass(frozen=True)
class Policy:
    mode: str = "observe"
    daily_limit_usd: Decimal = Decimal("5.00")
    monthly_limit_usd: Decimal = Decimal("50.00")
    per_call_limit_usd: Decimal = Decimal("2.00")
    approval_threshold_usd: Decimal = Decimal("0.50")
    recipient_allowlist: tuple[str, ...] = ()
    asset_allowlist: tuple[str, ...] = ("USDC", "USDT", "OUSD")
    network_allowlist: tuple[str, ...] = ("base", "base-sepolia", "tempo", "bsc", "near", "solana", "celo", "ethereum", "arbitrum", "optimism", "polygon")
    unknown_recipient_action: str = "ask"
    fail_closed: bool = False
    watch_terminal: bool = True
    watched_tools: tuple[str, ...] = DEFAULT_WATCHED_TOOLS

    @classmethod
    def from_config(cls, get: Callable[[str, Any], Any]) -> "Policy":
        def value(key: str, default: Any) -> Any:
            try:
                got = get(key, default)
            except Exception:
                return default
            return default if got is None else got

        def as_list(key: str, default: Iterable[str]) -> tuple[str, ...]:
            raw = value(key, list(default))
            if isinstance(raw, str):
                raw = [part.strip() for part in raw.split(",") if part.strip()]
            if not isinstance(raw, (list, tuple)):
                return tuple(default)
            return tuple(str(item).strip() for item in raw if str(item).strip())

        def as_bool(key: str, default: bool) -> bool:
            raw = value(key, default)
            if isinstance(raw, str):
                return raw.strip().lower() in {"1", "true", "yes", "on"}
            return bool(raw)

        def as_decimal(key: str, default: str) -> Decimal:
            try:
                return Decimal(str(value(key, default))).quantize(MICRO)
            except (InvalidOperation, TypeError, ValueError):
                return Decimal(default)

        mode = str(value("mode", "observe")).strip().lower()
        if mode not in {"observe", "enforce"}:
            mode = "observe"
        unknown = str(value("unknown_recipient_action", "ask")).strip().lower()
        if unknown not in {"ask", "block"}:
            unknown = "ask"

        return cls(
            mode=mode,
            daily_limit_usd=as_decimal("daily_limit_usd", "5.00"),
            monthly_limit_usd=as_decimal("monthly_limit_usd", "50.00"),
            per_call_limit_usd=as_decimal("per_call_limit_usd", "2.00"),
            approval_threshold_usd=as_decimal("approval_threshold_usd", "0.50"),
            recipient_allowlist=tuple(normalize_recipient(x) for x in as_list("recipient_allowlist", ())),
            asset_allowlist=tuple(normalize_asset(x) for x in as_list("asset_allowlist", ("USDC", "USDT", "OUSD"))),
            network_allowlist=tuple(normalize_network(x) for x in as_list("network_allowlist", cls.network_allowlist)),
            unknown_recipient_action=unknown,
            fail_closed=as_bool("fail_closed", False),
            watch_terminal=as_bool("watch_terminal", True),
            watched_tools=as_list("watched_tools", DEFAULT_WATCHED_TOOLS),
        )


@dataclass
class SpendIntent:
    amount_usd: Decimal | None = None
    asset: str = ""
    network: str = ""
    recipient: str = ""
    purpose: str = ""
    tool_name: str = ""
    source: str = "tool"
    raw_amount: str = ""

    def normalized(self) -> "SpendIntent":
        return SpendIntent(
            amount_usd=self.amount_usd,
            asset=normalize_asset(self.asset),
            network=normalize_network(self.network),
            recipient=normalize_recipient(self.recipient),
            purpose=(self.purpose or "").strip()[:240],
            tool_name=self.tool_name,
            source=self.source,
            raw_amount=str(self.raw_amount or ""),
        )


@dataclass
class Decision:
    action: str  # allow | ask | block
    reasons: list[str] = field(default_factory=list)
    receipt: str = ""

    @property
    def allowed(self) -> bool:
        return self.action == "allow"

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "reasons": self.reasons, "receipt": self.receipt}


def _matches(value: str, patterns: Iterable[str]) -> bool:
    return any(fnmatch.fnmatchcase(value, pattern) for pattern in patterns)


def evaluate(
    intent: SpendIntent,
    policy: Policy,
    spent_today_micro: int,
    spent_month_micro: int,
    receipt: str = "",
) -> Decision:
    """Evaluate one payment intent against the current policy and totals."""
    intent = intent.normalized()
    reasons: list[str] = []
    blocking = False
    asking = False

    if intent.amount_usd is None:
        asking = True
        reasons.append("amount is not priced in USD; a human must approve")
    else:
        amount = intent.amount_usd
        if amount <= 0:
            blocking = True
            reasons.append("amount must be greater than zero")
        if amount > policy.per_call_limit_usd:
            blocking = True
            reasons.append(
                f"{human_usd(amount)} exceeds the {human_usd(policy.per_call_limit_usd)} per-call limit"
            )
        if spent_today_micro + to_micro(amount) > to_micro(policy.daily_limit_usd):
            blocking = True
            reasons.append(
                f"daily budget: {human_usd(spent_today_micro)} spent + {human_usd(amount)} "
                f"would exceed {human_usd(policy.daily_limit_usd)}"
            )
        if spent_month_micro + to_micro(amount) > to_micro(policy.monthly_limit_usd):
            blocking = True
            reasons.append(
                f"monthly budget: {human_usd(spent_month_micro)} spent + {human_usd(amount)} "
                f"would exceed {human_usd(policy.monthly_limit_usd)}"
            )
        if not blocking and amount >= policy.approval_threshold_usd:
            asking = True
            reasons.append(
                f"{human_usd(amount)} is at or above the {human_usd(policy.approval_threshold_usd)} approval threshold"
            )

    if intent.recipient and policy.recipient_allowlist:
        if not _matches(intent.recipient, policy.recipient_allowlist):
            if policy.unknown_recipient_action == "block":
                blocking = True
                reasons.append(f"recipient {intent.recipient} is not on the allowlist")
            else:
                asking = True
                reasons.append(f"recipient {intent.recipient} is not on the allowlist")

    if intent.asset and policy.asset_allowlist:
        if intent.asset not in policy.asset_allowlist:
            blocking = True
            reasons.append(
                f"asset {intent.asset} is not allowed "
                f"(allowed: {', '.join(policy.asset_allowlist)})"
            )

    if intent.network and policy.network_allowlist:
        if intent.network not in policy.network_allowlist:
            blocking = True
            reasons.append(
                f"network {intent.network} is not allowed "
                f"(allowed: {', '.join(policy.network_allowlist)})"
            )

    if blocking:
        return Decision("block", reasons, receipt)
    if asking:
        return Decision("ask", reasons, receipt)
    return Decision("allow", ["within policy"], receipt)


def _find_nested(args: Any, keys: tuple[str, ...], depth: int = 0) -> tuple[str, Any]:
    """Find the first matching key in a nested argument object (MCP-style)."""
    if depth > 3 or not isinstance(args, dict):
        return "", None
    for key in keys:
        if key in args and args[key] not in (None, ""):
            return key, args[key]
    for value in args.values():
        if isinstance(value, dict):
            found_key, found_value = _find_nested(value, keys, depth + 1)
            if found_key:
                return found_key, found_value
    return "", None


def detect_intent(
    tool_name: str,
    args: dict[str, Any],
    policy: Policy,
    session_id: str = "",
    task_id: str = "",
) -> SpendIntent | None:
    """Best-effort extraction of a payment intent from a tool call.

    The detector is intentionally conservative: it only reports an intent when
    both a recipient and an amount are present, or when the tool name is a
    known payment tool. False negatives are acceptable; false positives are
    not, because they would block unrelated work.
    """
    if tool_name in OWN_TOOLS:
        return None
    if not isinstance(args, dict):
        return None

    _, recipient_value = _find_nested(args, _RECIPIENT_KEYS)
    recipient = str(recipient_value or "")

    amount_key, amount_value = _find_nested(args, _AMOUNT_KEYS)

    _, asset_value = _find_nested(args, ("asset", "currency", "token", "symbol"))
    asset = str(asset_value or "")

    _, network_value = _find_nested(args, ("network", "chain", "chain_id"))
    network = str(network_value or "")

    _, purpose_value = _find_nested(args, ("purpose", "description", "memo", "reason"))
    purpose = str(purpose_value or "")

    looks_like_payment_tool = _matches(tool_name, policy.watched_tools)
    if not (recipient and amount_key) and not (looks_like_payment_tool and amount_key):
        # Nothing payment-shaped in the arguments; try the terminal parser.
        if policy.watch_terminal and tool_name in {"terminal", "shell", "bash", "exec", "run_command"}:
            command = ""
            for key in ("command", "cmd", "script"):
                if isinstance(args.get(key), str):
                    command = args[key]
                    break
            return intent_from_command(command, policy)
        return None

    if not recipient:
        recipient = ""
    if not asset:
        asset = "USDC" if amount_key.endswith("_usd") else ""
    if not network:
        network = ""

    amount_usd: Decimal | None = None
    raw_amount = str(amount_value)
    try:
        if amount_key in _ATOMIC_KEYS and asset:
            amount_usd = atomic_to_usd(amount_value, asset)
        else:
            amount_usd = Decimal(str(amount_value)).quantize(MICRO, rounding=ROUND_HALF_UP)
            if asset and normalize_asset(asset) not in STABLE_SYMBOLS and normalize_asset(asset) not in ASSET_DECIMALS:
                amount_usd = None
    except (ValueError, InvalidOperation, TypeError):
        amount_usd = None

    return SpendIntent(
        amount_usd=amount_usd,
        asset=asset,
        network=network,
        recipient=recipient,
        purpose=purpose,
        tool_name=tool_name,
        source="tool",
        raw_amount=raw_amount,
    )


_CAST_VALUE_RE = re.compile(r"\bcast\s+send\b(?P<body>.*?)(?:$|\n)", re.DOTALL)
_CAST_VALUE_FLAG_RE = re.compile(r"--value\s+(?P<value>0x[0-9a-fA-F]+|\d+)")
_CAST_TO_RE = re.compile(r"\bcast\s+send\s+(?P<to>0x[0-9a-fA-F]{40})")
_TRANSFER_CALL_RE = re.compile(
    r"cast\s+send\s+(?P<token>0x[0-9a-fA-F]{40})\s+['\"]transfer\(address,uint256\)['\"]\s+"
    r"(?P<to>0x[0-9a-fA-F]{40})\s+(?P<amount>\d+)"
)
_SOLANA_TRANSFER_RE = re.compile(r"\bsolana\s+transfer\s+(?P<to>[1-9A-HJ-NP-Za-km-z]{32,44})\s+(?P<amount>[\d.]+)")
_BITCOIN_SEND_RE = re.compile(r"\bbitcoin-cli\s+sendtoaddress\s+(?P<to>[A-Za-z0-9]{26,90})\s+(?P<amount>[\d.]+)")
_NEAR_DEPOSIT_RE = re.compile(r"\bnear\s+call\s+\S+\s+\S+.*?--deposit\s+(?P<amount>[\d.]+)")


def intent_from_command(command: str, policy: Policy) -> SpendIntent | None:
    """Recognise a handful of high-risk money-moving shell commands."""
    if not command or not isinstance(command, str):
        return None
    text = command.strip()
    if not text:
        return None

    match = _TRANSFER_CALL_RE.search(text)
    if match:
        token = match.group("token")
        symbol = KNOWN_TOKEN_SYMBOLS.get(token.lower(), token)
        return SpendIntent(
            amount_usd=atomic_to_usd(match.group("amount"), symbol),
            asset=symbol,
            network="",
            recipient=match.group("to"),
            purpose="ERC-20 transfer via cast",
            tool_name="terminal",
            source="terminal",
            raw_amount=match.group("amount"),
        )

    match = _CAST_TO_RE.search(text)
    if match and _CAST_VALUE_FLAG_RE.search(text):
        value = _CAST_VALUE_FLAG_RE.search(text).group("value")
        wei = int(value, 0)
        return SpendIntent(
            amount_usd=None,
            asset="ETH",
            network="",
            recipient=match.group("to"),
            purpose="native value transfer via cast",
            tool_name="terminal",
            source="terminal",
            raw_amount=str(wei),
        )

    match = _SOLANA_TRANSFER_RE.search(text)
    if match:
        return SpendIntent(
            amount_usd=None,
            asset="SOL",
            network="solana",
            recipient=match.group("to"),
            purpose="SOL transfer",
            tool_name="terminal",
            source="terminal",
            raw_amount=match.group("amount"),
        )

    match = _BITCOIN_SEND_RE.search(text)
    if match:
        return SpendIntent(
            amount_usd=None,
            asset="BTC",
            network="bitcoin",
            recipient=match.group("to"),
            purpose="BTC sendtoaddress",
            tool_name="terminal",
            source="terminal",
            raw_amount=match.group("amount"),
        )

    match = _NEAR_DEPOSIT_RE.search(text)
    if match:
        return SpendIntent(
            amount_usd=None,
            asset="NEAR",
            network="near",
            recipient="",
            purpose="NEAR call with deposit",
            tool_name="terminal",
            source="terminal",
            raw_amount=match.group("amount"),
        )

    # A curl that carries an already-signed x402 payment is a spend attempt.
    if re.search(r"\bcurl\b", text) and re.search(r"x-payment\s*:", text, re.IGNORECASE):
        return SpendIntent(
            amount_usd=None,
            asset="",
            network="",
            recipient="",
            purpose="curl with an X-PAYMENT header",
            tool_name="terminal",
            source="terminal",
        )
    return None
