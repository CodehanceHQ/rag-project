.PHONY: setup check start clear db-up db-down api web

# Any Python 3.10 or newer. Override with: make setup PYTHON=/path/to/python
PYTHON ?= python3
export PYTHON

# Unusual ports on purpose, so they are unlikely to clash with other tools.
# They are also written in .env (FRONTEND_ORIGIN, NEXT_PUBLIC_API_URL).
API_PORT := 18001
WEB_PORT := 13001
export API_PORT WEB_PORT

COMPOSE := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose")
# Compose v2 can block until the container's health check passes.
WAIT := $(shell docker compose version >/dev/null 2>&1 && echo "--wait")

setup:
	@test -f .env || cp .env.example .env
	@test -f frontend/.env.local || grep '^NEXT_PUBLIC_API_URL=' .env > frontend/.env.local
	@test -x .venv/bin/python || $(PYTHON) -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r backend/requirements.txt
	cd frontend && npm install

check:
	@bash scripts/check.sh

start:
	@bash scripts/start.sh

# Wipes the database: all data and the search indexes, which are then rebuilt
# empty. Asks first; YES=1 skips the question.
clear: db-up
	@.venv/bin/python scripts/clear.py

db-up:
	$(COMPOSE) up -d $(WAIT) mongodb

db-down:
	$(COMPOSE) down

api:
	.venv/bin/uvicorn app.main:app --app-dir backend --reload --port $(API_PORT)

web:
	cd frontend && npm run dev -- -p $(WEB_PORT)
