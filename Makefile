# =============================================================================
# Biotact Platform v2 - Development Commands
# =============================================================================
# Usage: make <command>
# Run `make help` to see all available commands

.PHONY: help install dev test lint format typecheck clean docker-up docker-down migrate run

# Default target
.DEFAULT_GOAL := help

# Colors for output
CYAN := \033[36m
GREEN := \033[32m
YELLOW := \033[33m
RESET := \033[0m

# =============================================================================
# HELP
# =============================================================================
help: ## Show this help message
	@echo "$(CYAN)Biotact Platform v2 - Available Commands$(RESET)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(RESET) %s\n", $$1, $$2}'
	@echo ""

# =============================================================================
# INSTALLATION
# =============================================================================
install: ## Install production dependencies
	pip install -e .

dev: ## Install development dependencies
	pip install -e ".[dev]"
	pre-commit install

# =============================================================================
# DEVELOPMENT
# =============================================================================
run: ## Run development server
	uvicorn biotact.main:app --reload --host 0.0.0.0 --port 8000

# =============================================================================
# TESTING
# =============================================================================
test: ## Run all tests
	pytest

test-unit: ## Run unit tests only
	pytest -m unit

test-integration: ## Run integration tests only
	pytest -m integration

test-cov: ## Run tests with coverage report
	pytest --cov=src/biotact --cov-report=html --cov-report=term-missing

test-watch: ## Run tests in watch mode (requires pytest-watch)
	ptw -- -v

# =============================================================================
# CODE QUALITY
# =============================================================================
lint: ## Run linter (ruff)
	ruff check src tests

lint-fix: ## Run linter and fix issues
	ruff check src tests --fix

format: ## Format code (ruff)
	ruff format src tests

format-check: ## Check code formatting
	ruff format src tests --check

typecheck: ## Run type checker (mypy)
	mypy src

check: lint format-check typecheck ## Run all checks (lint, format, typecheck)

fix: lint-fix format ## Fix all auto-fixable issues

# =============================================================================
# DATABASE
# =============================================================================
migrate: ## Run database migrations
	alembic upgrade head

migrate-new: ## Create new migration (usage: make migrate-new MSG="description")
	alembic revision --autogenerate -m "$(MSG)"

migrate-down: ## Rollback last migration
	alembic downgrade -1

migrate-history: ## Show migration history
	alembic history

# =============================================================================
# DOCKER
# =============================================================================
docker-up: ## Start Docker services (postgres, qdrant, redis)
	docker compose up -d

docker-down: ## Stop Docker services
	docker compose down

docker-logs: ## View Docker logs
	docker compose logs -f

docker-ps: ## Show Docker service status
	docker compose ps

docker-clean: ## Stop and remove Docker volumes
	docker compose down -v

# =============================================================================
# CLEANUP
# =============================================================================
clean: ## Remove build artifacts and cache
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
