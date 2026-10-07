#!/usr/bin/env bash
# Starts the whole system: checks dependencies, sets up if needed, starts
# MongoDB, then the API and the UI. Safe to run again: anything already
# running is left alone.
cd "$(dirname "$0")/.." || exit 1

API_PORT=8001
WEB_PORT=3001

listening() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

bash scripts/check.sh || exit 1

if [ ! -x .venv/bin/python ] || [ ! -d frontend/node_modules ] || [ ! -f .env ] || [ ! -f frontend/.env.local ]; then
  echo "First-time setup"
  make setup || exit 1
fi

echo "Starting MongoDB"
make db-up || exit 1

pids=""
stop() {
  trap - INT TERM EXIT
  [ -n "$pids" ] && kill $pids 2>/dev/null
  wait
}
trap stop INT TERM EXIT

if listening "$API_PORT"; then
  echo "API already running on port $API_PORT"
else
  make api &
  pids="$pids $!"
fi

if listening "$WEB_PORT"; then
  echo "UI already running on port $WEB_PORT"
else
  make web &
  pids="$pids $!"
fi

if [ -z "$pids" ]; then
  echo "Everything is already running: http://localhost:$WEB_PORT"
  exit 0
fi

echo "Open http://localhost:$WEB_PORT (Ctrl+C stops what this command started)"
wait
