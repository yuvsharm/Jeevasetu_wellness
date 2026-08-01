.PHONY: install backend-install frontend-install lint test check build compose-config up down

PYTHON ?= python
PNPM ?= pnpm

install: backend-install frontend-install

backend-install:
	$(PYTHON) -m pip install -r backend/requirements/development.txt

frontend-install:
	cd frontend && $(PNPM) install --frozen-lockfile

lint:
	cd backend && $(PYTHON) -m ruff format --check . && $(PYTHON) -m ruff check .
	cd frontend && $(PNPM) lint

test:
	cd backend && $(PYTHON) -m pytest
	cd frontend && $(PNPM) test

check:
	cd backend && $(PYTHON) manage.py check --settings=config.settings.test
	cd backend && $(PYTHON) manage.py makemigrations --check --dry-run --settings=config.settings.test
	cd frontend && $(PNPM) typecheck

build:
	cd frontend && $(PNPM) build

compose-config:
	docker compose config

up:
	docker compose up --build

down:
	docker compose down

