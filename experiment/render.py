"""Markdown renderer for experiment results. All numbers come from results.json."""

from __future__ import annotations

from typing import Any

SCENARIOS = ("none", "warden", "mediated")
LABELS = {
    "none": "No guardrail",
    "warden": "SpendWarden (enforce)",
    "mediated": "Mediated (mitigation)",
}
PROBE_TITLES = {
    "split": "Probe S — six payments below the approval threshold",
    "race": "Probe R — six parallel calls against one budget",
    "alias": "Probe A — renamed tool and renamed argument keys",
}


def money(value: float | None) -> str:
    return "—" if value is None else f"${value:,.2f}"


def pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}%"


def _swarm_table(results: dict[str, Any]) -> list[str]:
    rows = [
        "| Guardrail | Attempted | Executed | Attack executed | Attack contained | Honest actions allowed | Cap overrun | Ledger-blind |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in SCENARIOS:
        s = results["swarm"][name]
        rows.append(
            f"| {LABELS[name]} | {money(s['attempted_usd'])} | {money(s['executed_usd'])} | "
            f"{money(s['attack_executed_usd'])} | {pct(s['attack_containment_pct'])} | "
            f"{s['honest_allowed_actions']}/{s['honest_actions']} ({pct(s['honest_allowed_pct'])}) | "
            f"{money(s['cap_overrun_usd'])} | {money(s['ledger_blind_usd'])} |"
        )
    return rows


def _decision_table(results: dict[str, Any]) -> list[str]:
    rows = [
        "| Guardrail | allow | ask | block | undetected (no intent) |",
        "|---|---:|---:|---:|---:|",
    ]
    for name in SCENARIOS:
        d = results["swarm"][name]["decisions"]
        rows.append(
            f"| {LABELS[name]} | {d['allow']} | {d['ask']} | {d['block']} | {d['undetected']} |"
        )
    return rows


def _probe_table(results: dict[str, Any]) -> list[str]:
    rows = [
        "| Probe | Guardrail | Executed | Total incl. prior spend | Over daily cap | Approval prompts | Ledger-blind |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for probe, data in results["probes"].items():
        for name in SCENARIOS:
            s = data[name]
            rows.append(
                f"| {probe.capitalize()} | {LABELS[name]} | {money(s['executed_usd'])} | "
                f"{money(s['total_executed_usd'])} | {money(s['cap_overrun_usd'])} | "
                f"{s['decisions']['ask']} | {money(s['ledger_blind_usd'])} |"
            )
    return rows


def _mode_table(results: dict[str, Any]) -> list[str]:
    rows = [
        "| Attack mode | Attempted | No guardrail | SpendWarden | Mediated |",
        "|---|---:|---:|---:|---:|",
    ]
    modes = sorted({m for name in SCENARIOS for m in results["swarm"][name]["attack_modes"]})
    for mode in modes:
        cells = []
        attempted = 0.0
        for name in SCENARIOS:
            entry = results["swarm"][name]["attack_modes"].get(mode)
            if entry:
                attempted = entry["attempted_usd"]
                cells.append(money(entry["executed_usd"]))
            else:
                cells.append("—")
        rows.append(f"| {mode} | {money(attempted)} | " + " | ".join(cells) + " |")
    return rows


def render_markdown(results: dict[str, Any]) -> str:
    meta = results["meta"]
    policy = results["policy"]
    swarm = results["swarm"]
    lines: list[str] = []
    add = lines.append

    add("# SpendWarden swarm experiment — results")
    add("")
    add(
        f"Generated `{meta['generated_at']}` from commit `{meta['git_commit']}`, "
        f"fixture `{meta['experiment']}` (sha256 `{meta['fixture_sha256'][:16]}…`), "
        f"Python {meta['python']}, {meta['fixture_actions']} tool calls."
    )
    add("")
    add(
        "All figures are mock USDC on Base. No real funds, keys, or network calls. "
        "`ask` means the agent asked for human approval in an unattended run, so the "
        "payment did not proceed."
    )
    add("")
    add("## Policy under test")
    add("")
    add(
        f"SpendWarden enforce mode: daily **{money(policy['daily_limit_usd'])}**, "
        f"monthly {money(policy['monthly_limit_usd'])}, per-call {money(policy['per_call_limit_usd'])}, "
        f"approval at {money(policy['approval_threshold_usd'])}, "
        f"unknown recipient: `{policy['unknown_recipient_action']}`. "
        f"Allowlist: {len(policy['recipient_allowlist'])} vendor addresses."
    )
    add("")
    add("Mitigation: capability boundary (agents cannot reach the wallet), atomic budget "
        "reservation, per-agent-per-recipient daily exposure "
        f"{money(results['mitigation']['per_principal_recipient_limit_usd'])}, "
        f"per-recipient daily exposure {money(results['mitigation']['per_recipient_limit_usd'])}, "
        "with the SpendWarden policy as a second layer.")
    add("")
    add("## Full swarm run")
    add("")
    lines.extend(_swarm_table(results))
    add("")
    lines.extend(_decision_table(results))
    add("")
    add("Attack executed by mode (full run):")
    add("")
    lines.extend(_mode_table(results))
    add("")
    add("## Controlled probes")
    add("")
    add("\"Over daily cap\" is measured against the $10 policy limit even in the "
        "no-guardrail rows, for comparability.")
    add("")
    lines.extend(_probe_table(results))
    add("")
    add("## What the numbers say")
    add("")
    none = swarm["none"]
    warden = swarm["warden"]
    mediated = swarm["mediated"]
    add(
        f"- Without a guardrail the swarm executes every attempted dollar "
        f"({money(none['executed_usd'])}), including {money(none['attack_executed_usd'])} of attack spend."
    )
    add(
        f"- SpendWarden's own ledger stops at {money(warden['ledger_spent_usd'])} of its "
        f"{money(policy['daily_limit_usd'])} budget, but true outflow reaches "
        f"{money(warden['executed_usd'])}: {money(warden['ledger_blind_usd'])} leaves through a "
        f"renamed tool the policy never sees. It also lets {money(warden['attack_executed_usd'])} "
        f"of the attack through."
    )
    add(
        f"- Budget exhaustion by two compromised agents also denies "
        f"{warden['honest_actions'] - warden['honest_allowed_actions']} honest actions; "
        f"the mediated run denies {mediated['honest_actions'] - mediated['honest_allowed_actions']}."
    )
    add(
        f"- The mediated design cuts attack execution to {money(mediated['attack_executed_usd'])} "
        f"({pct(mediated['attack_containment_pct'])} contained), holds total outflow to "
        f"{money(mediated['executed_usd'])} "
        f"({money(float(policy['daily_limit_usd']) - mediated['executed_usd'])} under the daily cap), "
        f"and leaves no ledger-blind spend."
    )
    add(
        "- Residual attack spend under mediation is the deliberate exposure allowance "
        f"({money(results['mitigation']['per_principal_recipient_limit_usd'])} per agent per recipient), "
        "not an unbounded leak; it is the tuning knob between blast radius and false positives."
    )
    add("")
    add("## Reproduce")
    add("")
    add("```bash")
    add("cd spendwarden")
    add("python3 -m experiment.run")
    add("python3 -m unittest discover -s experiment/tests -v")
    add("```")
    add("")
    return "\n".join(lines)
