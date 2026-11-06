# Add SpendWarden

SpendWarden is a spend policy firewall and local ledger for Hermes agents that
can move money. It is a `pre_tool_call` guard, not a prompt: a deterministic
Python check runs before a payment-shaped tool executes.

## What it registers

- `spend_check` — evaluate a proposed payment against daily, monthly, per-call,
  recipient, asset and network policy before money moves.
- `spend_record` — record a successful payment. Idempotent on `payment_id` or
  `tx_hash`, so a retry after a timeout cannot double-count.
- `spend_report` — totals, remaining budget, top recipients, decisions, recent
  receipts.
- `x402_inspect` — decode a `PAYMENT-REQUIRED` challenge or a signed
  `X-PAYMENT` payload, normalize the terms, and run the same policy. It never
  signs.
- `pre_tool_call` — catches payment-shaped tool calls (`wallet_*`, `x402_*`,
  `*pay*`, `*transfer*`, `*swap*`, `*bridge*`, `*send*`, `*withdraw*`,
  `*deposit*`, and more) plus `cast send`, `solana transfer`,
  `bitcoin-cli sendtoaddress`, `near call --deposit`, and `curl` with
  `X-PAYMENT`.
- `/spend` — a one-line status command.
- `hermes spendwarden report|policy|receipts` — the same data from the terminal.

In `enforce` mode a hard violation returns `{"action": "block"}`; an uncertain
payment returns `{"action": "approve"}` and goes through Hermes's own approval
gate. In `observe` mode (the default) it only logs.

## Disclosure

- State is a local SQLite ledger under the plugin data directory
  (`$HERMES_HOME/plugin-data/spendwarden/ledger.db`), DELETE journal.
- **No network calls. No credentials. No private keys. No signing. No
  transaction sending.**
- The plugin sees tool names and arguments for every tool call because it
  registers `pre_tool_call`. It only records an event when it detects a
  payment-shaped call.
- In `enforce` mode it can block a tool call or escalate it to the approval
  prompt. That is the intended behavior; `observe` is the default.
- A process that can edit the plugin's database or disable the plugin can
  bypass it. It is a second check, not a sandbox or a hardware wallet.
- It does not price volatile assets. An ETH/SOL/BNB payment without an
  explicit USD value asks for approval instead of inventing a price.
- The terminal parser recognizes a small set of commands, not arbitrary shell
  scripts.

## Validation

- `python3 -m unittest discover -s tests -v` — 37 tests pass.
- `hermes plugins validate . --install-deps` — all checks pass, no warnings.
- `hermes plugins doctor . --ci` — 4 tools, 1 hook; registration passes.
- End-to-end: a real Hermes turn asks to transfer 5 USDC with `cast send`; the
  hook blocks it before the terminal runs. The demo video shows this.

## Demo

- 48-second video: https://x.com/i_am_ahero/status/2118732352620794118
- Page and source archive: https://agent-payments-audit.surge.sh/spendwarden/
- Repository: `<repo URL>`
- Pinned commit: `<sha>`

Built by an autonomous agent; human operator approved. MIT.
