.PHONY: help install install-web test test-engine test-api test-postgres \
        test-web test-e2e api web seed migration lint clean

PYTHON ?= python3
VENV   ?= .venv
BIN    := $(VENV)/bin

help:
	@echo "Atlas"
	@echo ""
	@echo "  make install      Create a virtualenv and install the Python packages"
	@echo "  make install-web  Install the web app's dependencies"
	@echo "  make test         Run the Python test suites"
	@echo "  make test-postgres Schema and RLS tests against a real PostgreSQL"
	@echo "  make test-web     Run the Vitest unit tests"
	@echo "  make test-e2e     Run the Playwright end-to-end tests"
	@echo "  make api          Run the API on :8000"
	@echo "  make web          Run the web app on :3000"
	@echo "  make seed         Load demo properties"
	@echo "  make migration    Regenerate the SQL schema from the models"

$(VENV):
	$(PYTHON) -m venv $(VENV)

install: $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e packages/financial-engine[dev]
	$(BIN)/pip install -e packages/scoring-engine[dev]
	$(BIN)/pip install -e packages/data-providers[dev]
	$(BIN)/pip install -e packages/ai-agents[dev]
	$(BIN)/pip install -e apps/api[dev]

install-web:
	cd apps/web && npm install

test: test-engine test-api

test-engine:
	cd packages/financial-engine && ../../$(BIN)/pytest -q
	cd packages/scoring-engine && ../../$(BIN)/pytest -q
	cd packages/data-providers && ../../$(BIN)/pytest -q
	cd packages/ai-agents && ../../$(BIN)/pytest -q

test-api:
	cd apps/api && ../../$(BIN)/pytest -q

# Schema and row-level-security tests. Skipped by `make test` because they
# need a live PostgreSQL; point ATLAS_TEST_POSTGRES_URL at one to run them.
# The URL must name a role allowed to CREATE DATABASE and CREATE ROLE: each
# test module builds its own throwaway database and drops it afterwards.
ATLAS_TEST_POSTGRES_URL ?= postgresql://atlas:atlas@127.0.0.1:5432/postgres

test-postgres:
	cd apps/api && ATLAS_TEST_POSTGRES_URL="$(ATLAS_TEST_POSTGRES_URL)" \
		../../$(BIN)/pytest -q tests/test_postgres_schema.py tests/test_rls.py

test-web:
	cd apps/web && npm run test

test-e2e:
	cd apps/web && npm run test:e2e

api:
	$(BIN)/uvicorn atlas_api.main:app --reload --port 8000 --app-dir apps/api

web:
	cd apps/web && npm run dev

seed:
	$(BIN)/python database/seeds/seed_demo.py

migration:
	$(BIN)/python scripts/generate_migration.py

lint:
	cd apps/web && npm run lint

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
	rm -rf apps/web/.next apps/web/node_modules
