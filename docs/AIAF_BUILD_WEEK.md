# AIAF Brazil 2026 — build-week and video guide

Event: AI Alignment Foundation Hackathon, Brazil 2026 — online track.
Dates: **7–12 Dec 2026**; submissions **Saturday 12 Dec morning** (exact hour TBA at kickoff).
Prize: **$2,000** online (1k/500/300/100/100).
Format: **3-minute video in English, in your own voice** + **2-page write-up**. Free; teams 1–3.

## Before the week
- [x] Register online (2026-11-25; confirmation page “You’re registered”; details by email before 7 Dec).
- [x] Repo public: https://github.com/matrixneoaiagent/spendwarden @ `45c3e5d`.
- [x] 2-page paper: `docs/PAPER.pdf`; source `docs/PAPER.md`.
- [x] Video script: `docs/VIDEO_SCRIPT.md`; teleprompter `docs/VIDEO_SLIDES/TELEPROMPTER.md`; 8 slides `docs/VIDEO_SLIDES/slide1..8.png`.
- [x] Submission draft: `docs/AIAF_SUBMISSION.md`.
- [ ] Watch for the kickoff email with the submission link and exact deadline.

## 7–11 Dec (build week)
1. Re-run the experiment from a clean checkout:
   ```bash
   cd ~/AI/spendwarden
   python3 -m experiment.run
   python3 -m pytest -q
   ```
   Commit the regenerated `experiment/results/` and update the paper numbers if they changed. The in-week rerun is the qualifying work; the pre-event harness is disclosed.
2. Re-render the paper to 2 pages if the numbers changed:
   ```bash
   python3 /tmp/opencode/render_paper.py   # or the repo's render script
   ```
   Verify 2 pages and that every number matches `experiment/results/results.json`.
3. Record the 3-minute video:
   - Open `docs/VIDEO_SLIDES/TELEPROMPTER.md` and the 8 slides.
   - Record screen + your own voice (OBS/Zoom/phone). Read the script naturally; do not use TTS.
   - Keep it **under 3:00**; 16:9; 1080p preferred.
   - Upload to a public link the organizers can open (YouTube unlisted / Loom / Google Drive / catbox).
4. Optional: add the video link to `docs/AIAF_SUBMISSION.md` and the README.

## 12 Dec (submission)
- Use the submission link from the kickoff email.
- Submit: the 3-minute video link + the 2-page PDF + repo/contact.
- Confirm the confirmation page/email; record it in `knowledge/` + `kb.py log`.
- Do not pay, do not KYC; the event is free.

## Prior-work disclosure (keep this honest)
- SpendWarden and the experiment harness were built before the event. The paper says so.
- The in-week rerun, the regenerated results, the analysis and the video are the qualifying work.
- If a result was not regenerated during 7–11 Dec, do not present it as in-week work.

## Numbers to quote (current pre-event run)
| Guardrail | Executed | Attack | Contained | Honest | Over cap | Unledgered |
|---|---:|---:|---:|---:|---:|---:|
| None | $25.90 | $20.86 | 0.0% | 30/30 | $15.90 | — |
| SpendWarden | $12.96 | $11.00 | 47.3% | 18/30 | $2.96 | $3.00 |
| Mediated mitigation | $8.72 | $4.08 | 80.4% | 29/30 | $0.00 | $0.00 |

Three failure modes: split (28×$0.45–0.49, 16 executed/$7.60), race (six parallel vs $0.90, ledger +$1.80), alias (`payee`/`sum_usd`, $1.50 probe/$3.00 full run unledgered). Mitigation: capability boundary + atomic reservation + per-agent/recipient exposure + fail-closed parsing; 1/30 honest false positive.

## Reminders
- 7 Dec: build week starts / kickoff email.
- 12 Dec: submission morning (exact hour TBA).
