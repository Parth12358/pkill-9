#!/bin/bash
# One command for the whole demo on one Mac: brain + plea room in the background, body in front.
#   ./demo.sh             brain on this Mac
#   ./demo.sh <brain-url> body only, brain elsewhere (e.g. http://10.0.0.5:5000)
# Ctrl+C kills ARIA (the brain keeps running for its next life). Ctrl+C twice = instant.
set -e
cd "$(dirname "$0")"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
PY=.venv/bin/python
[ -f .env ] || echo "warning: no .env (copy .env.example, add OPENROUTER_API_KEY + ELEVENLABS_API_KEY)"

if [ -n "$1" ]; then
  export BRAIN_URL="$1"
else
  export BRAIN_PORT="${BRAIN_PORT:-5055}"          # 5000 is AirPlay on macOS
  export PLEA_ROOM_PORT="${PLEA_ROOM_PORT:-5001}"
  if ! curl -s "localhost:$BRAIN_PORT/health" >/dev/null; then
    $PY -m brain.server > brain.log 2>&1 &
    echo "brain starting (log: brain.log)..."
    for _ in $(seq 30); do curl -s "localhost:$BRAIN_PORT/health" >/dev/null && break; sleep 0.3; done
  fi
  export BRAIN_URL="http://127.0.0.1:$BRAIN_PORT"
  IP=$(ipconfig getifaddr en0 2>/dev/null || echo localhost)
  echo "plea room:  http://$IP:$PLEA_ROOM_PORT     projector: http://$IP:$PLEA_ROOM_PORT/screen"
fi
exec $PY -m body
