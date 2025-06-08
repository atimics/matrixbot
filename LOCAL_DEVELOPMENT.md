# Local Development Setup

This guide helps you migrate from GitHub Codespaces to local development using Dev Containers.

## Prerequisites

1. **Docker Desktop**: Download and install from [docker.com](https://www.docker.com/products/docker-desktop/)
2. **Visual Studio Code**: Download from [code.visualstudio.com](https://code.visualstudio.com/)
3. **Dev Containers Extension**: Install from VS Code marketplace

## Setup Steps

### 1. Clone Repository
```bash
git clone <your-repo-url>
cd matrixbot
```

### 2. Environment Configuration
```bash
# Copy the example environment file
cp .env.example .env

# Edit .env with your actual values
code .env
```

### 3. Open in Dev Container

1. Open the project folder in VS Code
2. When prompted, click "Reopen in Container" OR
3. Press `Ctrl+Shift+P` (or `Cmd+Shift+P` on macOS)
4. Type "Dev Containers: Reopen in Container"
5. Select this option

### 4. Wait for Container Build

The dev container will:
- Build the Python environment with pyenv and poetry
- Install all dependencies
- Set up Docker-in-Docker for multi-container development
- Configure VS Code extensions

### 5. Verify Setup

Once the container is running:

```bash
# Check Python version
python --version

# Check poetry
poetry --version

# Install dependencies (if not done automatically)
poetry install

# Run tests to verify everything works
poetry run pytest
```

## Key Differences from Codespaces

### Storage and Performance
- **Local**: Faster file I/O, persistent between sessions
- **Codespaces**: Network latency, limited storage

### Resource Management
- **Local**: Use your machine's full resources
- **Codespaces**: Limited by instance size

### Networking
- **Local**: Direct access to localhost ports
- **Codespaces**: Port forwarding required

## Development Workflow

### Starting Services
```bash
# Start all services with Docker Compose
docker-compose up -d

# Or start specific services
docker-compose up postgres arweave-service
```

### Running the Chatbot
```bash
# In development mode
poetry run python run.py

# Or with the API server
poetry run python chatbot/main_with_ui.py
```

### Debugging
- Use VS Code's integrated debugger
- Set breakpoints directly in the editor
- Debug containers using Docker extension

## Port Mappings

The following ports are automatically forwarded:
- `8000`: Chatbot API server
- `3000`: Frontend UI (if running)
- `8001`: Arweave service

## Troubleshooting

### Container Won't Start
1. Ensure Docker Desktop is running
2. Check available disk space (containers need ~2-4GB)
3. Try rebuilding: `Dev Containers: Rebuild Container`

### Dependency Issues
```bash
# Clear poetry cache and reinstall
poetry cache clear pypi --all
poetry install --no-cache
```

### Docker Issues
```bash
# Reset Docker state
docker system prune -a
docker volume prune
```

### Performance Issues
- Increase Docker Desktop memory allocation (8GB+ recommended)
- Enable WSL2 integration on Windows
- Consider using volume mounts for better I/O performance

## Backup and Sync

### Important Data Locations
- `./data/`: Chatbot database and storage
- `./matrix_store/`: Matrix session data
- `./.env`: Environment configuration

### Sync with Codespaces
If migrating data from Codespaces:
1. Download data folder from Codespaces
2. Copy to local repository
3. Ensure file permissions are correct

## Additional Resources

- [Dev Containers Documentation](https://code.visualstudio.com/docs/devcontainers/containers)
- [Docker Desktop Documentation](https://docs.docker.com/desktop/)
- [Project Architecture](./ARCHITECTURE.md)
