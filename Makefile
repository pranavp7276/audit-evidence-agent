# Run `make help` to see targets. On Windows, use WSL or Git Bash.
SHELL := /bin/bash
PY ?= python

.PHONY: help install db-up db-down migrate load staging setup db-reset data-check test lint eval

help:
	@echo "install     install Python deps (dev included)"
	@echo "db-up       start local Postgres in Docker"
	@echo "db-down     stop local Postgres (data volume kept)"
	@echo "migrate     apply versioned migrations (db/migrations)"
	@echo "load        load raw files per data/manifest.yaml, then rebuild staging"
	@echo "staging     (re)apply staging views (db/staging)"
	@echo "setup       db-up + migrate + load: full local setup"
	@echo "db-reset    drop everything and rebuild from scratch"
	@echo "data-check  verify your data files match data/CHECKSUMS.sha256"
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

load:
	$(PY) scripts/load_data.py
	$(PY) scripts/migrate.py --staging

staging:
	$(PY) scripts/migrate.py --staging

setup: db-up migrate load

db-reset:
	$(PY) scripts/migrate.py --reset
	$(MAKE) migrate load

data-check:
	cd data && sha256sum -c CHECKSUMS.sha256

test:
	$(PY) -m pytest -q

lint:
	$(PY) -m ruff check .

eval:
	$(PY) -m eval.score --run $(RUN) --gap-key $(KEY)
