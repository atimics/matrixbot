# MatrixBot Comprehensive Testing Guide

This document describes the comprehensive testing setup for MatrixBot, including Docker-based testing, local testing, and CI/CD integration.

## Overview

The testing infrastructure provides multiple testing modes:

- **Comprehensive**: Full test suite with coverage, quality checks, and security scans
- **Quick**: Fast unit tests for rapid feedback
- **Matrix**: Categorized test execution (unit, integration, service, database)
- **Health**: Basic health checks and import validation

## Testing Architecture

### Multi-Stage Docker Testing

The `Dockerfile.test` implements a multi-stage build:

1. **Base Stage**: System dependencies and Poetry installation
2. **Dependencies Stage**: Python dependencies installation
3. **Testing Stage**: Source code, test files, and test execution environment

### Test Categories

Tests are organized using pytest markers:

- `unit`: Unit tests
- `integration`: Integration tests
- `service`: Service tests
- `slow`: Slow running tests
- `database`: Tests requiring database
- `network`: Tests requiring network access

## Usage

### Docker-based Testing

#### Run All Tests (Recommended)
```bash
# Comprehensive test suite
docker-compose -f docker-compose.test.yml run --rm test-comprehensive

# Quick tests only
docker-compose -f docker-compose.test.yml run --rm test-quick

# Test matrix (categorized)
docker-compose -f docker-compose.test.yml run --rm test-matrix

# Health checks
docker-compose -f docker-compose.test.yml run --rm test-health
```

#### Extended Testing (with slow/network tests)
```bash
docker-compose -f docker-compose.test.yml --profile extended run --rm test-parallel-with-network
```

#### Service-specific Tests
```bash
# S3 service only
docker-compose -f docker-compose.test.yml run --rm test-s3-service

# Arweave service only
docker-compose -f docker-compose.test.yml run --rm test-arweave-service
```

### Local Testing

#### Using the Test Runner Script
```bash
# Comprehensive tests
./run_tests.sh

# Quick tests
./run_tests.sh -m quick

# With parallel execution
./run_tests.sh -p

# Include slow and network tests
./run_tests.sh -s -n

# Custom coverage threshold
./run_tests.sh -c 80

# Use Docker
./run_tests.sh -d -m comprehensive
```

#### Direct Poetry Commands
```bash
# Install dependencies
poetry install --with dev

# Run all tests with coverage
poetry run pytest tests/ --cov=chatbot --cov-report=html

# Run specific test categories
poetry run pytest tests/ -m "unit"
poetry run pytest tests/ -m "integration"
poetry run pytest tests/ -m "not slow and not network"

# Parallel execution
poetry run pytest tests/ -n auto
```

## Test Reports and Coverage

### Coverage Reports

Coverage reports are generated in multiple formats:
- **Terminal**: Real-time coverage display
- **HTML**: Detailed HTML report in `data/test_results/coverage/html/`
- **XML**: Machine-readable format in `data/test_results/coverage/coverage.xml`
- **JSON**: JSON format in `data/test_results/coverage/coverage.json`

### Test Reports

- **JUnit XML**: Test results in `data/test_results/junit/`
- **Test Duration**: Slowest tests reported
- **Test Summary**: Generated in `data/test_results/reports/test_summary.txt`

## Code Quality and Security

### Code Quality Checks

1. **Ruff Linting**: Modern Python linter and formatter
   ```bash
   poetry run ruff check .
   poetry run ruff format --check .
   ```

2. **Type Checking**: MyPy static type checking
   ```bash
   poetry run mypy chatbot/
   ```

### Security Scanning

1. **Bandit**: Security linting for Python code
   ```bash
   poetry run bandit -r chatbot/
   ```

2. **Safety**: Dependency vulnerability scanning
   ```bash
   poetry run safety check
   ```

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Comprehensive Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        test-mode: [comprehensive, quick, matrix]
    
    steps:
    - uses: actions/checkout@v4
    
    - name: Run Tests
      run: |
        chmod +x ./run_tests.sh
        ./run_tests.sh -d -m ${{ matrix.test-mode }}
    
    - name: Upload Coverage
      uses: codecov/codecov-action@v3
      with:
        file: ./data/test_results/coverage/coverage.xml
```

### GitLab CI Example

```yaml
stages:
  - test
  - security

