#!/bin/bash
#
# Storage Service Switcher
#
# Helper script to switch between Arweave and S3 storage services.
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}🔄 MatrixBot Storage Service Switcher${NC}"
    echo "==========================================="
    echo
}

print_help() {
    echo "Usage: $0 [arweave|s3|status|help]"
    echo
    echo "Commands:"
    echo "  arweave  - Switch to Arweave blockchain storage"
    echo "  s3       - Switch to S3 cloud storage"
    echo "  status   - Show current storage service status"
    echo "  help     - Show this help message"
    echo
    echo "Examples:"
    echo "  $0 arweave    # Use Arweave for permanent storage"
    echo "  $0 s3         # Use S3 for fast cloud storage"
    echo "  $0 status     # Check which service is running"
}

check_requirements() {
    if ! command -v docker-compose &> /dev/null && ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Error: docker-compose or docker is required${NC}"
        exit 1
    fi
    
    if [ ! -f "docker-compose.yml" ]; then
        echo -e "${RED}❌ Error: docker-compose.yml not found. Run from project root.${NC}"
        exit 1
    fi
}

get_current_service() {
    # Check which service is running
    if docker-compose ps | grep -q "arweave_service.*Up"; then
        echo "arweave"
    elif docker-compose ps | grep -q "s3_service.*Up"; then
        echo "s3"
    else
        echo "none"
    fi
}

show_status() {
    local current=$(get_current_service)
    
    echo -e "${BLUE}📊 Current Storage Service Status${NC}"
    echo "--------------------------------"
    
    case $current in
        arweave)
            echo -e "✅ Arweave service is ${GREEN}running${NC}"
            echo "   - Permanent blockchain storage"
            echo "   - Requires AR tokens for uploads"
            echo "   - Port: 8001"
            ;;
        s3)
            echo -e "✅ S3 service is ${GREEN}running${NC}"
            echo "   - Fast cloud storage with CDN"
            echo "   - Uses S3-compatible storage"
            echo "   - Port: 8001"
            ;;
        none)
            echo -e "❌ No storage service is ${RED}running${NC}"
            echo "   - Use '$0 arweave' or '$0 s3' to start a service"
            ;;
    esac
    
    echo
    
    # Show docker-compose status
    echo -e "${BLUE}🐳 Docker Services Status${NC}"
    echo "------------------------"
    docker-compose ps --services | while read service; do
        if docker-compose ps "$service" | grep -q "Up"; then
            echo -e "✅ $service is ${GREEN}running${NC}"
        else
            echo -e "❌ $service is ${RED}stopped${NC}"
        fi
    done
}

switch_to_arweave() {
    echo -e "${YELLOW}🔄 Switching to Arweave storage service...${NC}"
    
    # Check if Arweave wallet exists
    if [ ! -f "data/arweave_wallet.json" ]; then
        echo -e "${YELLOW}⚠️  Warning: Arweave wallet not found at data/arweave_wallet.json${NC}"
        echo "   Generate one with: python generate_arweave_wallet.py"
        echo "   Or create the data directory and add your wallet file"
    fi
    
    # Stop S3 service if running
    if docker-compose ps | grep -q "s3_service.*Up"; then
        echo "   Stopping S3 service..."
        docker-compose stop s3-service
    fi
    
    # Start Arweave service
    echo "   Starting Arweave service..."
    docker-compose --profile arweave up -d arweave-service
    
    # Wait for service to be ready
    echo "   Waiting for service to be ready..."
    sleep 5
    
    if docker-compose ps | grep -q "arweave_service.*Up"; then
        echo -e "${GREEN}✅ Successfully switched to Arweave storage service${NC}"
        echo "   Service running at: http://localhost:8001"
        echo "   Health check: curl http://localhost:8001/health"
    else
        echo -e "${RED}❌ Failed to start Arweave service${NC}"
        echo "   Check logs: docker-compose logs arweave-service"
        exit 1
    fi
}

switch_to_s3() {
    echo -e "${YELLOW}🔄 Switching to S3 storage service...${NC}"
    
    # Check required environment variables
    if [ -f ".env" ]; then
        source .env
        missing_vars=()
        
        [ -z "$S3_API_KEY" ] && missing_vars+=("S3_API_KEY")
        [ -z "$S3_API_ENDPOINT" ] && missing_vars+=("S3_API_ENDPOINT")
        [ -z "$CLOUDFRONT_DOMAIN" ] && missing_vars+=("CLOUDFRONT_DOMAIN")
        
        if [ ${#missing_vars[@]} -gt 0 ]; then
            echo -e "${YELLOW}⚠️  Warning: Missing required environment variables:${NC}"
            for var in "${missing_vars[@]}"; do
                echo "     - $var"
            done
            echo "   Please update your .env file before starting S3 service"
        fi
    else
        echo -e "${YELLOW}⚠️  Warning: .env file not found${NC}"
        echo "   Copy .env.example to .env and configure S3 variables"
    fi
    
    # Stop Arweave service if running
    if docker-compose ps | grep -q "arweave_service.*Up"; then
        echo "   Stopping Arweave service..."
        docker-compose stop arweave-service
    fi
    
    # Start S3 service
    echo "   Starting S3 service..."
    docker-compose --profile s3 up -d s3-service
    
    # Wait for service to be ready
    echo "   Waiting for service to be ready..."
    sleep 5
    
    if docker-compose ps | grep -q "s3_service.*Up"; then
        echo -e "${GREEN}✅ Successfully switched to S3 storage service${NC}"
        echo "   Service running at: http://localhost:8001"
        echo "   Health check: curl http://localhost:8001/health"
        echo "   Test with: python s3-service/test_s3_service.py"
    else
        echo -e "${RED}❌ Failed to start S3 service${NC}"
        echo "   Check logs: docker-compose logs s3-service"
        exit 1
    fi
}

main() {
    print_header
    check_requirements
    
    case "${1:-}" in
        arweave)
            switch_to_arweave
            ;;
        s3)
            switch_to_s3
            ;;
        status)
            show_status
            ;;
        help|--help|-h)
            print_help
            ;;
        "")
            echo -e "${YELLOW}⚠️  No command specified${NC}"
            echo
            print_help
            echo
            show_status
            ;;
        *)
            echo -e "${RED}❌ Unknown command: $1${NC}"
            echo
            print_help
            exit 1
            ;;
    esac
}

main "$@"
