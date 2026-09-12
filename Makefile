.PHONY: setup db-up db-down api web

COMPOSE := $(shell docker compose version >/dev/null 2>&1 && echo "docker compose" || echo "docker-compose")

setup:
	@test -f .env || cp .env.example .env
	@test -f frontend/.env.local || grep '^NEXT_PUBLIC_API_URL=' .env > frontend/.env.local
	python3.11 -m venv .venv
	.venv/bin/pip install --upgrade pip
	.venv/bin/pip install -r backend/requirements.txt
	cd frontend && npm install

db-up:
	$(COMPOSE) up -d mongodb

db-down:
	$(COMPOSE) down

api:
	.venv/bin/uvicorn app.main:app --app-dir backend --reload --port 8000

web:
	cd frontend && npm run dev
