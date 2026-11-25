#!/usr/bin/env python3
"""Build the AIAF Brazil 3-minute video from the 8 prepared slides + the user's own voice.

Usage:
    python3 docs/VIDEO_SLIDES/build_video.py --audio /path/to/voice.m4a
    python3 docs/VIDEO_SLIDES/build_video.py --audio voice.wav --out docs/AIAF_VIDEO.mp4

The audio must be the user's own voice reading docs/VIDEO_SLIDES/TELEPROMPTER.md.
The script muxes the slides at the script's section timings; if the voice track is
longer than 2:50 it extends the last slide, and refuses to produce a video over 3:00.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent
# Section durations from docs/VIDEO_SCRIPT.md (0:00, 0:25, 0:50, 1:10, 1:25, 1:45, 2:05, 2:35).
DURATIONS = [25, 25, 20, 15, 20, 20, 30, 15]  # 170 s = 2:50
MAX_SECONDS = 180.0


def ffmpeg() -> str:
    for name in ("ffmpeg", "/nix/store/42z02ipbn03xsbg07yih4983pbqhwgjw-ffmpeg-7.1.1-bin/bin/ffmpeg"):
        p = shutil.which(name) if not name.startswith("/") else (name if Path(name).exists() else None)
        if p:
            return p
    raise SystemExit("ffmpeg not found")


def ffprobe() -> str:
    for name in ("ffprobe", "/nix/store/42z02ipbn03xsbg07yih4983pbqhwgjw-ffmpeg-7.1.1-bin/bin/ffprobe"):
        p = shutil.which(name) if not name.startswith("/") else (name if Path(name).exists() else None)
        if p:
            return p
    raise SystemExit("ffprobe not found")


def audio_duration(path: Path) -> float:
    out = subprocess.run(
        [ffprobe(), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise SystemExit(f"cannot read audio: {out.stderr[-300:]}")
    return float(out.stdout.strip())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audio", required=True, help="the user's own-voice recording (m4a/wav/mp3)")
    ap.add_argument("--out", default=str(BASE.parent / "AIAF_VIDEO.mp4"))
    ap.add_argument("--allow-silent-test", action="store_true", help="build a test video without a real voice track")
    args = ap.parse_args()

    audio = Path(args.audio).expanduser()
    if not audio.exists():
        raise SystemExit(f"audio not found: {audio}")
    dur = audio_duration(audio)
    print(f"audio: {audio} ({dur:.1f}s)")
    if dur < 120:
        print("warning: under 2:00; the script is ~2:50, check the recording", file=sys.stderr)
    if dur > MAX_SECONDS:
        raise SystemExit(f"audio is {dur:.1f}s; the competition limit is 3:00. Trim it to <=180s and retry.")
    if not args.allow_silent_test and dur < 30:
        raise SystemExit("audio is under 30s; pass --allow-silent-test only for pipeline testing")

    slides = [BASE / f"slide{i}.png" for i in range(1, 9)]
    for s in slides:
        if not s.exists():
            raise SystemExit(f"missing slide: {s}")

    # Extend the last slide if the voice track runs longer than the scripted 2:50.
    durations = list(DURATIONS)
    total = sum(durations)
    if dur > total:
        durations[-1] += dur - total
    listfile = BASE / "concat.txt"
    lines = []
    for s, d in zip(slides, durations):
        lines.append(f"file '{s}'")
        lines.append(f"duration {d}")
    lines.append(f"file '{slides[-1]}'")
    listfile.write_text("\n".join(lines) + "\n")

    out = Path(args.out)
    cmd = [
        ffmpeg(), "-y",
        "-f", "concat", "-safe", "0", "-i", str(listfile),
        "-i", str(audio),
        "-map", "0:v:0", "-map", "1:a:0",
        "-vf", "fps=30,format=yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20",
        "-c:a", "aac", "-b:a", "160k",
        "-shortest", "-movflags", "+faststart",
        str(out),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1200:], file=sys.stderr)
        raise SystemExit("ffmpeg failed")
    d = subprocess.run(
        [ffprobe(), "-v", "error", "-show_entries", "format=duration,size",
         "-show_entries", "stream=width,height,codec_name", "-of", "default=noprint_wrappers=1", str(out)],
        capture_output=True, text=True,
    )
    print(d.stdout.strip())
    print(f"written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
