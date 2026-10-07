#!/usr/bin/env bash
# Checks that this machine has what the project needs. Reports every check,
# then exits non-zero if any failed. Installs nothing.
cd "$(dirname "$0")/.." || exit 1

PYTHON="${PYTHON:-python3}"
failed=0

ok()   { printf '  ok    %s\n' "$1"; }
fail() { printf '  FAIL  %s\n        fix: %s\n' "$1" "$2"; failed=1; }

echo "Checking dependencies"

# The virtual environment's interpreter is the one that runs the API, so check
# that if it exists; otherwise check the one `make setup` would build it from.
if [ -x .venv/bin/python ]; then py=.venv/bin/python; else py="$PYTHON"; fi
if ! command -v "$py" >/dev/null 2>&1; then
  fail "Python: '$py' not found" "install Python 3.10 or newer (brew install python)"
elif ! "$py" -c 'import sys; sys.exit(sys.version_info < (3, 10))'; then
  fail "Python: $("$py" --version 2>&1) is too old ($py)" "install Python 3.10 or newer, or run with PYTHON=/path/to/python"
else
  ok "Python: $("$py" --version 2>&1) ($py)"
fi

if ! command -v node >/dev/null 2>&1; then
  fail "Node.js: not found" "install Node.js 20.9 or newer (brew install node)"
elif ! node -e 'const [a,b]=process.versions.node.split(".").map(Number);process.exit(a>20||(a===20&&b>=9)?0:1)'; then
  fail "Node.js: $(node --version) is too old" "install Node.js 20.9 or newer"
else
  ok "Node.js: $(node --version)"
fi

if command -v npm >/dev/null 2>&1; then
  ok "npm: $(npm --version)"
else
  fail "npm: not found" "reinstall Node.js, which includes npm"
fi

if ! command -v docker >/dev/null 2>&1; then
  fail "Docker: not installed" "install OrbStack from https://orbstack.dev"
elif ! docker info >/dev/null 2>&1; then
  fail "Docker: installed but not running" "open -a OrbStack"
else
  ok "Docker: running"
fi

if docker compose version >/dev/null 2>&1; then
  ok "Docker Compose: $(docker compose version --short 2>/dev/null)"
elif command -v docker-compose >/dev/null 2>&1; then
  ok "Docker Compose: docker-compose (standalone)"
else
  fail "Docker Compose: not found" "it ships with OrbStack; install or start OrbStack"
fi

if [ "$failed" -ne 0 ]; then
  echo "Some checks failed."
  exit 1
fi
echo "All checks passed."
