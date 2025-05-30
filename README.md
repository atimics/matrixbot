# Chatbot System

A context-aware chatbot system that manages conversation state and integrates with Matrix and Farcaster platforms.

## Features

- **Context-Aware Conversations**: Maintains evolving world state across conversations
- **Multi-Platform Integration**: Support for Matrix and Farcaster
- **Tool System**: Extensible tool execution framework
- **State Management**: Persistent storage of conversation context and world state
- **AI-Powered Decision Making**: Intelligent response generation with context awareness

## Installation

### Development Setup

1. Install dependencies:
```bash
pip install -e .
```

2. Configure your environment:
   - Copy configuration files and update with your credentials
   - Set up Matrix and/or Farcaster integration tokens

3. Run the system:
```bash
python -m chatbot.main
```

### Using Poetry (Recommended)

```bash
poetry install
poetry run python -m chatbot.main
```

## Configuration

The system requires configuration for:
- Matrix homeserver and credentials
- Farcaster account and API keys
- AI inference service (OpenRouter, Ollama, etc.)
- Storage backend

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
