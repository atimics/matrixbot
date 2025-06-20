#!/bin/bash
# RatiChat Setup Script - Improved Version
# This script automates the initial setup and configuration of the RatiChat system

set -e  # Exit on any error

echo "🚀 RatiChat Setup Script v2.0"
echo "=============================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
if [[ $EUID -eq 0 ]]; then
   log_error "This script should not be run as root for security reasons"
   exit 1
fi

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to detect OS
detect_os() {
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        echo "linux"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
        echo "windows"
    else
        echo "unknown"
    fi
}

OS=$(detect_os)
log_info "Detected OS: $OS"

# Check prerequisites
log_info "Checking prerequisites..."

# Check Python
if ! command_exists python3; then
    log_error "Python 3 is required but not installed. Please install Python 3.10 or later."
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
log_success "Python $PYTHON_VERSION found"

# Check if Python version is >= 3.10
if python3 -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)"; then
    log_success "Python version is compatible"
else
    log_error "Python 3.10 or later is required. Current version: $PYTHON_VERSION"
    exit 1
fi

# Check Poetry
if ! command_exists poetry; then
    log_warning "Poetry not found. Installing Poetry..."
    if [[ "$OS" == "windows" ]]; then
        log_error "Please install Poetry manually on Windows: https://python-poetry.org/docs/#installation"
        exit 1
    else
        curl -sSL https://install.python-poetry.org | python3 -
        export PATH="$HOME/.local/bin:$PATH"
        if ! command_exists poetry; then
            log_error "Poetry installation failed. Please install manually."
            exit 1
        fi
    fi
fi

log_success "Poetry found"

# Check Docker (optional)
if command_exists docker; then
    log_success "Docker found"
    if command_exists docker-compose; then
        log_success "Docker Compose found"
        DOCKER_AVAILABLE=true
    else
        log_warning "Docker Compose not found. Some features may be limited."
        DOCKER_AVAILABLE=false
    fi
else
    log_warning "Docker not found. Some features may be limited."
    DOCKER_AVAILABLE=false
fi

# Install Python dependencies
log_info "Installing Python dependencies with Poetry..."
poetry install

# Generate .env file if it doesn't exist
if [[ ! -f .env ]]; then
    log_info "Creating .env file from template..."
    cp .env.example .env
    log_warning "Please edit .env file with your actual API keys and configuration"
    log_info "Required configuration:"
    echo "  - OPENROUTER_API_KEY: Your OpenRouter API key"
    echo "  - MATRIX_HOMESERVER: Your Matrix homeserver URL"
    echo "  - MATRIX_USER_ID: Your Matrix bot user ID"
    echo "  - MATRIX_PASSWORD: Your Matrix bot password"
    echo "  - NEYNAR_API_KEY: Your Neynar API key (for Farcaster integration)"
else
    log_success ".env file already exists"
fi

# Create data directories
log_info "Creating data directories..."
mkdir -p data/context_storage
mkdir -p data/payload_dumps
mkdir -p data/reports
mkdir -p matrix_store
log_success "Data directories created"

# Set appropriate permissions
chmod 700 data/
chmod 600 .env 2>/dev/null || log_warning "Could not set .env permissions"

# Initialize database if needed
log_info "Setting up database..."
if [[ -f "chatbot/storage/database.py" ]]; then
    poetry run python -c "
import asyncio
import sys
import os
sys.path.append(os.getcwd())
from chatbot.storage.database import init_database
asyncio.run(init_database())
print('Database initialized successfully')
" 2>/dev/null || log_warning "Database initialization skipped (may not be needed)"
fi

# Run basic configuration validation
log_info "Validating configuration..."
poetry run python -c "
import os
from dotenv import load_dotenv
load_dotenv()

required_vars = ['OPENROUTER_API_KEY', 'MATRIX_HOMESERVER', 'MATRIX_USER_ID']
missing_vars = [var for var in required_vars if not os.getenv(var)]

if missing_vars:
    print(f'Missing required environment variables: {', '.join(missing_vars)}')
    exit(1)
else:
    print('Basic configuration validation passed')
" 2>/dev/null && log_success "Configuration validation passed" || log_warning "Please configure required environment variables in .env"

# Test basic functionality
log_info "Testing basic functionality..."
poetry run python -c "
import sys
import os
sys.path.append(os.getcwd())
try:
    from chatbot.config import settings
    print('Configuration loading: OK')
    
    from chatbot.core.ai_engine import create_ai_engine
    print('AI engine import: OK')
    
    print('Basic functionality test passed')
except Exception as e:
    print(f'Basic functionality test failed: {e}')
    exit(1)
" && log_success "Basic functionality test passed" || log_error "Basic functionality test failed"

# Setup development tools
log_info "Setting up development tools..."
if [[ -f ".pre-commit-config.yaml" ]]; then
    poetry run pre-commit install 2>/dev/null && log_success "Pre-commit hooks installed" || log_warning "Pre-commit hook installation failed"
fi

# Print setup summary
echo ""
log_success "Setup completed successfully!"
echo ""
echo "📋 Next Steps:"
echo "1. Edit .env file with your API keys and configuration"
echo "2. Test the configuration:"
echo "   poetry run python -m chatbot.main --test"
echo ""
if [[ "$DOCKER_AVAILABLE" == "true" ]]; then
    echo "🐳 Docker Usage:"
    echo "   docker-compose up -d"
    echo ""
fi
echo "📚 Documentation:"
echo "   - Development guide: DEVELOPMENT.md"
echo "   - API documentation: API.md"
echo "   - Architecture overview: ARCHITECTURE.md"
echo ""
echo "🚀 Start the chatbot:"
echo "   poetry run python run.py"
echo ""

log_info "Happy coding! 🎉"
