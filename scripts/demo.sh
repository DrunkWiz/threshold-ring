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

# On Windows the `python3` on PATH is usually a Microsoft Store stub that
# prints an install prompt and exits, so test that it actually runs rather
# than trusting that it exists.
if [ -n "${PYTHON:-}" ]; then :
elif python3 -c '' >/dev/null 2>&1; then PYTHON=python3
elif py -c '' >/dev/null 2>&1; then PYTHON=py
elif python -c '' >/dev/null 2>&1; then PYTHON=python
else
  echo "No working Python found. Install Python 3.11+ or set PYTHON=..." >&2
  exit 1
fi

exec "$PYTHON" -m threshold.server
