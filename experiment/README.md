# Swarm red-team experiment

This directory contains the experiment behind the AIAF Brazil 2026 submission
*Caps Are Not Capabilities*. It is self-contained: no network, no keys, no real
funds, no LLM calls.

The question: **does a spend policy that is sound for one sequential agent
still hold when a swarm of agents shares one wallet, acts concurrently, and can
write its own payment tools?**

## What is tested

SpendWarden itself is the treatment, not the thing being replaced. The harness
imports `policy.py` and `storage.py` from the repository root by path, so the
detector and policy evaluation are the plugin's real code.

| Scenario | Guardrail |
|---|---|
| `none` | no guardrail; every tool call reaches the mock wallet |
| `warden` | SpendWarden enforce mode; `ask` cannot be answered in an unattended run, so it stops |
| `mediated` | capability boundary + atomic budget reservation + cumulative exposure, with the SpendWarden policy as a second layer |

The full run is six agents over six rounds: four workers doing routine
purchases, two compromised agents escalating through a fixed ladder. The
ladder is frozen in `fixtures/swarm_script.json` (sha256 recorded in every
result file).

Three controlled probes isolate one failure mode each, so a result is not
confounded by the rest of the ladder:

| Probe | Mechanism | What it shows |
|---|---|---|
| S — split | six payments of $0.49 | per-call caps and approval thresholds are message-level, not principal-level |
| R — race | six parallel calls with $0.90 left | check-then-act is not a reservation |
| A — alias | `vendor_settle` with `payee`/`sum_usd` keys | name-based detection has silent false negatives |

The mitigation adds:

1. **Capability boundary** — agents call a mediator; only the mediator can reach
   the wallet. A tool the agents write themselves has no payment capability.
2. **Atomic reservation** — budget is held before execution, so parallel agents
   cannot all pass the same check.
3. **Cumulative exposure** — per agent→recipient and per recipient daily limits,
   so a run of small payments still hits a ceiling.
4. **Fail-closed parsing** — a payment request the mediator cannot parse is
   refused.

## Run it

```bash
cd spendwarden
python3 -m experiment.run          # writes experiment/results/{results.json,RESULTS.md}
python3 -m unittest discover -s experiment/tests -v
```

`experiment/results/RESULTS.md` is generated; do not edit it by hand. Every
number in the paper comes from `results.json`.

The run is deterministic: fixed fixture, integer micro-USD, no clocks or
randomness in any decision. Only `meta.generated_at`, `meta.git_commit`, and
SQLite row ids vary between runs; no metric uses them.

## Fixture schema

`fixtures/swarm_script.json` is data only:

- `policy` — SpendWarden settings under test.
- `recipients` / `allowlist` — mock addresses; `allowlist` names the vendors the
  policy trusts.
- `honest_routine` — the four calls repeated every round.
- `rounds[].honest_extra` — one-off honest work (the round-4 batch).
- `rounds[].attack` — `{agent, mode, amount, recipient, count, tool, args, entry}`.
  `mode` is one of `blend`, `split`, `oversize`, `alias`, `race` and is used only
  for scoring. `entry: "direct"` means the tool tries to reach the wallet
  without the mediator.

The gate never receives `kind`, `mode`, or the declared amount. It sees the
tool name and arguments only, exactly like the plugin's `pre_tool_call` hook.

## Files

| File | Purpose |
|---|---|
| `bridge.py` | loads the real policy engine and ledger; `Gate` reproduces check→record |
| `swarm.py` | fixture expansion, agents, mock wallet, three scenarios, scoring |
| `probes.py` | the three controlled probes |
| `run.py` | CLI; writes `results/results.json` and `results/RESULTS.md` |
| `render.py` | Markdown tables, generated from results |
| `tests/` | 18 tests: determinism, failure-mode regressions, and paper/results consistency |
| `results/` | generated output, committed for reviewers |

## Honest limits

- Agents are rule-based, not LLM-driven. The experiment measures the guardrail,
  not model susceptibility to persuasion.
- One policy configuration, one fixture, six agents, one simulated day.
- The attack ladder was written by us and frozen before the run. It is not an
  adaptive adversary.
- `ask` is treated as denial because the run is unattended. Interactive human
  approval is untested and is itself an attack surface.
- The mediator is a ~150-line prototype in this directory, not integrated into
  the Hermes plugin. That integration is future work.
- Per-recipient exposure is what stops identity rotation in the design; the
  current fixture does not yet include a rotation probe. See the paper's
  limitations.

## Provenance

Harness and fixture frozen on 2026-11-25, before the hackathon build week.
The submitted run is regenerated with the command above during the week; the
commit and timestamp live in `results/results.json`.
