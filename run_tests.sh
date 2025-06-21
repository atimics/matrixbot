#!/bin/bash
# Comprehensive test runner script for MatrixBot
# Can be run locally or in CI/CD environments

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values
TEST_MODE="comprehensive"
USE_DOCKER="false"
PARALLEL="false"
SLOW_TESTS="false"
NETWORK_TESTS="false"
COVERAGE_THRESHOLD="70"
OUTPUT_DIR="./data/test_results"

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Options:
  -m, --mode MODE        Test mode: comprehensive, quick, matrix, health (default: comprehensive)
  -d, --docker           Run tests in Docker containers
  -p, --parallel         Enable parallel test execution
  -s, --slow             Include slow-running tests
  -n, --network          Include network-dependent tests
  -c, --coverage NUM     Set coverage threshold (default: 70)
  -o, --output DIR       Output directory for test results (default: ./data/test_results)
  -h, --help             Show this help message

Examples:
  $0                                    # Run comprehensive tests locally
  $0 -m quick                          # Run quick tests only
  $0 -d -m comprehensive               # Run comprehensive tests in Docker
  $0 -p -s -n                         # Run all tests with parallel execution
  $0 -m matrix -o /tmp/test_results   # Run test matrix with custom output dir

Test Modes:
  comprehensive  - Full test suite with coverage, quality checks, and security scans
  quick         - Fast unit tests only, no coverage or quality checks
  matrix        - Categorized test execution (unit, integration, service, database)
  health        - Basic health checks and import validation
EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -m|--mode)
            TEST_MODE="$2"
            shift 2
            ;;
        -d|--docker)
            USE_DOCKER="true"
            shift
            ;;
        -p|--parallel)
            PARALLEL="true"
            shift
            ;;
        -s|--slow)
            SLOW_TESTS="true"
            shift
            ;;
        -n|--network)
            NETWORK_TESTS="true"
            shift
            ;;
        -c|--coverage)
            COVERAGE_THRESHOLD="$2"
            shift 2
            ;;
        -o|--output)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Validate test mode
case $TEST_MODE in
    comprehensive|quick|matrix|health)
        ;;
    *)
        print_error "Invalid test mode: $TEST_MODE"
        show_usage
        exit 1
        ;;
esac

print_status "Starting MatrixBot Test Suite"
print_status "Mode: $TEST_MODE"
print_status "Docker: $USE_DOCKER"
print_status "Parallel: $PARALLEL"
print_status "Slow tests: $SLOW_TESTS"
print_status "Network tests: $NETWORK_TESTS"
print_status "Coverage threshold: $COVERAGE_THRESHOLD%"
print_status "Output directory: $OUTPUT_DIR"

# Create output directory
mkdir -p "$OUTPUT_DIR"/{coverage,junit,reports,security,quality}

if [[ "$USE_DOCKER" == "true" ]]; then
    print_status "Running tests in Docker containers..."
    
    case $TEST_MODE in
        comprehensive)
            if [[ "$PARALLEL" == "true" || "$SLOW_TESTS" == "true" ]]; then
                docker-compose -f docker-compose.test.yml --profile extended run --rm test-parallel-with-network
            else
                docker-compose -f docker-compose.test.yml run --rm test-comprehensive
            fi
            ;;
        quick)
            docker-compose -f docker-compose.test.yml run --rm test-quick
            ;;
        matrix)
            docker-compose -f docker-compose.test.yml run --rm test-matrix
            ;;
        health)
            docker-compose -f docker-compose.test.yml run --rm test-health
            ;;
    esac
