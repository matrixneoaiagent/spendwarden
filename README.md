# SpendWarden

**Your agent can buy things. It can't surprise you.**

SpendWarden is a Hermes Agent plugin that puts a deterministic spending policy in front of every payment-shaped tool call and keeps an idempotent local ledger of what happened.

It is built for the moment an agent stops being a chatbot and starts holding a wallet: paying for an x402 API, swapping tokens, bridging gas, or checking out with a card. A prompt that says "don't spend more than $5" is a suggestion. SpendWarden is a check that runs before the tool does.

```text
agent → spend_check → allow / ask / block
                    ↓
              tool executes
                    ↓
             spend_record → receipt
```

## What it adds

| Surface | What it does |
|---|---|
| `spend_check` | Evaluates a proposed payment against the policy before any money moves. Returns `allow`, `ask` or `block`, the reasons, and the remaining budget. |
| `spend_record` | Records a payment that actually succeeded. Idempotent on `payment_id` or `tx_hash`, so a retry after a timeout cannot double-count. |
| `spend_report` | Daily/weekly/monthly totals, remaining budget, top recipients, blocked/approval counts, and recent receipts. |
| `x402_inspect` | Decodes a `PAYMENT-REQUIRED` challenge or a signed `X-PAYMENT` payload, normalizes the terms, and runs the same policy check. It never signs. |
| `pre_tool_call` hook | Catches payment-shaped tool calls (`wallet_*`, `x402_*`, `*pay*`, `*transfer*`, `*swap*`, `*bridge*`, `*checkout*`, `*purchase*`, `*send*`, `*withdraw*`, `*deposit*`, `*invoice*`, `*tip*`, `*buy*`) and a small set of high-risk shell commands. In `enforce` mode it blocks hard violations and escalates uncertain ones to Hermes's approval gate. |
| `/spend` | A one-line status command for the current chat. |
| `hermes spendwarden report` / `policy` / `receipts` | The same data from the terminal. |

## Why a plugin, not a prompt

A system prompt can be ignored, paraphrased by compression, or overridden by a malicious tool result. SpendWarden's decision is ordinary Python that runs in the `pre_tool_call` hook, before the tool executes, and writes its reasoning to SQLite. It does not call a model to decide whether to spend.

The policy is intentionally boring:

- **Per-call cap** — one payment cannot exceed a fixed USD amount.
- **Daily and monthly caps** — totals include everything already recorded, not just the current session.
- **Recipient allowlist** — exact addresses or globs. An unknown recipient asks (or blocks, if configured).
- **Asset and network allowlists** — a payment in an unexpected token or chain is blocked.
- **Approval threshold** — payments at or above it go to Hermes's own approval prompt. In cron, yolo, or other unattended runs, Hermes refuses when nobody can answer.
- **Fail-closed option** — if the policy check itself errors, block payment-shaped calls instead of letting them through.

## Install

```bash
hermes plugins install opencode-audit/spendwarden
hermes plugins enable spendwarden
```

Or, from a checkout:

```bash
git clone https://github.com/opencode-audit/spendwarden
hermes plugins install ./spendwarden --enable
```

The plugin has **no Python dependencies** beyond the standard library and makes **no network calls**.

## Configure

Settings live under `plugins.entries.spendwarden.settings` and are editable from the Desktop **Settings → Plugins** page.

```yaml
plugins:
  entries:
    spendwarden:
      settings:
        mode: enforce            # observe (default) or enforce
        daily_limit_usd: 5.00
        monthly_limit_usd: 50.00
        per_call_limit_usd: 2.00
        approval_threshold_usd: 0.50
        unknown_recipient_action: ask   # ask or block
        recipient_allowlist:
          - "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        asset_allowlist: [USDC, USDT, OUSD]
        network_allowlist: [base, tempo, bsc, near, solana]
        watch_terminal: true
        fail_closed: false
```

Start in `observe` mode. It records every payment-shaped call and the decision it *would* have made, but does not block anything. Read a day of events, tune the limits and allowlist, then switch to `enforce`.

## A 60-second example

Ask the agent:

> Pay 0.25 USDC on Base to `0x1111…1111` for a market-data call.

The agent calls `spend_check` first:

```json
{
  "decision": {"action": "allow", "reasons": ["within policy"], "receipt": "SW-7F3A2C"},
  "remaining": {"today_usd": 4.75, "month_usd": 49.75},
  "message": "SpendWarden allows $0.25 in USDC on base to 0x1111…1111. within policy."
}
```

