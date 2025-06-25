#!/bin/bash
"""
PostgreSQL Migration Helper Script

This script automates the complete PostgreSQL migration process,
including dependency installation, database setup, migration execution,
and validation.

Usage:
    ./migrate_to_postgresql.sh [--dry-run] [--skip-tests]
"""

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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

# Parse command line arguments
DRY_RUN=false
SKIP_TESTS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        --help)
            echo "Usage: $0 [--dry-run] [--skip-tests]"
            echo "  --dry-run     Perform migration validation without actual changes"
            echo "  --skip-tests  Skip the comprehensive test suite"
            exit 0
            ;;
        *)
            print_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

print_status "Starting PostgreSQL Migration Process..."

# Step 1: Check prerequisites
print_status "Checking prerequisites..."

if ! command -v poetry &> /dev/null; then
    print_error "Poetry is required but not installed. Please install Poetry first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! command -v docker &> /dev/null; then
    print_warning "Docker is recommended for running PostgreSQL locally."
fi

# Step 2: Install dependencies
print_status "Installing Python dependencies..."
poetry lock
poetry install

if [ $? -eq 0 ]; then
    print_success "Dependencies installed successfully"
else
    print_error "Failed to install dependencies"
    exit 1
fi

# Step 3: Check environment configuration
print_status "Checking environment configuration..."

if [ ! -f ".env" ]; then
    print_warning ".env file not found. Creating template..."
    cat > .env << EOF
# PostgreSQL Configuration
POSTGRES_USER=ratichat
POSTGRES_PASSWORD=your_strong_password_here
POSTGRES_HOST=localhost
POSTGRES_DB=ratichat
POSTGRES_PORT=5432
POSTGRES_MIN_POOL_SIZE=1
POSTGRES_MAX_POOL_SIZE=10
EOF
    print_warning "Please update .env file with your PostgreSQL credentials"
fi

# Step 4: Start PostgreSQL (if using Docker)
if command -v docker-compose &> /dev/null; then
    print_status "Starting PostgreSQL with Docker Compose..."
    docker-compose up postgres -d
    
    # Wait for PostgreSQL to be ready
    print_status "Waiting for PostgreSQL to be ready..."
    timeout=60
    while ! docker-compose exec postgres pg_isready -U ratichat -d ratichat &> /dev/null; do
        sleep 2
        timeout=$((timeout - 2))
        if [ $timeout -le 0 ]; then
            print_error "PostgreSQL failed to start within 60 seconds"
            exit 1
        fi
    done
    print_success "PostgreSQL is ready"
fi

# Step 5: Run migration
print_status "Running database migration..."

if [ "$DRY_RUN" = true ]; then
    print_status "Running migration in dry-run mode..."
    poetry run python scripts/migrate_sqlite_to_pg.py --dry-run
else
    print_status "Running actual migration..."
    mkdir -p backups
    poetry run python scripts/migrate_sqlite_to_pg.py --backup-dir ./backups
fi

if [ $? -eq 0 ]; then
    print_success "Migration completed successfully"
else
    print_error "Migration failed"
    exit 1
fi

# Step 6: Run tests (unless skipped)
if [ "$SKIP_TESTS" = false ] && [ "$DRY_RUN" = false ]; then
    print_status "Running comprehensive test suite..."
    poetry run python test_postgresql_migration.py
    
    if [ $? -eq 0 ]; then
        print_success "All tests passed"
    else
        print_error "Some tests failed. Please review the output above."
        exit 1
    fi
else
    print_warning "Skipping test suite"
fi

# Step 7: Setup Alembic (for future migrations)
if [ "$DRY_RUN" = false ]; then
    print_status "Setting up Alembic for future schema migrations..."
    if [ ! -d "alembic" ]; then
        poetry run python scripts/setup_alembic.py
        print_success "Alembic setup completed"
    else
        print_warning "Alembic already configured"
    fi
fi

# Final summary
print_success "PostgreSQL migration process completed!"

if [ "$DRY_RUN" = false ]; then
    echo
    print_status "Next steps:"
    echo "1. Update your application configuration to use PostgreSQL"
    echo "2. Restart your application services"
    echo "3. Monitor performance and connection pooling"
    echo "4. Consider setting up automated backups"
    echo
    print_status "For production deployment, see POSTGRESQL_MIGRATION.md"
else
    echo
    print_status "Dry run completed. To execute the actual migration:"
    echo "  $0 (without --dry-run)"
fi