test:comprehensive:
  stage: test
  script:
    - ./run_tests.sh -d -m comprehensive
  artifacts:
    reports:
      junit: data/test_results/junit/*.xml
      coverage_report:
        coverage_format: cobertura
        path: data/test_results/coverage/coverage.xml

test:security:
  stage: security
  script:
    - docker-compose -f docker-compose.test.yml run --rm test-comprehensive
  artifacts:
    reports:
      sast: data/test_results/security/*.json
```

## Environment Variables

### Test Environment Variables

The testing environment uses placeholder values for sensitive data:

```bash
# Core testing
PYTHONPATH=/app
LOG_LEVEL=DEBUG
CHATBOT_DB_PATH=:memory:
AI_DUMP_PAYLOADS_TO_FILE=false

# Service placeholders (non-sensitive)
NEYNAR_API_KEY=test_key_placeholder
FARCASTER_BOT_FID=123456
MATRIX_ACCESS_TOKEN=test_token_placeholder
GOOGLE_GENAI_API_KEY=test_gemini_placeholder
S3_API_KEY=test_s3_placeholder
```

### Test Control Variables

```bash
# Enable slow tests
RUN_SLOW_TESTS=true

# Enable parallel execution
RUN_PARALLEL_TESTS=true
```

## Customization

### Adding New Test Categories

1. Add marker to `pyproject.toml`:
   ```toml
   markers = [
       "unit: Unit tests",
       "integration: Integration tests",
       "service: Service tests",
       "slow: Slow running tests",
       "database: Tests that require database",
       "network: Tests that require network access",
       "your_category: Your test category description"
   ]
   ```

2. Mark tests with the new category:
   ```python
   import pytest
   
   @pytest.mark.your_category
   def test_your_feature():
       pass
   ```

3. Update test scripts to include the new category.

### Custom Test Configurations

Create custom pytest configuration files:

```ini
# pytest.custom.ini
[pytest]
asyncio_mode = strict
addopts = 
    --strict-markers
    --strict-config
    --verbose
    --tb=long
    --durations=20
    --cov-fail-under=80
testpaths = tests
markers =
    custom: Custom test marker
```

Run with custom config:
```bash
pytest -c pytest.custom.ini
```

## Troubleshooting

### Common Issues

1. **Import Errors**: Ensure `PYTHONPATH` is set correctly
2. **Database Errors**: Use `:memory:` for SQLite in tests
3. **Network Timeouts**: Use mocks for external services
4. **Coverage Issues**: Check that source code is properly included

### Debug Mode

Enable verbose debugging:
```bash
./run_tests.sh -m comprehensive
# or
poetry run pytest tests/ -vvv --tb=long --log-cli-level=DEBUG
```

### Performance Issues

For slow test execution:
```bash
# Profile tests
poetry run pytest tests/ --durations=0

# Run in parallel
./run_tests.sh -p

# Skip slow tests
poetry run pytest tests/ -m "not slow"
```

## Best Practices

1. **Use Markers**: Properly categorize tests with pytest markers
2. **Mock External Services**: Use `pytest-mock` for external dependencies
3. **Async Testing**: Use `pytest-asyncio` for async code testing
4. **Fixture Organization**: Use `conftest.py` for shared fixtures
5. **Test Data**: Use `factory-boy` or `faker` for test data generation
6. **Coverage Goals**: Aim for >70% coverage, critical paths >90%
7. **Fast Feedback**: Use quick tests for rapid development cycles
8. **Comprehensive CI**: Use full test suite in CI/CD pipelines

## File Structure

```
├── Dockerfile.test                 # Multi-stage test Docker image
├── docker-compose.test.yml         # Docker Compose test services
├── run_tests.sh                    # Comprehensive test runner script
├── pytest.ini                     # Pytest configuration
├── pyproject.toml                  # Poetry dependencies and test config
├── tests/                          # Test files
│   ├── conftest.py                # Global test fixtures
│   ├── test_*.py                  # Test modules
│   └── ...
└── data/test_results/             # Test outputs
    ├── coverage/                  # Coverage reports
    ├── junit/                     # JUnit XML reports
    ├── reports/                   # Test summaries
    ├── security/                  # Security scan results
    └── quality/                   # Code quality reports
```

This comprehensive testing setup ensures high-quality, reliable, and maintainable code across the entire MatrixBot project.
