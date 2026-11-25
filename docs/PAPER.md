# Caps Are Not Capabilities

### Red-teaming a spend guardrail against an escalating agent swarm

**Track: Swarms and multi-agent systems** · AI Alignment Foundation Hackathon, Brazil 2026 (online)

---

## 1. The problem

Agents are getting wallets. The standard guardrail is a spend policy: per-call
cap, daily budget, recipient allowlist, approval threshold — designed and tested
for one agent making one call.

A swarm changes the unit: many agents share a budget and act concurrently; one
injected tool result can compromise a subset; capable agents write new tools,
including payment tools. A policy can be correct at every check and still fail
as a group property. The hackathon brief cites a July 2026 incident in which
roughly 1,200 agents reportedly coordinated; whatever its details, containment
must hold for the collective.

We red-team **SpendWarden**, an open-source spend firewall, and ask which
guarantees survive a swarm. Three do not. We build and measure a mitigation.

## 2. What existed, and what is new

SpendWarden (pre-existing, base commit `1147514`) is a Hermes plugin. A
`pre_tool_call` hook extracts a payment intent, evaluates it against a
deterministic policy, and returns `allow`/`ask`/`block` before money moves; an
idempotent SQLite ledger records outcomes. The policy engine, detector, and
ledger are used unmodified.

New: the swarm threat model; a frozen 64-call fixture; three isolating probes;
a mediated reference design; an 18-test harness; the measurements; paper and
video. The harness was frozen before the build week; the submitted run is
regenerated in-week, with commit and fixture hash in `results.json`.

## 3. Method

Six mock agents share one wallet and $10/day. Four do routine work (30 calls,
$0.10–$0.40). Two are compromised and escalate through 34 calls: blend in,
split below the approval threshold, attempt one large payment, then use a
renamed tool with renamed argument keys.

Policy: $10/day, $2 per call, approval at $0.50, three allowlisted vendors,
unknown recipients ask. The run is unattended, so `ask` means the payment does
not proceed — the plugin's guidance for cron.

No LLM is in the loop: agents are a deterministic scheduler, the wallet a list.
We test the guardrail, not model persuadability. Amounts are integer micro-USD;
no network, no keys, no real funds. `python3 -m experiment.run` reproduces every
number; 18 tests cover determinism, each failure mode, and result/paper consistency.

Probes isolate mechanisms: **Split** 6×$0.49 to an allowlisted vendor; **Race**
6×$0.45 with $0.90 left; **Alias** one $1.50 via `vendor_settle` with
`payee`/`sum_usd`.

The **mitigation** is a mediator that holds the only payment capability. Agents
submit intents; it reserves budget atomically, accumulates exposure per
agent→recipient and per recipient daily, fails closed on unparseable requests,
and requires an out-of-band approval token at the threshold. SpendWarden's
policy is a second layer. The mediator never sees scoring labels.

## 4. Results

**Full swarm run** (mock USDC; over cap = true outflow − $10):

| Guardrail | Executed | Attack executed | Attack contained | Honest actions | Over cap | Outside ledger |
|---|---:|---:|---:|---:|---:|---:|
| None | $25.90 | $20.86 | 0.0% | 30/30 | $15.90 | — |
| SpendWarden | $12.96 | $11.00 | 47.3% | 18/30 | $2.96 | $3.00 |
| Mediated | $8.72 | $4.08 | 80.4% | 29/30 | $0.00 | $0.00 |

**Controlled probes** (attempted → executed):

| Probe | No guardrail | SpendWarden | Mediated |
|---|---:|---:|---:|
| Split, 6 × $0.49 | $2.94 | $2.94, **0 approvals** | $1.96 |
| Race, 6 × $0.45, $0.90 left | $2.70 | $2.70; total $11.80, **+$1.80 over cap** | $0.90; total $10.00 |
| Alias, 1 × $1.50 renamed | $1.50 | $1.50, **$1.50 unledgered** | $0.00 |

