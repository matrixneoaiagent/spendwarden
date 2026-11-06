"""Decode and inspect x402 payment challenges without signing anything.

The x402 flow is simple on the wire and easy to get wrong in an agent:

1. The client requests a resource.
2. The server answers 402 with a ``PAYMENT-REQUIRED`` header (base64 JSON).
3. The client signs an EIP-3009 authorization and retries with ``X-PAYMENT``.
4. A facilitator verifies and settles it.

This module performs steps 1-2 only: it decodes the challenge, normalizes the
terms, and hands them to the same policy engine used for tool calls. It never
holds a key and never signs.
"""

from __future__ import annotations

import base64
import binascii
import json
import time
from decimal import Decimal
from typing import Any
from urllib.parse import urlparse

from .policy import SpendIntent, asset_decimals, atomic_to_usd, normalize_network, usd

# Common x402 assets. Extend deliberately: an unknown asset asks for approval.
KNOWN_ASSETS: dict[str, tuple[str, int]] = {
    # Base mainnet
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": ("USDC", 6),
    # Base Sepolia
    "0x036cbd53842c5426634e7929541ec2318f3dcf7e": ("USDC", 6),
    # Ethereum
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": ("USDC", 6),
    # Arbitrum
    "0xaf88d065e77c8cc2239327c5edb3a432268e5831": ("USDC", 6),
    # Optimism
    "0x0b2c639c533813f4aa9d7837caf62653d097ff85": ("USDC", 6),
    # Polygon
    "0x2791bca1f2de4661ed88a30c99a7a9449aa84174": ("USDC", 6),
    # BSC (Binance-Peg USDC uses 18 decimals)
    "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": ("USDC", 18),
}

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


class X402Error(ValueError):
    """Raised when a challenge or payment header cannot be decoded."""


