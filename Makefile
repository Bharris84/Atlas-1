.PHONY: help install install-web test test-engine test-api test-postgres \
        test-web test-e2e api web seed lint clean \
        db-upgrade db-downgrade db-current db-history db-revision db-baseline db-check

PYTHON ?= python3
VENV   ?= .venv
BIN    := $(VENV)/bin

help:
	@echo "Atlas"
	@echo ""
	@echo "  make install      Create a virtualenv and install the Python packages"
	@echo "  make install-web  Install the web app's dependencies"
	@echo "  make test         Run the Python test suites"
	@echo "  make test-postgres Schema, RLS and migration tests against PostgreSQL"
	@echo "  make test-web     Run the Vitest unit tests"
	@echo "  make test-e2e     Run the Playwright end-to-end tests"
	@echo "  make api          Run the API on :8000"
	@echo "  make web          Run the web app on :3000"
	@echo "  make seed         Load demo properties"
	@echo ""
	@echo "  Database migrations (Alembic):"
	@echo "  make db-upgrade   Apply every migration this database has not had"
	@echo "  make db-current   Which revision this database is at"
	@echo "  make db-history   The full migration history"
	@echo "  make db-check     Fail if the models have drifted from the migrations"
	@echo "  make db-revision  Autogenerate a revision (m=\"what changed\")"
	@echo "  make db-baseline  Bring a pre-Alembic database under Alembic"
	@echo "  make db-downgrade Step back one revision (to=<rev> for a target)"

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
		../../$(BIN)/pytest -q tests/test_postgres_schema.py tests/test_rls.py \
		tests/test_migrations.py

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

# --- Database migrations ---------------------------------------------------
#
# Alembic is the authoritative runner. It reads ATLAS_DATABASE_URL through
# env.py, so these targets always act on the same database the API uses.
# See docs/migrations.md.

ALEMBIC := $(BIN)/alembic -c apps/api/alembic.ini

db-upgrade:
	$(ALEMBIC) upgrade head

db-current:
	$(ALEMBIC) current --verbose

db-history:
	$(ALEMBIC) history --verbose

# Fails when a model has changed without a matching revision, which is the
# usual way a migration history quietly stops being the truth.
db-check:
	$(ALEMBIC) check

# make db-revision m="add rehab line items"
db-revision:
	@test -n "$(m)" || { echo 'usage: make db-revision m="what changed"'; exit 1; }
	$(ALEMBIC) revision --autogenerate -m "$(m)"

# make db-downgrade            step back one revision
# make db-downgrade to=0001_initial_schema
db-downgrade:
	$(ALEMBIC) downgrade $(or $(to),-1)

# Dry run by default. Add apply=1 to write the stamp.
db-baseline:
	$(BIN)/python scripts/db_baseline.py $(if $(apply),--apply --upgrade,)

lint:
	cd apps/web && npm run lint

clean:
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +
	rm -rf apps/web/.next apps/web/node_modules
