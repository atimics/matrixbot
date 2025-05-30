#!/bin/bash
# Script to rebuild dev container with Docker support

echo "🔄 Rebuilding Dev Container with Docker Support"
echo "==============================================="

echo "📝 Instructions:"
echo "1. This script helps you rebuild your dev container with Docker support"
echo "2. You have two options:"
echo ""
echo "   Option A: Docker-in-Docker (DinD) - Already configured ✅"
echo "   - Runs a Docker daemon inside your dev container"
echo "   - More isolated but uses more resources"
echo ""
echo "   Option B: Docker-outside-of-Docker (DooD)"
echo "   - Shares the host Docker daemon"
echo "   - More efficient but less isolated"
echo ""

read -p "Do you want to use Docker-outside-of-Docker instead of Docker-in-Docker? (y/N): " use_dood

if [[ $use_dood =~ ^[Yy]$ ]]; then
    echo "🔧 Configuring for Docker-outside-of-Docker..."
    
    # Enable DooD mount in devcontainer.json
    sed -i 's|// "source=/var/run/docker.sock|"source=/var/run/docker.sock|' .devcontainer/devcontainer.json
    
    echo "✅ Configured for DooD"
else
    echo "✅ Using Docker-in-Docker (default configuration)"
fi

echo ""
echo "🚀 To rebuild your dev container:"
echo "1. Open VS Code Command Palette (Ctrl+Shift+P / Cmd+Shift+P)"
echo "2. Run: 'Dev Containers: Rebuild Container'"
echo "3. Wait for the rebuild to complete"
echo ""
echo "🐳 After rebuild, you'll have Docker and Docker Compose available!"
echo ""
echo "Test with:"
echo "  docker --version"
echo "  docker-compose --version"
