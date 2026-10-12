# AdIntel — developer commands. Run `make help` to see them all.
SHELL := /bin/bash
PY    ?= .venv/bin/python
UV    ?= uv

.PHONY: help venv install lint format typecheck test test-cov security evals gate \
        seed run-api run-worker run-executor run-scheduler up down mlx-small mlx-frontier \
        frontend-install frontend-build load-test verify-audit reconcile clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

venv: ## Create the Python 3.12 virtual environment
	$(UV) venv -p 3.12 .venv

install: ## Install AdIntel with dev + ml extras
	$(UV) pip install -e ".[dev,ml]"

lint: ## Lint (ruff)
	$(PY) -m ruff check src tests evals scripts finetune

format: ## Auto-format (ruff)
	$(PY) -m ruff format src tests evals scripts finetune
	$(PY) -m ruff check --fix src tests evals scripts finetune

typecheck: ## Static types (mypy --strict)
	$(PY) -m mypy src

test: ## Unit + offline integration tests (no external services needed)
	$(PY) -m pytest -m "not integration and not mlx"

test-cov: ## Tests with the 85% coverage gate on non-LLM code
	$(PY) -m pytest -m "not integration and not mlx" --cov --cov-report=term-missing --cov-fail-under=85

security: ## Static security scan (bandit)
	$(PY) -m bandit -q -r src -c pyproject.toml || $(PY) -m bandit -q -r src

evals: ## Run every agent eval against the mock provider (CI mode)
	$(PY) -m adintel.evals.runner --provider mock --out evals/reports

evals-mlx: ## Run every agent eval against your local mlx-lm models
	$(PY) -m adintel.evals.runner --provider mlx --out evals/reports

gate: ## Promotion gate: fail if any hard threshold or category regresses
	$(PY) -m adintel.evals.gate --report evals/reports/latest.json --baseline evals/baseline.json

seed: ## Load synthetic tenants, brands, users, brand rules and the knowledge base
	$(PY) -m adintel.cli seed

run-api: ## Start the API service (FastAPI) on :8000
	$(PY) -m uvicorn adintel.api.app:create_app --factory --host 127.0.0.1 --port 8000 --reload

run-worker: ## Start the agent worker (runs LangGraph jobs from the agent-runs queue)
	$(PY) -m adintel.workers.agent_worker

run-executor: ## Start the executor service (no LLM access; only service with write credentials)
	$(PY) -m adintel.executor

run-scheduler: ## Start the nightly scheduler (EventBridge replacement)
	$(PY) -m adintel.scheduler

mlx-small: ## Serve the small/volume model (Qwen3.6-35B-A3B-4bit) on :8080
	./scripts/mlx/serve_small.sh

mlx-frontier: ## Serve the frontier/judgement model (Qwen3.8-27B-8bit) on :8081
	./scripts/mlx/serve_frontier.sh

up: ## Start local infrastructure (MongoDB Atlas Local, Redis, Langfuse, Prometheus, Grafana, Jaeger)
	docker compose -f deploy/docker-compose.yml up -d

down: ## Stop local infrastructure
	docker compose -f deploy/docker-compose.yml down

frontend-install: ## Install Angular dependencies
	cd frontend && npm ci

frontend-build: ## Production build of the Angular app
	cd frontend && npm run build

load-test: ## k6 Monday-morning load profile against a running stack
	k6 run tests/load/monday_peak.js

verify-audit: ## Verify the audit log hash chain
	$(PY) -m adintel.cli verify-audit

reconcile: ## Compare every executed change with what was approved
	$(PY) -m adintel.cli reconcile

clean: ## Remove caches and local artifacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage var/
