# MatrixBot Testing Makefile
# Provides easy-to-use targets for running tests

.PHONY: help test test-quick test-comprehensive test-matrix test-health test-docker clean lint security

# Default target
help: ## Show this help message
	@echo "MatrixBot Testing Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Examples:"
	@echo "  make test                 # Run comprehensive tests locally"
	@echo "  make test-docker          # Run comprehensive tests in Docker"
	@echo "  make test-quick           # Run quick tests only"
	@echo "  make test-parallel        # Run tests in parallel"

# Local testing targets
test: ## Run comprehensive tests locally
	./run_tests.sh -m comprehensive

test-quick: ## Run quick tests only
	./run_tests.sh -m quick

test-matrix: ## Run categorized test matrix
	./run_tests.sh -m matrix

test-health: ## Run health checks
	./run_tests.sh -m health

test-parallel: ## Run tests with parallel execution
	./run_tests.sh -p -m comprehensive

test-slow: ## Run all tests including slow ones
	./run_tests.sh -s -n -m comprehensive

# Docker testing targets
test-docker: ## Run comprehensive tests in Docker
	./run_tests.sh -d -m comprehensive

test-docker-quick: ## Run quick tests in Docker
	./run_tests.sh -d -m quick

test-docker-matrix: ## Run test matrix in Docker
	./run_tests.sh -d -m matrix

test-docker-health: ## Run health checks in Docker
	./run_tests.sh -d -m health

test-docker-extended: ## Run extended tests with slow/network tests
	docker-compose -f docker-compose.test.yml --profile extended run --rm test-parallel-with-network

# Service-specific testing
test-s3: ## Test S3 service only
	docker-compose -f docker-compose.test.yml run --rm test-s3-service

test-arweave: ## Test Arweave service only
	docker-compose -f docker-compose.test.yml run --rm test-arweave-service

# Code quality and security
lint: ## Run linting and formatting checks
	poetry run ruff check .
	poetry run ruff format --check .

lint-fix: ## Fix linting and formatting issues
	poetry run ruff check . --fix
	poetry run ruff format .

typecheck: ## Run type checking
	poetry run mypy chatbot/

security: ## Run security scans
	poetry run bandit -r chatbot/
	poetry run safety check

quality: lint typecheck security ## Run all code quality checks

# Coverage targets
coverage: ## Generate coverage report
	poetry run pytest tests/ --cov=chatbot --cov-report=html --cov-report=term-missing

coverage-xml: ## Generate XML coverage report
	poetry run pytest tests/ --cov=chatbot --cov-report=xml

# Cleanup
clean: ## Clean test artifacts and cache
	rm -rf data/test_results/*
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf htmlcov/
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete

clean-docker: ## Clean Docker test containers and images
	docker-compose -f docker-compose.test.yml down --rmi all --volumes --remove-orphans

# Development targets
install: ## Install dependencies
	poetry install --with dev

install-pre-commit: ## Install pre-commit hooks
	poetry run pre-commit install

dev-setup: install install-pre-commit ## Setup development environment

# CI/CD simulation
ci-test: ## Simulate CI testing pipeline
	make clean
	make quality
	make test-docker
	make coverage-xml

# Performance testing
perf-test: ## Run performance-focused tests
	poetry run pytest tests/ -m "not slow" --durations=20 -v

# Test with different Python versions (requires Docker)
test-py310: ## Test with Python 3.10 (requires Docker)
	docker run --rm -v $(PWD):/app -w /app python:3.10-slim bash -c "pip install poetry && poetry install --with dev && poetry run pytest tests/"

test-py311: ## Test with Python 3.11 (requires Docker)
	docker run --rm -v $(PWD):/app -w /app python:3.11-slim bash -c "pip install poetry && poetry install --with dev && poetry run pytest tests/"

test-py312: ## Test with Python 3.12 (requires Docker)
	docker run --rm -v $(PWD):/app -w /app python:3.12-slim bash -c "pip install poetry && poetry install --with dev && poetry run pytest tests/"

# Reporting
report: ## Generate comprehensive test report
	@echo "Generating comprehensive test report..."
	@./run_tests.sh -m comprehensive -c 70
	@echo ""
	@echo "Test Results Summary:"
	@echo "====================="
	@if [ -f data/test_results/reports/test_summary.txt ]; then cat data/test_results/reports/test_summary.txt; fi
	@echo ""
	@echo "Coverage Report:"
	@echo "==============="
	@if [ -f data/test_results/coverage/coverage.json ]; then python -c "import json; data=json.load(open('data/test_results/coverage/coverage.json')); print(f\"Total Coverage: {data['totals']['percent_covered']:.1f}%\")"; fi

# Watch mode for development
watch: ## Run tests in watch mode (requires entr)
	find tests/ chatbot/ -name "*.py" | entr -c make test-quick
