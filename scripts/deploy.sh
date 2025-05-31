#!/bin/bash
# Deployment script for Ratimics Chatbot

set -e

echo "🤖 Ratimics Chatbot Deployment Script"
echo "======================================"

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "📝 Please copy .env.example to .env and fill in your configuration:"
    echo "   cp .env.example .env"
    echo "   nano .env"
    exit 1
fi

# Check if required environment variables are set
echo "🔍 Checking configuration..."
source .env

required_vars=("MATRIX_HOMESERVER" "MATRIX_USER_ID" "MATRIX_PASSWORD" "OPENROUTER_API_KEY")
missing_vars=()

for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -ne 0 ]; then
    echo "❌ Missing required environment variables:"
    printf '   - %s\n' "${missing_vars[@]}"
    echo "📝 Please update your .env file"
    exit 1
fi

echo "✅ Configuration looks good!"

# Build and deploy
echo "🏗️  Building Docker images..."
docker-compose build

echo "🚀 Starting chatbot services..."
docker-compose up -d

echo "📊 Checking service status..."
docker-compose ps

echo ""
echo "🎉 Deployment complete!"
echo ""
echo "📋 Useful commands:"
echo "   View logs:     docker-compose logs -f chatbot"
echo "   Stop services: docker-compose down"
echo "   Restart:       docker-compose restart chatbot"
echo "   Shell access:  docker-compose exec chatbot bash"
echo ""
echo "🌐 Web interface (if enabled): http://localhost:8000"
echo ""
echo "✨ Your chatbot should now be running and connected to Matrix!"
