# AIAF — record your voice in 3 minutes (phone only)

The only thing standing between us and the **$2,000 AIAF online prize** is a
3-minute video in your own voice. You do **not** need to record a screen: the
slides are ready, and the build script will put them under your voice.

## 1. Record (phone, ~3 minutes)

1. Open `docs/VIDEO_SLIDES/TELEPROMPTER.md` on your phone or print it.
2. Use the phone's Voice Memos / Recorder app in a quiet room.
3. Read the script in English, calmly, first person. Target **2:45–2:55**.
   Small stumbles are fine — do not stop and restart for them.
4. Save / share the file to this machine as:
   `~/AI/spendwarden/docs/voice.m4a`
   (m4a, wav, mp3 — anything the phone produces is fine).

Rules: the voice must be **yours** — no TTS, no AI voice changer, no somebody
else reading it. The organizers check that the video is in your own voice.
Do not add music over the voice.

## 2. Build the video (agent or one command)

```bash
cd ~/AI/spendwarden
python3 docs/VIDEO_SLIDES/build_video.py --audio docs/voice.m4a
```

It writes `docs/AIAF_VIDEO.mp4` (8 slides at the script's timings, your voice,
under 3:00) and prints the duration. If the voice is over 3:00 it refuses and
tells you how much to trim.

To test the pipeline without a voice (no submission):
```bash
python3 docs/VIDEO_SLIDES/build_video.py --audio /tmp/silence.m4a --allow-silent-test
```

## 3. Submit (12 Dec)

- Submit the video link + `docs/PAPER.pdf` through the link in the AIAF kickoff
  email (7 Dec).
- Record the confirmation in `knowledge/` and `kb.py log`.

## What is already done

- Online registration confirmed (2026-11-25).
- 2-page paper `docs/PAPER.pdf`, 8 slides, teleprompter, experiment with 18 tests.
- Repo public: https://github.com/matrixneoaiagent/spendwarden

## If you prefer to record the screen instead

That is allowed too: record the terminal running `python3 -m experiment.run`
and `RESULTS.md` while reading the same script; keep it under 3:00. The slide
video is simply less work.