Then it executes the payment and records it:

```json
{
  "ok": true,
  "duplicate": false,
  "receipt": "SW-7F3A2C",
  "spent": {"today_usd": 0.25, "month_usd": 0.25}
}
```

A second call for $3.00 is blocked before any wallet tool runs:

```text
SpendWarden blocked $3.00 in USDC on base to 0x1111…1111.
$3.00 exceeds the $2.00 per-call limit.
Adjust the policy or make this payment explicitly in a separate, approved step.
```

## x402

x402 is a pay-per-call HTTP flow: the server answers `402` with a `PAYMENT-REQUIRED` header, the client signs an EIP-3009 authorization, and a facilitator settles it.

SpendWarden does not sign. It answers the question the agent should ask **before** it signs:

```bash
x402_inspect --challenge "$PAYMENT_REQUIRED_HEADER"
```

```json
{
  "ok": true,
  "terms": {
    "scheme": "exact",
    "network": "base",
    "asset": "USDC",
    "amount_atomic": "250000",
    "amount_usd": 0.25,
    "payTo": "0x1111111111111111111111111111111111111111",
    "resource": "https://api.example.com/market-data",
    "maxTimeoutSeconds": 60
  },
  "warnings": [],
  "decision": {"action": "allow", "reasons": ["within policy"], "receipt": "SW-91C0DE"}
}
```

It warns on unsupported schemes, a zero or missing `payTo`, a non-HTTPS resource, an unusually long payment window, and an unknown asset. Those warnings turn into an `ask` when the challenge cannot be evaluated safely.

It can also inspect an already-signed `X-PAYMENT` payload and refuse an expired authorization.

## The ledger

All state is local, in `$HERMES_HOME/plugin-data/spendwarden/ledger.db` (SQLite, DELETE journal):

- `entries` — one row per recorded payment. Amounts are integer micro-USD. `payment_id` is unique, which is the idempotency guarantee.
- `events` — every check, block, approval, and x402 inspection, with reasons and a receipt code.

Nothing is sent anywhere. There is no telemetry.

## How it differs from adjacent plugins

- **vet402 / toll** look up whether a URL, coin, or transaction is reputable.
  SpendWarden enforces the user's own budget and allowlist and records the
  payment; it calls no reputation service.
- **usage-guard** caps a subscription's model usage. SpendWarden caps payments
  the agent makes with a wallet or an x402 client.
- **openrouter-spend** accounts for LLM API cost. SpendWarden accounts for
  x402, on-chain, checkout, and other payment-shaped tool calls, and blocks
  them before they run.
- **airlock** taints a session after it reads untrusted content. SpendWarden is
  a spend-specific check that runs on every payment-shaped call, whether or not
  the session is tainted.

## What it deliberately does not do

- It does not hold a private key, sign a transaction, or send funds.
- It does not replace the wallet's own limits. It is a second, independent check.
- It does not price volatile assets. An ETH/SOL/BNB payment without an explicit USD value asks for approval instead of inventing a price.
- It does not parse arbitrary shell scripts. It recognizes `cast send`, `solana transfer`, `bitcoin-cli sendtoaddress`, `near call --deposit`, and `curl` with an `X-PAYMENT` header. A custom script that moves money is outside its reach; use a wallet tool with explicit arguments, or wrap it in one.
- It does not stop a compromised host. A process that can edit the plugin's database or disable the plugin can bypass it. Use OS-level isolation for that threat.

## Threat model

SpendWarden is designed for the ordinary failure modes of an agent with a wallet:

1. A prompt injection in a web page or task brief asks for a payment that is larger than the task.
2. The agent misunderstands a price (atomic units vs. dollars) and sends 1,000,000 USDC instead of 1 USDC.
3. A retry after a timeout pays twice.
4. A compromised or hallucinated x402 challenge changes `payTo` or the asset.
5. An unattended cron job spends the month's budget in one loop.

It is not a hardware wallet, a multisig, or a sandbox. Those are complementary.

## Development

```bash
python3 -m unittest discover -s tests -v
hermes plugins validate . --install-deps
```

The policy, x402 decoder, and ledger are independent of Hermes and can be tested without an agent. `hermes plugins doctor . --ci` checks discovery, manifest parsing, and registration.

## License

MIT. Built by an autonomous agent; human operator approved.
