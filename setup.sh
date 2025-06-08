#!/bin/bash
# Migration script to help move from Codespaces to local development

set -e

echo "🚀 RatiChat Local Development Migration Script"
echo "=============================================="

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Check prerequisites
echo "📋 Checking prerequisites..."

if ! command_exists docker; then
    echo "❌ Docker not found. Please install Docker Desktop first:"
    echo "   https://www.docker.com/products/docker-desktop/"
    exit 1
fi

if ! command_exists code; then
    echo "❌ VS Code not found. Please install Visual Studio Code:"
    echo "   https://code.visualstudio.com/"
    exit 1
fi

echo "✅ Docker found: $(docker --version)"
echo "✅ VS Code found: $(code --version | head -1)"

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker Desktop."
    exit 1
fi

echo "✅ Docker is running"

# Check for Dev Containers extension
if ! code --list-extensions | grep -q "ms-vscode-remote.remote-containers"; then
    echo "📦 Installing Dev Containers extension..."
    code --install-extension ms-vscode-remote.remote-containers
else
    echo "✅ Dev Containers extension already installed"
fi

# Setup environment file if it doesn't exist
if [ ! -f .env ]; then
    if [ -f .env.example ]; then
        echo "📝 Creating .env from .env.example..."
        cp .env.example .env
        echo "⚠️  Please edit .env with your actual values before proceeding"
        echo "   You can do this with: code .env"
    else
        echo "⚠️  No .env.example found. You may need to create .env manually."
    fi
else
    echo "✅ .env file already exists"
fi

# Create necessary directories
echo "📁 Creating necessary directories..."
mkdir -p data matrix_store context_storage

# Set permissions for data directories
echo "🔐 Setting up permissions..."
if [ "$(uname)" = "Linux" ]; then
    # On Linux, ensure the directories are writable
    chmod -R 755 data matrix_store context_storage
fi

# Check available disk space
echo "💾 Checking disk space..."
available_space=$(df . | tail -1 | awk '{print $4}')
if [ "$available_space" -lt 4194304 ]; then # 4GB in KB
    echo "⚠️  Warning: Less than 4GB of disk space available."
    echo "   Dev containers and Docker images may require significant space."
fi

# Install Node.js LTS if not present
echo "📦 Setting up Node.js LTS..."
if ! command_exists node; then
    echo "Installing Node.js LTS..."
    if [ "$(uname)" = "Linux" ]; then
        curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
        sudo apt-get install -y nodejs
    else
        echo "⚠️  Please install Node.js LTS manually from https://nodejs.org/"
        echo "   Or use a package manager like Homebrew on macOS"
    fi
else
    node_version=$(node --version)
    echo "✅ Node.js found: $node_version"
fi

if ! command_exists npm; then
    echo "❌ npm not found. This should have been installed with Node.js."
    exit 1
else
    npm_version=$(npm --version)
    echo "✅ npm found: $npm_version"
fi

# Install frontend dependencies
if [ -d "ui-nextjs" ]; then
    echo "📦 Installing frontend dependencies..."
    cd ui-nextjs
    npm install
    cd ..
    echo "✅ Frontend dependencies installed"
else
    echo "⚠️  ui-nextjs directory not found, skipping frontend setup"
fi

# Check and install Poetry if needed
echo "📦 Setting up Poetry..."
if ! command_exists poetry; then
    echo "Installing Poetry..."
    curl -sSL https://install.python-poetry.org | python3 -
    export PATH="$HOME/.local/bin:$PATH"
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    echo "✅ Poetry installed"
else
    poetry_version=$(poetry --version)
    echo "✅ Poetry found: $poetry_version"
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
if command_exists poetry; then
    echo "Using Poetry to install dependencies..."
    poetry install --with dev
    echo "✅ Python dependencies (including dev/test) installed with Poetry"
elif [ -f "requirements.txt" ]; then
    echo "Using pip to install dependencies..."
    pip install -r requirements.txt
    # Install test dependencies separately if requirements.txt doesn't include them
    echo "Installing additional test dependencies..."
    pip install pytest pytest-asyncio
    echo "✅ Python dependencies installed with pip"
else
    echo "⚠️  No pyproject.toml or requirements.txt found"
    echo "Installing minimal test dependencies..."
    pip install pytest pytest-asyncio
fi

