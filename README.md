# Chatbot System

A context-aware chatbot system that manages conversation state and integrates with Matrix and Farcaster platforms.

## Features

- **Context-Aware Conversations**: Maintains evolving world state across conversations
- **Multi-Platform Integration**: Support for Matrix and Farcaster
- **Tool System**: Extensible tool execution framework
- **State Management**: Persistent storage of conversation context and world state
- **AI-Powered Decision Making**: Intelligent response generation with context awareness

## Quick Start

### Docker Deployment (Recommended)

1. **Setup environment**:
```bash
cp env.example .env
nano .env  # Fill in your API keys and credentials
```

2. **Deploy with Docker**:
```bash
./scripts/deploy.sh
```

3. **Monitor logs**:
```bash
docker-compose logs -f chatbot
```

### Development Setup

1. **Install dependencies**:
```bash
pip install -e .
```

2. **Configure environment**:
```bash
cp env.example .env
nano .env  # Add your credentials
```

3. **Run the system**:
```bash
python -m chatbot.main
```

### Using Poetry

```bash
poetry install
poetry run python -m chatbot.main
```

## Docker Setup in Dev Container

If you're using a dev container and need Docker support:

1. **Configure Docker support**:
```bash
./scripts/setup-docker.sh
```

2. **Rebuild your dev container**:
   - Open VS Code Command Palette (Ctrl+Shift+P)
   - Run: "Dev Containers: Rebuild Container"

3. **Validate setup**:
```bash
./scripts/validate-docker.sh
```

## Configuration

Required environment variables:
- `MATRIX_HOMESERVER` - Your Matrix server URL
- `MATRIX_USER_ID` - Bot's Matrix user ID
- `MATRIX_PASSWORD` - Bot's Matrix password
- `OPENROUTER_API_KEY` - OpenRouter API key for AI inference
- `NEYNAR_API_KEY` - (Optional) Farcaster API key

## Docker Commands

- **Start services**: `docker-compose up -d`
- **View logs**: `docker-compose logs -f chatbot`
- **Stop services**: `docker-compose down`
- **Restart bot**: `docker-compose restart chatbot`
- **Shell access**: `docker-compose exec chatbot bash`
- **Web interface**: http://localhost:8000 (if enabled)

## Architecture

- `chatbot/core/` - Core system components (orchestrator, world state, context management)
- `chatbot/integrations/` - Platform integrations (Matrix, Farcaster)
- `chatbot/tools/` - Tool execution system
- `chatbot/storage/` - Data persistence layer

## Testing

Run tests with:
```bash
pytest
```

For coverage reports:
```bash
pytest --cov=chatbot
```

## Control Panel

A web-based control panel is available for monitoring and managing the system:
```bash
python control_panel.py
```

Visit http://localhost:5000 to access the control panel.
