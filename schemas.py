"""Tool schemas — what the model sees."""

SPEND_CHECK = {
    "name": "spend_check",
    "description": (
        "Check a proposed payment against the user's SpendWarden policy BEFORE moving money. "
        "Returns allow / ask / block with reasons, remaining daily and monthly budget, and a receipt code. "
        "Use this for any wallet transfer, x402 payment, swap, bridge, checkout, or paid API call. "
        "It never signs or sends anything."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "amount_usd": {
                "type": "number",
                "description": "Payment amount in USD, e.g. 0.25. Use this for stablecoin payments.",
            },
            "amount_atomic": {
                "type": "string",
                "description": "Raw token amount in atomic units (e.g. '250000' for 0.25 USDC). Requires asset.",
            },
            "asset": {
                "type": "string",
                "description": "Token symbol or contract address, e.g. USDC, USDT, OUSD, ETH.",
            },
            "network": {
                "type": "string",
                "description": "Chain name or id, e.g. base, tempo, bsc, solana, near, eip155:8453.",
            },
            "recipient": {
                "type": "string",
                "description": "Destination address or account. Required for allowlist checks.",
            },
            "purpose": {
                "type": "string",
                "description": "Short reason for the payment, e.g. 'buy market data from api.example.com'.",
            },
        },
    },
}

SPEND_RECORD = {
    "name": "spend_record",
    "description": (
        "Record a payment that actually succeeded in the SpendWarden ledger, after the money moved. "
        "Idempotent on payment_id or tx_hash: retrying after a timeout will not double-count. "
        "Records what happened even if the payment violated policy: the entry is flagged over_budget "
        "or unapproved, and still counts toward the budget. If the policy says ask, set approved=true "
        "only after a human confirms. This does not send funds; it records a spend and returns a receipt."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "amount_usd": {
                "type": "number",
                "description": "Amount actually paid, in USD.",
            },
            "amount_atomic": {
                "type": "string",
                "description": "Raw token amount in atomic units. Requires asset.",
            },
            "asset": {"type": "string", "description": "Token symbol or contract address."},
            "network": {"type": "string", "description": "Chain name or id."},
            "recipient": {"type": "string", "description": "Destination address or account."},
            "purpose": {"type": "string", "description": "Short reason for the payment."},
            "payment_id": {
                "type": "string",
                "description": "Stable idempotency key, e.g. an x402 receipt id or a payment intent id.",
            },
            "tx_hash": {
                "type": "string",
                "description": "On-chain transaction hash, if the payment settled on-chain.",
            },
            "approved": {
                "type": "boolean",
                "description": "Set true only after a human explicitly approved a payment above the approval threshold.",
            },
        },
    },
}

SPEND_REPORT = {
    "name": "spend_report",
    "description": (
        "Show what the agent has spent, what is left in the daily and monthly budgets, "
        "the top recipients, and how many payments were blocked or sent for approval. "
        "Use it when the user asks 'what did you spend?', 'what is left?', or before a larger purchase."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "period": {
                "type": "string",
                "enum": ["today", "week", "month", "all"],
                "description": "Reporting window. Defaults to today (UTC).",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum recent entries to return (1-50, default 10).",
            },
        },
    },
}

X402_INSPECT = {
    "name": "x402_inspect",
    "description": (
        "Decode an x402 402 challenge (PAYMENT-REQUIRED header or JSON body) or an already-signed "
        "X-PAYMENT payload without signing anything. Returns the normalized terms: network, asset, "
        "amount in USD, payTo, resource, expiry, and warnings. Runs the same SpendWarden policy check, "
        "so an agent can decide whether to pay before it touches a key."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "challenge": {
                "type": "string",
                "description": "Base64 PAYMENT-REQUIRED header, JSON challenge, or base64 X-PAYMENT payload.",
            },
            "mode": {
                "type": "string",
                "enum": ["challenge", "payment"],
                "description": "challenge (default) decodes a 402 offer; payment decodes a signed X-PAYMENT.",
            },
            "network": {
                "type": "string",
                "description": "Preferred network when the challenge offers several options.",
            },
            "asset": {
                "type": "string",
                "description": "Asset hint for payment mode when the payload does not carry the token address.",
            },
        },
        "required": ["challenge"],
    },
}
