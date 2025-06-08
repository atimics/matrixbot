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

# Function to validate Arweave wallet file
validate_arweave_wallet() {
    local wallet_file="$1"
    
    if [ ! -f "$wallet_file" ]; then
        return 1
    fi
    
    # Check if it's valid JSON
    if ! jq empty "$wallet_file" 2>/dev/null; then
        return 1
    fi
    
    # Check if it has required JWK fields
    local required_fields=("kty" "n" "e" "d" "p" "q" "dp" "dq" "qi")
    for field in "${required_fields[@]}"; do
        if ! jq -e ".$field" "$wallet_file" >/dev/null 2>&1; then
            return 1
        fi
    done
    
    return 0
}

# Check Arweave wallet setup
echo "🔐 Checking Arweave wallet setup..."
ARWEAVE_WALLET_PATH="./data/arweave_wallet.json"

if [ -f "$ARWEAVE_WALLET_PATH" ]; then
    if command_exists jq; then
        if validate_arweave_wallet "$ARWEAVE_WALLET_PATH"; then
            echo "✅ Arweave wallet found and valid"
            
            # Try to extract wallet address using Python if available
            if command_exists python3; then
                wallet_info=$(python3 -c "
import json
import hashlib
import base64
try:
    with open('$ARWEAVE_WALLET_PATH', 'r') as f:
        wallet = json.load(f)
    
    # Get basic wallet info
    print('✅ Wallet file validated')
    print(f'   Key type: {wallet.get(\"kty\", \"unknown\")}')
    
    # Try to calculate address if possible (simplified)
    try:
        n = wallet.get('n', '')
        if n:
            # This is a simplified version - full address calculation requires proper Arweave libs
            print(f'   Public key length: {len(n)} chars')
        print('   (Full address calculation requires arweave-python-client)')
    except Exception:
        print('   Address calculation skipped')
        
except Exception as e:
    print(f'❌ Error reading wallet: {e}')
" 2>/dev/null)
                echo "   $wallet_info"
                
                # Check if wallet can be used with arweave-python-client
                if python3 -c "
try:
    import arweave
    with open('$ARWEAVE_WALLET_PATH', 'r') as f:
        wallet_data = f.read()
    wallet = arweave.Wallet(wallet_data)
    print(f'✅ Wallet address: {wallet.address}')
    print(f'   Balance check: Use arweave service health endpoint')
except ImportError:
    print('⚠️  arweave-python-client not installed - address verification limited')
except Exception as e:
    print(f'❌ Wallet validation error: {e}')
" 2>/dev/null; then
                    echo "   Wallet validated with arweave-python-client"
                fi
            fi
            
            # Check wallet file permissions
            wallet_perms=$(stat -c "%a" "$ARWEAVE_WALLET_PATH" 2>/dev/null || stat -f "%A" "$ARWEAVE_WALLET_PATH" 2>/dev/null)
            if [ "$wallet_perms" != "600" ] && [ "$wallet_perms" != "0600" ]; then
                echo "   ⚠️  Wallet file permissions: $wallet_perms (recommend: 600)"
                echo "   Fix with: chmod 600 $ARWEAVE_WALLET_PATH"
            else
                echo "   ✅ Wallet file permissions secure: $wallet_perms"
            fi
            
        else
            echo "❌ Arweave wallet file exists but appears invalid"
            echo "   File: $ARWEAVE_WALLET_PATH"
            echo "   Issues detected during validation"
            echo "   🔧 Fix options:"
            echo "   1. Regenerate: python3 generate_arweave_wallet.py --force"
            echo "   2. Restore from backup if available"
            echo "   3. Check file format (should be JSON Web Key format)"
        fi
    else
        echo "⚠️  Arweave wallet file exists but jq not available for validation"
        echo "   Install jq to enable wallet validation:"
        echo "   - Ubuntu/Debian: sudo apt-get install jq"
        echo "   - macOS: brew install jq"
        echo "   File: $ARWEAVE_WALLET_PATH"
    fi
else
    echo "❌ Arweave wallet not found at: $ARWEAVE_WALLET_PATH"
    echo "   🔧 Generate wallet options:"
    echo "   1. Auto-generate: python3 generate_arweave_wallet.py"
    echo "   2. Import existing: Place wallet.json in data/ directory"
    echo "   3. Skip for now (Arweave features will be disabled)"
    echo ""
    echo "   ⚠️  Without Arweave wallet:"
    echo "   - Media uploads to Arweave will fail"
    echo "   - NFT metadata storage will be unavailable"
    echo "   - Permanent data features disabled"
fi

# Check Arweave service configuration
echo "🔧 Checking Arweave service configuration..."
if [ -f ".env" ]; then
    # Check Arweave-related environment variables
    arweave_vars=(
        "ARWEAVE_INTERNAL_UPLOADER_SERVICE_URL"
        "ARWEAVE_GATEWAY_URL"
    )
    
    missing_arweave_vars=()
    for var in "${arweave_vars[@]}"; do
        if ! grep -q "^${var}=" .env || grep -q "^${var}=$" .env; then
            missing_arweave_vars+=("$var")
        fi
    done
    
    if [ ${#missing_arweave_vars[@]} -eq 0 ]; then
        echo "✅ Arweave service configuration found"
        
        # Show current configuration
        arweave_service_url=$(grep "^ARWEAVE_INTERNAL_UPLOADER_SERVICE_URL=" .env | cut -d'=' -f2 | tr -d '"')
        arweave_gateway=$(grep "^ARWEAVE_GATEWAY_URL=" .env | cut -d'=' -f2 | tr -d '"')
        
        echo "   Service URL: ${arweave_service_url:-'not set'}"
        echo "   Gateway URL: ${arweave_gateway:-'not set'}"
    else
        echo "⚠️  Missing Arweave configuration:"
        for var in "${missing_arweave_vars[@]}"; do
            echo "   - $var"
        done
        echo "   Default values will be used from .env.example"
    fi
fi

# Validate environment configuration
echo "🔧 Validating environment configuration..."
if [ -f ".env" ]; then
    # Check critical environment variables
    missing_vars=()
    optional_vars=()
    
    # Critical variables for basic functionality
    critical_vars=(
        "OPENROUTER_API_KEY"
        "MATRIX_HOMESERVER"
        "MATRIX_USER_ID"
        "MATRIX_PASSWORD"
        "MATRIX_ROOM_ID"
    )
    
    # Optional but recommended variables
    recommended_vars=(
        "NEYNAR_API_KEY"
        "FARCASTER_BOT_FID"
        "FARCASTER_BOT_SIGNER_UUID"
        "REPLICATE_API_TOKEN"
        "GOOGLE_API_KEY"
    )
    
    for var in "${critical_vars[@]}"; do
        if ! grep -q "^${var}=" .env || grep -q "^${var}=$" .env || grep -q "^${var}=\"\"$" .env; then
            missing_vars+=("$var")
        fi
    done
    
    for var in "${recommended_vars[@]}"; do
        if ! grep -q "^${var}=" .env || grep -q "^${var}=$" .env || grep -q "^${var}=\"\"$" .env; then
            optional_vars+=("$var")
        fi
    done
    
    if [ ${#missing_vars[@]} -eq 0 ]; then
        echo "✅ All critical environment variables are configured"
    else
        echo "❌ Missing critical environment variables:"
        for var in "${missing_vars[@]}"; do
            echo "   - $var"
        done
        echo "   Please edit .env file: code .env"
    fi
    
    if [ ${#optional_vars[@]} -gt 0 ]; then
        echo "⚠️  Optional environment variables not configured:"
        for var in "${optional_vars[@]}"; do
            echo "   - $var (for enhanced functionality)"
        done
    fi
else
    echo "❌ .env file not found - this will cause startup issues"
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

# Check for required system packages
echo "🔧 Checking system dependencies..."
required_packages=("jq" "curl" "git")
missing_packages=()

for package in "${required_packages[@]}"; do
    if ! command_exists "$package"; then
        missing_packages+=("$package")
    fi
done

if [ ${#missing_packages[@]} -gt 0 ]; then
    echo "📦 Installing missing system packages..."
    if [ "$(uname)" = "Linux" ]; then
        if command_exists apt-get; then
            sudo apt-get update
            for package in "${missing_packages[@]}"; do
                echo "Installing $package..."
                sudo apt-get install -y "$package"
            done
        elif command_exists yum; then
            for package in "${missing_packages[@]}"; do
                echo "Installing $package..."
                sudo yum install -y "$package"
            done
        else
            echo "⚠️  Please install these packages manually: ${missing_packages[*]}"
        fi
    else
        echo "⚠️  Please install these packages manually: ${missing_packages[*]}"
        echo "   On macOS with Homebrew: brew install ${missing_packages[*]}"
    fi
else
    echo "✅ All required system packages are available"
fi

# Verify Python and pip
echo "🐍 Checking Python environment..."
if ! command_exists python3; then
    echo "❌ Python 3 not found. Please install Python 3.8 or later."
    exit 1
else
    python_version=$(python3 --version)
    echo "✅ Python found: $python_version"
fi

if ! command_exists pip3 && ! command_exists pip; then
    echo "❌ pip not found. Please install pip."
    exit 1
else
    if command_exists pip3; then
        pip_version=$(pip3 --version)
        echo "✅ pip found: $pip_version"
    else
        pip_version=$(pip --version)
        echo "✅ pip found: $pip_version"
    fi
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

# Function to wait for service to be ready
wait_for_service() {
    local service_name="$1"
    local url="$2"
    local max_attempts=30
    local attempt=1
    
    echo "⏳ Waiting for $service_name to be ready..."
    while [ $attempt -le $max_attempts ]; do
        if curl -s -f "$url" >/dev/null 2>&1; then
            echo "✅ $service_name is ready"
            return 0
        fi
        echo "   Attempt $attempt/$max_attempts: $service_name not ready yet..."
        sleep 2
        attempt=$((attempt + 1))
    done
    
    echo "❌ $service_name failed to start after $max_attempts attempts"
    return 1
}

# Function to check service health
check_service_health() {
    local service_name="$1"
    local health_url="$2"
    
    echo "🏥 Checking $service_name health..."
    if response=$(curl -s "$health_url" 2>/dev/null); then
        echo "✅ $service_name health check passed"
        echo "   Response: $response"
        return 0
    else
        echo "❌ $service_name health check failed"
        return 1
    fi
}

# Launch the control panel and services
echo "🚀 Starting services..."
if [ -f "docker-compose.yml" ]; then
    echo "Starting all services with docker-compose..."
    docker-compose up -d
    
    # Wait for services to start and perform health checks
    echo "⏳ Waiting for services to start..."
    sleep 15
    
    # Check individual service health
    services_healthy=true
    
    echo "🏥 Performing service health checks..."
    
    # Check UI service
    if wait_for_service "UI Service" "http://localhost:3000"; then
        echo "✅ UI Service is responding"
    else
        echo "❌ UI Service failed to start"
        services_healthy=false
    fi
    
    # Check API server
    if wait_for_service "API Server" "http://localhost:8000/health"; then
        if check_service_health "API Server" "http://localhost:8000/health"; then
            echo "✅ API Server is healthy"
        else
            echo "⚠️  API Server is responding but health check failed"
        fi
    else
        echo "❌ API Server failed to start"
        services_healthy=false
    fi
    
    # Check Arweave service
    if wait_for_service "Arweave Service" "http://localhost:8001/health"; then
        if check_service_health "Arweave Service" "http://localhost:8001/health"; then
            echo "✅ Arweave Service is healthy"
            
            # Check wallet status if possible
            if wallet_info=$(curl -s "http://localhost:8001/wallet-info" 2>/dev/null); then
                if echo "$wallet_info" | jq -e '.address' >/dev/null 2>&1; then
                    wallet_address=$(echo "$wallet_info" | jq -r '.address')
                    wallet_balance=$(echo "$wallet_info" | jq -r '.balance_ar // "Unknown"')
                    echo "   Wallet Address: $wallet_address"
                    echo "   Wallet Balance: $wallet_balance AR"
                    
                    # Warn if balance is low
                    if [ "$wallet_balance" != "Unknown" ]; then
                        balance_float=$(echo "$wallet_balance" | cut -d' ' -f1)
                        if [ "$(echo "$balance_float < 0.1" | bc -l 2>/dev/null)" = "1" ] 2>/dev/null; then
                            echo "   ⚠️  Wallet balance is low - consider funding for Arweave operations"
                        fi
                    fi
                fi
            fi
        else
            echo "⚠️  Arweave Service is responding but health check failed"
        fi
    else
        echo "❌ Arweave Service failed to start"
        services_healthy=false
    fi
    
    # Check if services are running
    echo "📊 Service status:"
    docker-compose ps
    
    if [ "$services_healthy" = true ]; then
        echo ""
        echo "🎉 All services are healthy and ready!"
    else
        echo ""
        echo "⚠️  Some services may have issues. Check logs with: docker-compose logs"
    fi
    
    echo ""
    echo "🌐 Service URLs:"
    echo "=================="
    echo "• Control Panel: http://localhost:3000"
    echo "• API Server: http://localhost:8000"
    echo "• API Health: http://localhost:8000/health"
    echo "• API Docs: http://localhost:8000/docs"
    echo "• Arweave Service: http://localhost:8001"
    echo "• Arweave Health: http://localhost:8001/health"
    
    # Try to open the control panel in browser
    if command_exists "$BROWSER"; then
        "$BROWSER" "http://localhost:3000" &
    elif [ -n "$BROWSER" ]; then
        $BROWSER "http://localhost:3000" &
    else
        echo ""
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
