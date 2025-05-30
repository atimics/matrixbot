#!/bin/bash
# Validate Docker setup and test chatbot deployment

echo "🐳 Docker Environment Validation"
echo "================================"

# Check Docker installation
echo "🔍 Checking Docker installation..."
if command -v docker &> /dev/null; then
    echo "✅ Docker is installed: $(docker --version)"
else
    echo "❌ Docker is not available"
    exit 1
fi

# Check Docker Compose
echo "🔍 Checking Docker Compose..."
if command -v docker-compose &> /dev/null || docker compose version &> /dev/null; then
    echo "✅ Docker Compose is available"
    if command -v docker-compose &> /dev/null; then
        echo "   Version: $(docker-compose --version)"
    else
        echo "   Version: $(docker compose version)"
    fi
else
    echo "❌ Docker Compose is not available"
    exit 1
fi

# Check if Docker daemon is running
echo "🔍 Checking Docker daemon..."
if docker info &> /dev/null; then
    echo "✅ Docker daemon is running"
else
    echo "❌ Docker daemon is not running"
    echo "💡 Try: sudo service docker start (for DooD) or wait for DinD to start"
    exit 1
fi

# Test basic Docker functionality
echo "🔍 Testing Docker functionality..."
if docker run --rm hello-world &> /dev/null; then
    echo "✅ Docker is working correctly"
else
    echo "❌ Docker test failed"
    exit 1
fi

echo ""
echo "🎉 Docker environment is ready!"
echo ""
echo "🚀 Next steps:"
echo "1. Review your .env file: cp env.example .env && nano .env"
echo "2. Run deployment script: ./scripts/deploy.sh"
echo "3. Or build manually: docker-compose build && docker-compose up -d"
echo ""
echo "📊 Monitor with:"
echo "   docker-compose logs -f chatbot"
echo "   docker-compose ps"
