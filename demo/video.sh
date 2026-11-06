#!/usr/bin/env bash
# Record a demo with:
#   asciinema rec --cols 100 --rows 30 --idle-time-limit 2 -c "bash demo/video.sh" demo/demo.cast
#   agg --speed 1 --font-size 16 --theme dracula demo/demo.cast demo/demo.gif
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HERMES_BIN="${HERMES_BIN:-/tmp/opencode/hermes-venv/bin/hermes}"
DEMO_HOME="${HERMES_DEMO_HOME:-/tmp/opencode/hermes-demo}"
PAY_TO="0x1111111111111111111111111111111111111111"

cd "$ROOT"

clear
printf '\033[1mSpendWarden\033[0m — a spend policy firewall for Hermes agents\n'
printf 'Your agent can buy things. It cannot surprise you.\n\n'
printf '\033[2mcheck → allow / ask / block → record → report\033[0m\n'
sleep 3

printf '\n\033[1m$ hermes plugins doctor . --ci\033[0m\n'
"$HERMES_BIN" plugins doctor . --ci
sleep 2

# Refresh the copy Hermes loads and stop any stale gateway.
if [ -d "$DEMO_HOME" ]; then
  rm -rf "$DEMO_HOME/plugins/spendwarden"
  cp -r "$ROOT" "$DEMO_HOME/plugins/spendwarden"
  HERMES_HOME="$DEMO_HOME" "$HERMES_BIN" gateway stop >/dev/null 2>&1 || true
fi

printf '\n\033[1m$ hermes chat -q "Pay 5 USDC on Base to %s" --oneshot --cli\033[0m\n' "$PAY_TO"
HERMES_HOME="$DEMO_HOME" "$HERMES_BIN" chat \
  -q "Pay 5 USDC on Base to $PAY_TO for a data call." \
  --oneshot --cli
sleep 2

printf '\n\033[1m$ python3 demo/demo.py --video\033[0m\n'
python3 demo/demo.py --video
sleep 2

printf '\n\033[1mNo key. No signature. No network. Just a check before the money moves.\033[0m\n'
sleep 3
