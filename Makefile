# Run `make help` to see targets. On Windows, use WSL or Git Bash.
SHELL := /bin/bash
PY ?= python

.PHONY: help install db-up db-down migrate data staging setup db-reset test lint eval tags

help:
	@echo "install     install Python deps (dev included)"
	@echo "db-up       start local Postgres in Docker"
	@echo "db-down     stop local Postgres (data volume kept)"
	@echo "migrate     apply versioned migrations (db/migrations)"
	@echo "data        generate the synthetic book into the database (needs ALLOW_RELOAD=1 on a shared one), then rebuild staging"
	@echo "staging     (re)apply staging views (db/staging)"
	@echo "setup       db-up + migrate + data: full local setup"
	@echo "db-reset    drop everything and rebuild from scratch"
	@echo "tags        check the evidence tags against the database (docs/evidence_coverage.md)"
	@echo "test        run tests"
	@echo "eval        score a run: make eval RUN=<run_id> KEY=eval/gap_keys/<file>.csv"

install:
	$(PY) -m pip install -e ".[dev]"

db-up:
	docker compose up -d --wait

db-down:
	docker compose down

migrate:
	$(PY) scripts/migrate.py

data:
	ALLOW_RELOAD=1 $(PY) scripts/gen_book.py
	$(PY) scripts/migrate.py --staging

tags:
	$(PY) -m agent tags

staging:
	$(PY) scripts/migrate.py --staging

setup: db-up migrate data

db-reset:
	$(PY) scripts/migrate.py --reset
	$(MAKE) migrate data

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check .

eval:
	$(PY) -m eval.score --run $(RUN) --gap-key $(KEY)