def _b64_json(raw: str) -> Any:
    text = raw.strip()
    # Accept both standard and URL-safe base64, with or without padding.
    text += "=" * (-len(text) % 4)
    try:
        decoded = base64.b64decode(text.replace("-", "+").replace("_", "/"), validate=False)
    except (binascii.Error, ValueError) as exc:
        raise X402Error(f"not valid base64: {exc}") from exc
    try:
        return json.loads(decoded.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise X402Error(f"base64 did not contain JSON: {exc}") from exc


def load_header(raw: Any) -> Any:
    """Parse a challenge from a JSON object, a JSON string, or base64 text."""
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        raise X402Error("empty challenge")
    text = raw.strip()
    if text.startswith("{") or text.startswith("["):
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise X402Error(f"not valid JSON: {exc}") from exc
    return _b64_json(text)


def extract_options(doc: Any) -> list[dict[str, Any]]:
    if isinstance(doc, list):
        return [item for item in doc if isinstance(item, dict)]
    if isinstance(doc, dict):
        accepts = doc.get("accepts")
        if isinstance(accepts, list):
            return [item for item in accepts if isinstance(item, dict)]
        # Some servers return the option itself.
        if "payTo" in doc or "maxAmountRequired" in doc:
            return [doc]
    raise X402Error("no x402 payment options found")


def asset_info(option: dict[str, Any]) -> tuple[str, int]:
    address = str(option.get("asset") or "").strip()
    known = KNOWN_ASSETS.get(address.lower())
    if known:
        return known
    extra = option.get("extra") if isinstance(option.get("extra"), dict) else {}
    name = str(extra.get("name") or "")
    if "usd" in name.lower() or "stable" in name.lower():
        return (address or name or "UNKNOWN", 6)
    if address:
        return (address, asset_decimals(address))
    return (name or "UNKNOWN", 18)


def _resource_warning(resource: str) -> str | None:
    if not resource:
        return None
    parsed = urlparse(resource)
    if parsed.scheme == "https":
        return None
    if parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        return None
    return f"resource is not HTTPS: {resource[:120]}"


def inspect_challenge(
    raw: Any,
    policy,
    evaluate,
    preferred_network: str | None = None,
    now: int | None = None,
) -> dict[str, Any]:
    """Decode a 402 challenge and evaluate its terms.

    ``evaluate`` is injected from policy.py to keep this module testable and
    free of a circular import.
    """
    doc = load_header(raw)
    options = extract_options(doc)
    if not options:
        raise X402Error("no payment options")

    preferred = normalize_network(preferred_network) if preferred_network else ""
    selected = None
    if preferred:
        for option in options:
            if normalize_network(str(option.get("network") or "")) == preferred:
                selected = option
                break
    if selected is None:
        selected = options[0]

    scheme = str(selected.get("scheme") or "")
    network = normalize_network(str(selected.get("network") or ""))
    asset, decimals = asset_info(selected)
    amount_raw = selected.get("maxAmountRequired", selected.get("amount"))
    try:
        amount_usd = atomic_to_usd(amount_raw, asset, decimals)
    except (ValueError, TypeError):
        amount_usd = None

    pay_to = str(selected.get("payTo") or "")
    resource = str(selected.get("resource") or "")
    timeout = selected.get("maxTimeoutSeconds")
    x402_version = doc.get("x402Version") if isinstance(doc, dict) else selected.get("x402Version")

    warnings: list[str] = []
    if scheme != "exact":
        warnings.append(f"unsupported scheme {scheme!r}; only 'exact' is evaluated")
    if x402_version not in (None, 1, "1"):
        warnings.append(f"unexpected x402Version {x402_version!r}")
    if not pay_to or pay_to.lower() == ZERO_ADDRESS:
        warnings.append("payTo is empty or the zero address")
    resource_warning = _resource_warning(resource)
    if resource_warning:
        warnings.append(resource_warning)
    if isinstance(timeout, (int, float)) and timeout > 300:
        warnings.append(f"challenge allows {timeout}s to pay; long windows widen replay risk")

    intent = SpendIntent(
        amount_usd=amount_usd,
        asset=asset,
        network=network,
        recipient=pay_to,
        purpose=str(selected.get("description") or "x402 resource")[:240],
        tool_name="x402_inspect",
        source="x402",
        raw_amount=str(amount_raw or ""),
    )
    decision = evaluate(intent, policy, 0, 0)
    # A warning is not automatically a block, but an unsupported scheme or a
    # missing recipient cannot be evaluated safely, so escalate those.
    if scheme != "exact" or not pay_to or pay_to.lower() == ZERO_ADDRESS:
        if decision.action == "allow":
            decision.action = "ask"
            decision.reasons = list(decision.reasons) + ["challenge needs a human review"]

    return {
        "ok": True,
        "kind": "challenge",
        "x402Version": x402_version,
        "terms": {
            "scheme": scheme,
            "network": network,
            "asset": asset,
            "asset_address": str(selected.get("asset") or ""),
            "decimals": decimals,
            "amount_atomic": str(amount_raw) if amount_raw is not None else "",
            "amount_usd": usd(amount_usd) if amount_usd is not None else None,
            "payTo": pay_to,
            "resource": resource,
            "description": str(selected.get("description") or ""),
            "mimeType": str(selected.get("mimeType") or ""),
            "maxTimeoutSeconds": timeout,
            "extra": selected.get("extra") if isinstance(selected.get("extra"), dict) else {},
            "expires_at": (int(now or time.time()) + int(timeout or 0)) if timeout else None,
        },
        "options_count": len(options),
        "other_networks": [
            normalize_network(str(option.get("network") or ""))
            for option in options
            if option is not selected
        ],
        "warnings": warnings,
        "decision": decision.to_dict(),
    }


def inspect_payment(
    raw: Any,
    policy,
    evaluate,
    now: int | None = None,
    asset_hint: str = "",
) -> dict[str, Any]:
    """Decode an already-signed X-PAYMENT payload and check its authorization."""
    doc = load_header(raw)
    if not isinstance(doc, dict):
        raise X402Error("payment payload is not an object")
    payload = doc.get("payload")
    if not isinstance(payload, dict):
        raise X402Error("payment payload has no payload object")
    auth = payload.get("authorization")
    if not isinstance(auth, dict):
        raise X402Error("payment payload has no authorization")
    network = normalize_network(str(doc.get("network") or ""))
    asset_address = auth.get("asset") or doc.get("asset") or asset_hint
    asset, decimals = asset_info({"asset": asset_address, "extra": doc.get("extra") or {}})
    amount_raw = auth.get("value")
    try:
        amount_usd = atomic_to_usd(amount_raw, asset, decimals)
    except (ValueError, TypeError):
        amount_usd = None
    valid_before = auth.get("validBefore")
    expired = False
    try:
        expired = int(valid_before) <= int(now or time.time())
    except (TypeError, ValueError):
        pass
    intent = SpendIntent(
        amount_usd=amount_usd,
        asset=asset,
        network=network,
        recipient=str(auth.get("to") or ""),
        purpose="signed x402 payment",
        tool_name="x402_inspect",
        source="x402",
        raw_amount=str(amount_raw or ""),
    )
    decision = evaluate(intent, policy, 0, 0)
    if expired and decision.action == "allow":
        decision.action = "block"
        decision.reasons = list(decision.reasons) + ["authorization has expired"]
    return {
        "ok": True,
        "kind": "payment",
        "x402Version": doc.get("x402Version"),
        "scheme": str(doc.get("scheme") or ""),
        "network": network,
        "terms": {
            "from": str(auth.get("from") or ""),
            "to": str(auth.get("to") or ""),
            "asset": asset,
            "amount_atomic": str(amount_raw) if amount_raw is not None else "",
            "amount_usd": usd(amount_usd) if amount_usd is not None else None,
            "validAfter": auth.get("validAfter"),
            "validBefore": valid_before,
            "nonce": str(auth.get("nonce") or ""),
            "expired": expired,
            "signature_present": bool(payload.get("signature")),
        },
        "warnings": [] if not expired else ["authorization has expired"],
        "decision": decision.to_dict(),
    }