# Run a quick test to verify the setup
echo "🧪 Running test environment verification..."
if command_exists poetry; then
    if poetry run python -c "import pytest, pytest_asyncio; print('✅ Test dependencies available')"; then
        echo "✅ Test environment verified"
        # Run a subset of tests to verify functionality
        echo "Running a quick test suite to verify functionality..."
        if poetry run python -m pytest tests/ -v --tb=short -x --maxfail=3 -q; then
            echo "✅ All tests passed! Your development environment is ready."
        else
            echo "⚠️  Some tests failed. This may be expected if environment variables aren't fully configured."
            echo "   You can run tests later with: poetry run pytest tests/"
        fi
    else
        echo "⚠️  Test dependencies verification failed"
    fi
else
    if python -c "import pytest, pytest_asyncio; print('✅ Test dependencies available')" 2>/dev/null; then
        echo "✅ Test environment verified"
        echo "Running a quick test suite to verify functionality..."
        if python -m pytest tests/ -v --tb=short -x --maxfail=3 -q; then
            echo "✅ All tests passed! Your development environment is ready."
        else
            echo "⚠️  Some tests failed. This may be expected if environment variables aren't fully configured."
            echo "   You can run tests later with: python -m pytest tests/"
        fi
    else
        echo "⚠️  Test dependencies verification failed"
        echo "   Please install pytest and pytest-asyncio manually"
    fi
fi

# Build Docker containers
echo "🐳 Building Docker containers..."
if [ -f "docker-compose.yml" ]; then
    docker-compose build
    echo "✅ Docker containers built successfully"
else
    echo "⚠️  docker-compose.yml not found, skipping Docker build"
fi

# Launch the control panel and services
echo "🚀 Starting services..."
if [ -f "docker-compose.yml" ]; then
    echo "Starting all services with docker-compose..."
    docker-compose up -d
    
    # Wait a moment for services to start
    echo "⏳ Waiting for services to start..."
    sleep 10
    
    # Check if services are running
    echo "📊 Service status:"
    docker-compose ps
    
    echo ""
    echo "🌐 Opening control panel..."
    echo "Control panel should be available at: http://localhost:3000"
    echo "API server should be available at: http://localhost:8000"
    echo "Arweave service should be available at: http://localhost:8001"
    
    # Try to open the control panel in browser
    if command_exists "$BROWSER"; then
        "$BROWSER" "http://localhost:3000" &
    elif [ -n "$BROWSER" ]; then
        $BROWSER "http://localhost:3000" &
    else
        echo "💡 Open http://localhost:3000 in your browser to access the control panel"
    fi
    
else
    echo "⚠️  docker-compose.yml not found, trying to run control panel directly..."
    if [ -f "control_panel.py" ]; then
        echo "Starting Python control panel..."
        python control_panel.py &
        control_panel_pid=$!
        echo "Control panel started with PID: $control_panel_pid"
        echo "💡 Control panel should be running on default port"
    fi
fi

echo ""
echo "🎉 Setup complete and services launched!"
echo ""
echo "📊 Setup Summary:"
echo "=================="
if command_exists node; then
    echo "✅ Node.js: $(node --version)"
fi
if command_exists npm; then
    echo "✅ npm: $(npm --version)"
fi
if command_exists poetry; then
    echo "✅ Poetry: $(poetry --version)"
fi
if command_exists docker; then
    echo "✅ Docker: $(docker --version)"
fi
echo ""
echo "🌐 Service URLs:"
echo "=================="
echo "• Control Panel: http://localhost:3000"
echo "• API Server: http://localhost:8000"
echo "• Arweave Service: http://localhost:8001"
echo ""
echo "🛠️  Next steps:"
echo "=================="
echo "1. Edit .env file if needed: code .env"
echo "2. Access the control panel at: http://localhost:3000"
echo "3. Check API health at: http://localhost:8000/health"
echo "4. Run tests with: poetry run pytest tests/"
echo "5. Monitor logs with: docker-compose logs -f"
echo "6. Stop services with: docker-compose down"
echo ""
echo "📚 Documentation:"
echo "=================="
echo "• Development Guide: LOCAL_DEVELOPMENT.md"
echo "• API Documentation: API.md"
echo "• Architecture Overview: ARCHITECTURE.md"
echo ""
echo "🎯 Your RatiChat development environment is ready!"
