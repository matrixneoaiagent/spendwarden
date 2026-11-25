# AIAF Brazil 2026 — event rules and submission checklist

Source: <https://aialignmentfoundation.org/hackathons/brazil-alignment-2026>,
fetched 2026-11-25. The page says "Details are subject to change", so re-check
at kickoff.

## Facts confirmed on the event page

| Item | Detail |
|---|---|
| Event | AI Alignment Hackathon in Brazil, organised by the AI Alignment Foundation with AE Studio |
| Dates | 7–12 December 2026 (kickoff Mon 7 Dec; build days Tue–Fri 8–11; submissions and presentations Sat 12) |
| Format | In person at Costão do Santinho, Florianópolis, **and online from anywhere** |
| Cost | Free |
| Team size | 1–3 |
| Online prize pool | **$2,000**: 1st $1,000, 2nd $500, 3rd $300, 4th $100, 5th $100 |
| In-person pool | Over $5,000 (separate; not our path) |
| Submission | A **3-minute video**, narrated in **English, in your own voice**, plus a **2-page write-up** |
| Deadline | Saturday morning, 12 December; exact time "will be announced soon" / at kickoff |
| Results | Online winners announced the following week, judged separately from in-person |
| Submission page | Shared at kickoff ("a dedicated page where you'll join and submit your video and write-up") |
| Language | English required for video, write-up, and presentations. Portuguese not accepted |
| Prior work | Allowed. Must make clear what was done before the hackathon and what was done during the week. **Only work done during the hackathon is judged** |
| AI tools | Allowed, but the team is responsible for every result, number, and reference |
| Expertise | None required |

## Tracks (pick one to anchor; cross-track work welcome)

1. **Swarms and multi-agent systems** — alignment as a group property; coordination,
   spread of misalignment between agents, honeypots for rogue swarms.
2. **Evals for RSI** — tests that show whether alignment holds as a model changes
   itself; fine-tuning drift, self-generated training data, self-steering.
3. **Model psychology and personas** — whether character survives self-change.
4. **Alignment invariants** — properties that make a system more capable by making
   it more aligned, so self-improvement keeps them.
5. **Neglected approaches** — anything else with an experiment behind it.

This project anchors on **Track 1**, with a Track 4 argument (a capability
boundary is an invariant that survives tool invention).

## Judging criteria

1. **Idea, novelty and relevance** — a real, significant problem; fresh rather
   than a rehash.
2. **Soundness and execution** — does the approach make sense, and did the team
   actually attempt it during the week?
3. **Results** — do they make sense and support the idea? Negative results are
   fine if they genuinely test something.
4. **Clarity of communication** — can a viewer follow problem, method, findings
   from the video and write-up?

## What the page does not state

- No page template, citation style, or repo-link requirement is specified.
- No KYC, fee, or geographic restriction is mentioned for the online track.
- No exact submission hour yet; no confirmation of whether the write-up is
  uploaded as PDF or pasted. Do not assume; read the kickoff page.

## Compliance notes for this submission

- The experiment uses mock USDC on Base only. No keys, no accounts, no real
  funds, no network calls.
- SpendWarden (policy engine, detector, ledger, original 38 tests) existed
  before the hackathon. The swarm threat model, harness, frozen 64-call fixture,
  three probes, mediated prototype, 18 experiment tests, measurements, paper,
  and video are new.
- No account was created and nothing was submitted by the research subagent.
  Registration and submission are the orchestrator's job.
- Do not overstate: agents are rule-based, the adversary is not adaptive, and
  `ask` is treated as denial because the run is unattended. These limits are in
  the paper.

## Orchestrator checklist before 12 December

1. Register for the **online** track (not done here). Note the account email used.
2. On 7 December, re-read the event page and the kickoff instructions; capture
   the exact deadline and submission URL in `knowledge/`.
3. Run the locked experiment during the build week and commit the output:
   `cd spendwarden && python3 -m experiment.run && python3 -m unittest discover -s experiment/tests -v`
4. Confirm the paper's numbers still match `experiment/results/results.json`
   (the harness is deterministic; if a number moved, the paper is wrong).
5. Update the paper's provenance line if the commit hash or date is quoted.
6. Record the 3-minute video from `docs/VIDEO_SCRIPT.md` in the user's own
   voice, in English. Check runtime is under 3:00.
7. Render `docs/PAPER.md` to PDF at ~10.5pt with 0.75in margins and verify it is
   **2 pages**. If it spills, trim section 7 or the references, not the results.
8. Submit video + write-up through the kickoff page before the deadline, and
   record the confirmation in the knowledge base.
9. If the rules differ materially at kickoff (deadline, format, page limit),
   stop and re-plan before submitting.