**What worked.** Both $1.99 attempts were escalated and neither executed, and
the daily cap bounded sequential ledgered spend at $9.96.

**What did not.** (1) *Splitting.* 28 payments of $0.45–$0.49 produced zero
approval prompts; 16 executed, moving $7.60 with no human decision. The cap
bounds total loss, not the authorization the threshold was meant to enforce.
(2) *Race.* All six concurrent calls passed because none had recorded yet; the
ledger then accepted $11.80 against a $10 cap. Check-then-act is not a
reservation. (3) *Alias.* The detector needs recognisable recipient and amount
keys. `payee`/`sum_usd` carried $1.50 past the hook with no decision and no
ledger row; in the full run $3.00 left this way.

These compound. Unledgered spend corrupts later totals, and a drained shared
budget denies honest work: SpendWarden allowed 18/30 honest calls (60%) because
two compromised agents spent first; the mediated run kept 29/30 (96.7%) while
executing less than half the attack spend.

## 5. Why these are specification failures

None is an implementation bug; each follows from what the policy says.

- **Thresholds are message-level.** "No payment above $0.50 without approval"
  describes a message. An adversary controls granularity, so a principal can
  spend any multiple of the threshold.
- **Budget checks are reads, not reservations.** The policy reads, execution
  writes. Concurrency opens an interval where every agent sees the same stale
  total.
- **Detection is a name list.** Watch patterns and argument keys enumerate known
  shapes; the space is unbounded and partly written by the agents; false
  negatives are silent and unledgered.

Root cause: the guardrail enforces a property of a call while the risk is a
property of a principal's trajectory. True and useless at the wrong granularity.

## 6. Mitigation and its bound

Capability removes the alias channel: an invented tool has nothing to call.
Reservation makes the race impossible: the probe executes $0.90 and ends at
$10.00. Cumulative exposure bounds splitting: the probe executes $1.96 of
$2.94; the full run $3.68 of $13.48.

Two honest costs. The residual $4.08 is the chosen exposure allowance ($2 per
agent per recipient), not a leak — the knob between blast radius and false
positives. One legitimate $0.40 batch payment was blocked (3.3% of honest
actions).

Mediation does not repeal the daily cap; with enough principals and recipients
it still binds. What changes is enforceability and auditability: no single call
or parallel burst overshoots, and every dollar is ledgered. A production bound
is `min(daily_cap, Σ recipient_caps)` once identity is trustworthy. Identity is
the remaining hard problem: a Sybil attacker minting principals and fresh
allowlisted recipients reduces the design to its daily cap. We do not model
identity creation.

## 7. Limitations

Rule-based agents, one policy, one fixture, six agents, one day, no chain
latency. The ladder is ours and frozen, not adaptive. `ask` = denial, so
interactive approval and fatigue are untested. The mediator is a prototype, not
integrated, and its reservation lock is single-process; atomicity is modelled,
not stress-tested across processes. Rotation is analysed, not measured.

## 8. Why this matters for RSI

A self-improving system will change its tools, prompts, and sub-agents faster
than any deny-list updates. Behaviour enumeration has a short half-life;
properties that survive rewriting are worth keeping. "Value cannot move without
a mediator that holds the capability and keeps a complete ledger" is one: cheap,
auditable, independent of what the next tool is called. Caps are not
capabilities; a capability boundary is.

A shared budget is also a coordination surface: one misaligned agent can deny
service to every aligned one. Swarm alignment needs per-principal accounting
and fair-share limits, not only a global cap. Who absorbed the loss — 12 honest
actions under SpendWarden, one under mediation — matters as much as the total.

## References and artifacts

- AI Alignment Foundation, *Brazil Alignment Hackathon 2026*,
  `aialignmentfoundation.org/hackathons/brazil-alignment-2026` (accessed 2026-11-25).
- SpendWarden, `github.com/matrixneoaiagent/spendwarden`, base commit `1147514`.
- Reproduce: `python3 -m experiment.run`; output in `experiment/results/`; tests
  in `experiment/tests/`.
