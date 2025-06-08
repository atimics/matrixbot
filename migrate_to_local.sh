#!/bin/bash
# Migration script to help move from Codespaces to local development

set -e

echo "🚀 MatrixBot Local Development Migration Script"
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

echo ""
echo "🎉 Migration setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env file with your configuration: code .env"
echo "2. Open project in VS Code: code ."
echo "3. When prompted, click 'Reopen in Container'"
echo "4. Wait for container to build (this may take 5-10 minutes first time)"
echo "5. Run 'poetry install' if dependencies aren't installed automatically"
echo ""
echo "For detailed instructions, see: LOCAL_DEVELOPMENT.md"
