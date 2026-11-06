---
title: "Your agent can buy things. A prompt won't stop it."
published: false
description: "A deterministic spend policy firewall for AI agents with wallets, built as a Hermes Agent plugin."
tags: ai, security, web3, opensource
cover_image: https://agent-payments-audit.surge.sh/spendwarden/banner.png
---

Last week I gave an autonomous agent a wallet, a browser, a shell, and one instruction: earn money. The interesting part was not the $0.34 it made. It was how many ways a tool call could turn into a payment.

A task brief can contain a line that looks like an instruction. A web page can hide text in a comment. A retry after a timeout can pay twice. An x402 challenge can change the `payTo` address between the quote and the signature. A cron loop can spend a month's budget while nobody is watching.

The usual answer is a system prompt: "never spend more than $5." That is a suggestion. It can be paraphrased by compression, ignored under pressure, or overridden by a malicious tool result. If the agent has a wallet, the enforcement point has to be below the model.

So I built **SpendWarden**, a plugin for [Hermes Agent](https://hermes-agent.nousresearch.com/). It puts a deterministic policy check in front of every payment-shaped tool call and keeps an idempotent local ledger of what happened.

## The shape of the check

Hermes plugins can register a `pre_tool_call` hook. It runs before a tool executes and can return a directive:

- `{"action": "block", "message": "..."}` stops the call.
- `{"action": "approve", "message": "..."}` sends it to Hermes's own approval gate.
- `None` lets it run.

SpendWarden uses that seam. It looks at the tool name and arguments, extracts a payment intent when it sees one, and evaluates it against a policy:

```yaml
mode: enforce
daily_limit_usd: 5.00
monthly_limit_usd: 50.00
per_call_limit_usd: 2.00
approval_threshold_usd: 0.50
unknown_recipient_action: ask
recipient_allowlist:
  - "0x1111111111111111111111111111111111111111"
asset_allowlist: [USDC, USDT, OUSD]
network_allowlist: [base, tempo, bsc, near, solana]
```

The decision is ordinary Python. It does not ask a model whether to spend.

## What it watches

The plugin catches tools whose names look like payments (`wallet_*`, `x402_*`, `*pay*`, `*transfer*`, `*swap*`, `*bridge*`, `*send*`, `*withdraw*`, `*deposit*`, and more), MCP tools with nested payment arguments, and a small set of high-risk shell commands:

- `cast send` with native value or an ERC-20 `transfer`
- `solana transfer`
- `bitcoin-cli sendtoaddress`
- `near call ... --deposit`
- `curl` with an `X-PAYMENT` header

It is deliberately conservative. A false negative is a missed check; a false positive is a blocked task. Start in `observe` mode, read a day of events, tune the policy, then switch to `enforce`.

## The x402 problem

x402 is a pay-per-call HTTP flow. The server answers `402` with a `PAYMENT-REQUIRED` header, the client signs an EIP-3009 authorization, and a facilitator settles it. The dangerous moment is between decoding the challenge and signing it.

`x402_inspect` decodes the challenge (or an already-signed `X-PAYMENT`), normalizes the terms, and runs the same policy:

```json
{
  "network": "base",
  "asset": "USDC",
  "amount_atomic": "250000",
  "amount_usd": 0.25,
  "payTo": "0x1111111111111111111111111111111111111111",
  "resource": "https://api.example.com/market-data",
  "decision": {"action": "allow", "reasons": ["within policy"]}
}
```

It warns on an unsupported scheme, a zero or missing `payTo`, a non-HTTPS resource, an unusually long payment window, and an unknown asset. It never holds a key and never signs.

## The ledger

Every recorded payment gets a receipt. `payment_id` is unique, so a retry after a timeout cannot double-count. The ledger also records payments that violated policy, flagged `over_budget` or `unapproved`, because a spend that already happened should not disappear from the totals.

```text
SpendWarden · today
Spent: $0.25 across 1 payment(s)
Today remaining: $1.75 · Month remaining: $19.75
Mode: enforce · per-call $1.00 · approval at $0.30
Decisions: allow 2, ask 1, block 1
```

The database is local, SQLite, and the plugin makes no network calls. There is no telemetry.

## The demo

I pointed a throwaway Hermes profile at a mock OpenAI-compatible provider. The model asks to send 5 USDC on Base with `cast send`. Hermes passes the tool call to SpendWarden's hook. The hook returns a block, so the terminal command never runs. The model receives the block message and explains it.

The 48-second video shows that turn, then the standalone policy check, an approval escalation, the ledger, and an x402 challenge decoded without signing:

[Watch the demo on X](https://x.com/i_am_ahero/status/2118732352620794118)

There is also a [source archive and a longer write-up](https://agent-payments-audit.surge.sh/spendwarden/). The public repository and the Hermes catalog PR are being prepared.

## What it does not do

It is not a hardware wallet, a multisig, or a sandbox. A process that can edit the plugin's database or disable the plugin can bypass it. It does not price volatile assets: an ETH/SOL/BNB payment without an explicit USD value asks for approval instead of inventing a price. It does not parse arbitrary shell scripts; a custom script that moves money is outside its reach.

It is a second, independent check between the model and the money. That is the layer that was missing.

## Try it

- 48-second demo: https://x.com/i_am_ahero/status/2118732352620794118
- Source archive: https://agent-payments-audit.surge.sh/spendwarden/
- Built for the [Hermes Agent Plugin Hackathon](https://nousresearch.com/).

If you run an agent with a wallet, the useful question is not "did I write a good prompt?" It is "what happens when the model asks to pay the wrong address?" SpendWarden is my answer to that question.
