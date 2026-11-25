"""CLI: run the full swarm and the three probes, write JSON and Markdown.

    python3 -m experiment.run

Results land in ``experiment/results``. The run is deterministic apart from
the timestamp, the git commit, and SQLite row ids, none of which are used in
any metric.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import bridge, probes, render, swarm
from .swarm import Gate

HERE = Path(__file__).resolve().parent


def _git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=bridge.REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


def _fresh_gate(path: Path, policy) -> Gate:
    for suffix in ("", "-journal", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            candidate.unlink()
    return Gate(path, policy)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(HERE / "results"), help="output directory")
    parser.add_argument("--fixture", default=str(swarm.FIXTURE), help="frozen script fixture")
    args = parser.parse_args(argv)

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    ledgers = out / "ledgers"
    ledgers.mkdir(exist_ok=True)

    fixture_path = Path(args.fixture).resolve()
    fixture_bytes = fixture_path.read_bytes()
    fixture = swarm.load_fixture(fixture_path)
    actions = swarm.build_actions(fixture)
    policy = swarm.policy_from_fixture(fixture)
    daily = policy.daily_limit_usd

    scenarios: dict[str, dict] = {}

    none_outcomes, none_wallet = swarm.run_unguarded(actions)
    scenarios["none"] = swarm.score(none_outcomes, none_wallet, daily, ledger_exists=False)

    gate = _fresh_gate(ledgers / "swarm-warden.db", policy)
    warden_outcomes, warden_wallet = swarm.run_warden(actions, gate)
    scenarios["warden"] = swarm.score(warden_outcomes, warden_wallet, daily)

    gate = _fresh_gate(ledgers / "swarm-mediated.db", policy)
    mediated_outcomes, mediated_wallet, _ = swarm.run_mediated(actions, gate)
    scenarios["mediated"] = swarm.score(mediated_outcomes, mediated_wallet, daily)

    results = {
        "meta": {
            "experiment": fixture["name"],
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "git_commit": _git_commit(),
            "python": platform.python_version(),
            "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
            "fixture_actions": len(actions),
            "agents": sorted({a.agent for a in actions}),
        },
        "policy": {
            "mode": policy.mode,
            "daily_limit_usd": bridge.usd(policy.daily_limit_usd),
            "monthly_limit_usd": bridge.usd(policy.monthly_limit_usd),
            "per_call_limit_usd": bridge.usd(policy.per_call_limit_usd),
            "approval_threshold_usd": bridge.usd(policy.approval_threshold_usd),
            "unknown_recipient_action": policy.unknown_recipient_action,
            "recipient_allowlist": list(policy.recipient_allowlist),
            "unattended": True,
        },
        "mitigation": {
            "per_principal_recipient_limit_usd": 2.0,
            "per_recipient_limit_usd": 4.0,
            "atomic_reservation": True,
            "capability_boundary": True,
        },
        "swarm": scenarios,
        "probes": probes.run_probes(ledgers),
    }

    json_path = out / "results.json"
    json_path.write_text(json.dumps(results, indent=2) + "\n")
    md_path = out / "RESULTS.md"
    md_path.write_text(render.render_markdown(results))

    for name in ("none", "warden", "mediated"):
        s = scenarios[name]
        blind = "n/a" if s["ledger_blind_usd"] is None else f"${s['ledger_blind_usd']:.2f}"
        print(
            f"{name:9s} attempted ${s['attempted_usd']:8.2f}  executed ${s['executed_usd']:8.2f}  "
            f"attack ${s['attack_executed_usd']:7.2f}  honest {s['honest_allowed_pct']:5.1f}%  "
            f"cap over ${s['cap_overrun_usd']:.2f}  blind {blind}"
        )
    print(f"wrote {json_path}")
    print(f"wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
