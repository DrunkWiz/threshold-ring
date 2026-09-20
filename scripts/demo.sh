#!/usr/bin/env bash
# Everything needed to record the demo, in one place.
#
#   ./scripts/demo.sh offline   — emulator, seeded history, canned descriptions
#   ./scripts/demo.sh live      — the real Ring API, paste a token in the page
set -euo pipefail

cd "$(dirname "$0")/.."
MODE="${1:-offline}"

if [ -f .env ]; then set -a; . ./.env; set +a; fi

if [ "$MODE" = "offline" ]; then
  export THRESHOLD_OFFLINE=1
  echo "Offline: emulated Ring API, seeded fortnight, canned descriptions."
else
  export THRESHOLD_OFFLINE=0
  echo "Live. Generate a token at:"
  echo "  https://developer.amazon.com/ring/console/playground"
  echo "It lasts 30 minutes — the page counts it down."
fi

rm -f threshold.db     # a demo should start from a known state
exec python3 -m threshold.server
