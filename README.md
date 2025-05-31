# Chatbot System

A context-aware chatbot system with a dynamic tool-based architecture that manages conversation state and integrates with Matrix and Farcaster platforms.

## Features

- **Dynamic Tool Architecture**: Extensible tool system with runtime registration and AI integration
- **Context-Aware Conversations**: Maintains evolving world state across conversations
- **Multi-Platform Integration**: Support for Matrix and Farcaster with standardized tool interfaces
- **AI Blindness Fix**: Bot can see its own messages for improved conversation continuity
- **State Management**: Persistent storage of conversation context and world state
- **AI-Powered Decision Making**: Intelligent response generation with dynamic tool awareness

## Architecture Overview

The system has been architected with a dynamic tool-based design for maximum extensibility:

### Core Components

- **ToolRegistry**: Manages dynamic tool registration and provides AI-ready descriptions
- **ToolInterface**: Abstract base class for all tools with standardized execution
- **ActionContext**: Dependency injection for tools (observers, configurations)
- **ContextAwareOrchestrator**: Main coordinator using the tool system
- **AIDecisionEngine**: Updated to receive dynamic tool descriptions

### Tool System

All platform interactions are handled through standardized tools:

- `WaitTool` - Observation and waiting actions
- `SendMatrixReplyTool` - Matrix reply functionality
- `SendMatrixMessageTool` - Matrix message sending
- `SendFarcasterPostTool` - Farcaster posting
- `SendFarcasterReplyTool` - Farcaster replying

### Benefits

- **Extensibility**: Add new tools by implementing `ToolInterface` and registering
- **Maintainability**: Platform logic isolated in dedicated tool classes
- **Testability**: Clean dependency injection via `ActionContext`
- **AI Integration**: Tool descriptions automatically update AI capabilities
- **Consistency**: Standardized parameter schemas across all tools

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

### Directory Structure
- `chatbot/core/` - Core system components (orchestrator, world state, context management, AI engine)
- `chatbot/tools/` - Dynamic tool system with registry and implementations
- `chatbot/integrations/` - Platform observers (Matrix, Farcaster)
- `chatbot/storage/` - Data persistence layer

### Tool Development

To add a new tool:

1. **Create the tool class**:
```python
from chatbot.tools.base import ToolInterface, ActionContext

class MyCustomTool(ToolInterface):
    @property
    def name(self) -> str:
        return "my_custom_action"
    
    @property  
    def description(self) -> str:
        return "Description of what this tool does"
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "param1": "string (description)",
            "param2": "int (description)"
        }
    
    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        # Implementation here
        return {"success": True, "message": "Action completed"}
```

2. **Register the tool**:
```python
# In orchestrator's _initialize_tools method
self.tool_registry.register_tool(MyCustomTool())
```

The AI will automatically receive the tool description and can use it in decisions.

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
