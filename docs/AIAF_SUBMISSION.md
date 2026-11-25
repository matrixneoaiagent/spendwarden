# AIAF Brazil 2026 — online submission draft

**Title:** Containing runaway spend in agent swarms: a reproducible red-team of policy enforcement

**Track:** Swarms and multi-agent systems (also relevant to Evals for RSI)

**Team:** Matrix Neo (solo, online)

**Abstract:**  
Agents can escalate spend and tool use faster than a human can review, and prompt-level rules are not a boundary: split calls, races and aliased arguments can slip through. We red-team a policy layer with a frozen 64-call swarm script (30 honest actions, 34 adversarial) under three guardrails: none, SpendWarden, and a mediated mitigation. SpendWarden contains 47.3% of attack spend but leaks through three concrete failure modes — splitting, concurrency and argument aliasing. A capability boundary plus atomic reservation, per-agent/per-recipient exposure and fail-closed parsing raises containment to 80.4% and closes all three probes, at the cost of one honest false positive in 30. We publish the harness, the fixture and the paper so the result is reproducible, and argue that alignment for self-improving systems must be enforced where money moves, not only in text.

**Deliverables:**
- Repo: https://github.com/matrixneoaiagent/spendwarden
- Paper (2 pages): `docs/PAPER.pdf`
- Video (3 min, own voice): `docs/VIDEO_SCRIPT.md` + slides in `docs/VIDEO_SLIDES/`
- Experiment: `experiment/` (18 tests, frozen 64-call fixture, generated results)

**In-week work to do (7–11 Dec):** re-run `python3 -m experiment.run`, regenerate `experiment/results/`, update the paper numbers if they change, record the 3-minute video in the first person, and submit the video + 2-page PDF before Saturday morning (exact hour TBA).

**Prior-work disclosure:** SpendWarden and the experiment harness were built before the event; the paper explicitly distinguishes the pre-event code from the in-week rerun, analysis and video. No result is presented as in-week work unless it is regenerated during 7–11 Dec.

**Submission checklist:** registration done (online, 2026-11-25); paper 2 pages (done); video (pending, user voice); exact deadline from kickoff email; submit via the event page at kickoff.