else
    print_status "Running tests locally..."
    
    # Check if poetry is available
    if ! command -v poetry &> /dev/null; then
        print_error "Poetry not found. Please install Poetry or use Docker mode (-d)"
        exit 1
    fi
    
    # Set environment variables for local testing
    export PYTHONPATH="$(pwd)"
    export LOG_LEVEL="DEBUG"
    export CHATBOT_DB_PATH=":memory:"
    export AI_DUMP_PAYLOADS_TO_FILE="false"
    
    case $TEST_MODE in
        comprehensive)
            print_status "Running comprehensive test suite..."
            
            # Code quality checks
            print_status "Running code quality checks..."
            poetry run ruff check . --output-format=json > "$OUTPUT_DIR/quality/ruff_report.json" || true
            poetry run ruff check . || print_warning "Ruff found issues"
            
            # Type checking
            print_status "Running type checking..."
            poetry run mypy chatbot/ --json-report "$OUTPUT_DIR/quality/mypy_report" || print_warning "Type checking found issues"
            
            # Security scanning
            print_status "Running security scans..."
            poetry run bandit -r chatbot/ -f json -o "$OUTPUT_DIR/security/bandit_report.json" || print_warning "Security issues found"
            poetry run safety check --json --output "$OUTPUT_DIR/security/safety_report.json" || print_warning "Dependency vulnerabilities found"
            
            # Build test command
            TEST_CMD="poetry run pytest tests/ -v --tb=short --durations=20"
            TEST_CMD="$TEST_CMD --cov=chatbot --cov-report=term-missing"
            TEST_CMD="$TEST_CMD --cov-report=html:$OUTPUT_DIR/coverage/html"
            TEST_CMD="$TEST_CMD --cov-report=xml:$OUTPUT_DIR/coverage/coverage.xml"
            TEST_CMD="$TEST_CMD --junit-xml=$OUTPUT_DIR/junit/tests.xml"
            TEST_CMD="$TEST_CMD --cov-fail-under=$COVERAGE_THRESHOLD"
            
            # Add test markers based on options
            MARKERS="not slow and not network"
            if [[ "$SLOW_TESTS" == "true" ]]; then
                MARKERS=""
            elif [[ "$NETWORK_TESTS" == "true" ]]; then
                MARKERS="not slow"
            fi
            
            if [[ -n "$MARKERS" ]]; then
                TEST_CMD="$TEST_CMD -m \"$MARKERS\""
            fi
            
            if [[ "$PARALLEL" == "true" ]]; then
                TEST_CMD="$TEST_CMD -n auto --dist=worksteal"
            fi
            
            print_status "Running tests: $TEST_CMD"
            eval $TEST_CMD
            ;;
            
        quick)
            print_status "Running quick tests..."
            poetry run pytest tests/ -v --tb=short -x -m "not slow and not network" --disable-warnings
            ;;
            
        matrix)
            print_status "Running test matrix..."
            
            poetry run pytest tests/ -v --tb=short -m "not slow and not network and not database" \
                --junit-xml="$OUTPUT_DIR/junit/unit_tests.xml" || print_warning "Unit tests had issues"
                
            poetry run pytest tests/ -v --tb=short -m "integration" \
                --junit-xml="$OUTPUT_DIR/junit/integration_tests.xml" || print_warning "Integration tests had issues"
                
            poetry run pytest tests/ -v --tb=short -m "service" \
                --junit-xml="$OUTPUT_DIR/junit/service_tests.xml" || print_warning "Service tests had issues"
                
            poetry run pytest tests/ -v --tb=short -m "database" \
                --junit-xml="$OUTPUT_DIR/junit/database_tests.xml" || print_warning "Database tests had issues"
            ;;
            
        health)
            print_status "Running health checks..."
            
            python -c "
try:
    import chatbot
    import chatbot.config
    import chatbot.core
    print('✅ Core imports successful')
except ImportError as e:
    print(f'❌ Import error: {e}')
    exit(1)
"

            python -c "
from chatbot.config import AppConfig
try:
    config = AppConfig()
    print('✅ Configuration loads successfully')
except Exception as e:
    print(f'❌ Configuration error: {e}')
    exit(1)
"
            ;;
    esac
fi

print_success "Test execution completed!"
print_status "Results saved to: $OUTPUT_DIR"

# Generate summary report
cat > "$OUTPUT_DIR/reports/test_summary.txt" << EOF
=== MatrixBot Test Suite Results ===
Execution completed at: $(date)
Mode: $TEST_MODE
Docker: $USE_DOCKER
Parallel: $PARALLEL
Slow tests: $SLOW_TESTS
Network tests: $NETWORK_TESTS
Coverage threshold: $COVERAGE_THRESHOLD%

Reports Generated:
- Coverage: $OUTPUT_DIR/coverage/
- JUnit XML: $OUTPUT_DIR/junit/
- Security: $OUTPUT_DIR/security/
- Quality: $OUTPUT_DIR/quality/
EOF

print_success "Test summary saved to: $OUTPUT_DIR/reports/test_summary.txt"
