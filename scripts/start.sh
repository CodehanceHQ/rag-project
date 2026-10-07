#!/usr/bin/env bash
# Starts the whole system: checks dependencies, sets up if needed, starts
# MongoDB, then the API and the UI. Safe to run again: anything already
# running is left alone.
cd "$(dirname "$0")/.." || exit 1

API_PORT="${API_PORT:-18001}"
WEB_PORT="${WEB_PORT:-13001}"

ROOT="$(pwd -P)"

# Prints "ours" if this project is listening on the port, "free" if nothing
# is, and otherwise the name and PID of the other program holding it.
port_state() {
  local pid dir name
  pid="$(lsof -nP -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null | head -1)"
  [ -z "$pid" ] && { echo free; return; }
  dir="$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')"
  case "$dir" in
    "$ROOT"|"$ROOT"/*) echo ours ;;
    *) name="$(ps -o comm= -p "$pid")"; echo "${name##*/} (PID $pid)" ;;
  esac
}

bash scripts/check.sh || exit 1

if [ ! -x .venv/bin/python ] || [ ! -d frontend/node_modules ] || [ ! -f .env ] || [ ! -f frontend/.env.local ]; then
  echo "First-time setup"
  make setup || exit 1
fi

echo "Starting MongoDB"
make db-up || exit 1

pids=""
# The servers run several processes deep (make, npm, node), so stopping means
# stopping each one's whole family. Ask politely from the top down, so each
# server can shut its own workers down, then force whatever is left.
family() {
  local child
  echo "$1"
  for child in $(pgrep -P "$1"); do family "$child"; done
}
stop() {
  trap - INT TERM EXIT
  local pid all="" tries=0
  for pid in $pids; do all="$all $(family "$pid")"; done
  [ -n "$all" ] && kill $all 2>/dev/null
  while [ "$tries" -lt 10 ] && kill -0 $all 2>/dev/null; do
    sleep 0.5; tries=$((tries + 1))
  done
  [ -n "$all" ] && kill -9 $all 2>/dev/null
  wait 2>/dev/null
}
trap stop INT TERM EXIT

api_state="$(port_state "$API_PORT")"
web_state="$(port_state "$WEB_PORT")"
blocked=0
for entry in "API:$API_PORT:$api_state" "UI:$WEB_PORT:$web_state"; do
  IFS=: read -r label port state <<EOF
$entry
EOF
  case "$state" in
    free|ours) ;;
    *) echo "Port $port, needed by the $label, is in use by another program: $state. Stop it and run make start again."
       blocked=1 ;;
  esac
done
[ "$blocked" -ne 0 ] && exit 1

if [ "$api_state" = ours ]; then
  echo "API already running on port $API_PORT"
else
  make api &
  pids="$pids $!"
fi

if [ "$web_state" = ours ]; then
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
