# Chatbot System

A sophisticated context-aware chatbot system with a dynamic tool-based architecture that manages conversation state and integrates with Matrix and Farcaster platforms. The system implements an advanced world state management approach for maintaining conversation context across multi-platform interactions.

## 🌟 Key Features

- **🔧 Dynamic Tool Architecture**: Extensible tool system with runtime registration and AI integration
- **🧠 Context-Aware Conversations**: Maintains evolving world state across conversations with advanced deduplication
- **🌐 Multi-Platform Integration**: Support for Matrix and Farcaster with standardized tool interfaces
- **👁️ AI Conversation Continuity**: Bot tracks its own messages for improved conversation flow
- **💾 Persistent State Management**: Robust storage of conversation context and world state
- **🤖 AI-Powered Decision Making**: Intelligent response generation with dynamic tool awareness
- **📊 Advanced Rate Limiting**: Smart rate limiting with backoff and quota management
- **🔄 Thread Management**: Intelligent conversation thread tracking and context preservation
- **📧 Matrix Room Management**: Auto-join functionality with invite handling
- **📱 Enhanced User Profiling**: Rich user metadata tracking for social platforms

## 🏗️ Architecture Overview

The system has been architected with a dynamic tool-based design for maximum extensibility and maintainability. The architecture follows a layered approach with clear separation of concerns.

### 🔧 Core Components

#### **ToolRegistry & Tool System**
- **ToolRegistry**: Manages dynamic tool registration and provides AI-ready descriptions
- **ToolInterface**: Abstract base class for all tools with standardized execution patterns
- **ActionContext**: Comprehensive dependency injection for tools (observers, configurations, state managers)

#### **World State Management**
- **WorldStateManager**: Central state coordinator with advanced message deduplication
- **Message & Channel Models**: Rich data models supporting multi-platform message metadata
- **Thread Management**: Intelligent conversation threading for platforms like Farcaster
- **Rate Limiting**: Built-in rate limit tracking and enforcement

#### **AI Integration & Orchestration**
- **ContextAwareOrchestrator**: Main coordinator using the tool system with intelligent cycle management
- **AIDecisionEngine**: Updated to receive dynamic tool descriptions and optimized payloads
- **Context Manager**: Advanced conversation context preservation and retrieval

#### **Platform Integrations**
- **Matrix Integration**: Full Matrix protocol support with room management and invite handling
- **Farcaster Integration**: Complete Farcaster API integration with enhanced user profiling
- **Standardized Interfaces**: Unified message and action handling across platforms

### 🛠️ Tool System

All platform interactions are handled through standardized tools with consistent interfaces:

#### **Core Tools**
- `WaitTool` - Intelligent observation and waiting actions with configurable intervals
- `ObserveTool` - Advanced world state observation with filtering and summarization

#### **Matrix Tools**
- `SendMatrixReplyTool` - Matrix reply functionality with thread context awareness
- `SendMatrixMessageTool` - Matrix message sending with formatting support
- `JoinMatrixRoomTool` - Automated room joining with invite acceptance

#### **Farcaster Tools**
- `SendFarcasterPostTool` - Farcaster posting with media support and rate limiting
- `SendFarcasterReplyTool` - Farcaster replying with thread context preservation
- `LikeFarcasterPostTool` - Social engagement actions with deduplication
- `QuoteFarcasterPostTool` - Quote casting with content attribution
- `FollowFarcasterUserTool` - User following functionality
- `SendFarcasterDirectMessageTool` - Private messaging capabilities

### 🎯 Key Benefits

- **🔄 Extensibility**: Add new tools by implementing `ToolInterface` and registering
- **🧹 Maintainability**: Platform logic isolated in dedicated tool classes with clear boundaries
- **🧪 Testability**: Clean dependency injection via `ActionContext` enables comprehensive testing
- **🤖 AI Integration**: Tool descriptions automatically update AI capabilities and decision-making
- **📏 Consistency**: Standardized parameter schemas and error handling across all tools
- **⚡ Performance**: Optimized payload generation and intelligent message filtering
- **🔒 Reliability**: Robust error handling, rate limiting, and state consistency

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

## 🌐 World State Management

The system implements a sophisticated world state management approach that maintains comprehensive awareness of all platform activities and conversations.

### 📊 State Components

#### **Message Management**
- **Multi-Platform Messages**: Unified message model supporting Matrix and Farcaster with platform-specific metadata
- **Rich User Profiles**: Enhanced user information including follower counts, bios, profile pictures, and verification badges
- **Deduplication**: Advanced message deduplication across channels and platforms to prevent processing duplicates
- **Thread Tracking**: Intelligent conversation thread management for platforms supporting threaded discussions

#### **Channel & Room Tracking**
- **Dynamic Channel Creation**: Automatic channel discovery and registration as the bot encounters new rooms/feeds
- **Activity Summarization**: Real-time activity summaries with user engagement metrics and timestamp ranges
- **Matrix Room Metadata**: Complete room information including topics, member counts, power levels, and encryption status
- **Invite Management**: Pending Matrix room invites with automated acceptance workflows

#### **Action History**
- **Comprehensive Logging**: Complete audit trail of all bot actions with parameters and results
- **Action Deduplication**: Prevents duplicate actions (likes, replies, follows) with intelligent tracking
- **Scheduled Action Updates**: Support for updating scheduled/pending actions with final results
- **Rate Limit Integration**: Action history informs rate limiting decisions and backoff strategies

### 🔄 State Optimization

#### **AI Payload Optimization**
- **Primary Channel Focus**: Detailed information for the active conversation channel
- **Smart Summarization**: Intelligent summarization of secondary channels to reduce token usage
- **User Context Filtering**: Bot's own messages are filtered out to focus on external interactions
- **Configurable Truncation**: Adjustable limits for messages, actions, and thread history based on AI model constraints

#### **Performance Features**
- **Efficient Updates**: Incremental state updates with minimal memory footprint
- **Background Processing**: Non-blocking state updates that don't interrupt conversation flow
- **Smart Caching**: Intelligent caching of frequently accessed state components
- **Memory Management**: Automatic cleanup of old messages and actions to prevent memory bloat

### 📈 State Analytics

The world state provides rich analytics for understanding conversation patterns and bot performance:

- **Conversation Metrics**: Message frequency, user engagement, and response patterns
- **Platform Activity**: Cross-platform activity correlation and user behavior analysis
- **Bot Performance**: Action success rates, response times, and error patterns
- **Social Dynamics**: User interaction patterns, thread participation, and engagement quality

## 🔧 Configuration Management

The system uses a centralized configuration approach with environment-based settings that support both development and production deployments.

### 📝 Core Configuration Categories

#### **AI & LLM Settings**
```bash
AI_MODEL=openai/gpt-4o-mini                    # Primary AI model
OPENROUTER_API_KEY=your_key_here              # OpenRouter API access
PRIMARY_LLM_PROVIDER=openrouter               # LLM provider selection
OLLAMA_API_URL=http://localhost:11434         # Local Ollama instance (optional)
```

#### **Platform Credentials**
```bash
# Matrix Configuration
MATRIX_HOMESERVER=https://matrix.org          # Matrix homeserver URL
MATRIX_USER_ID=@bot:matrix.org                # Bot's Matrix user ID
MATRIX_PASSWORD=secure_password               # Matrix account password
MATRIX_ROOM_ID=#room:matrix.org               # Default monitoring room

# Farcaster Configuration (Optional)
NEYNAR_API_KEY=your_neynar_key               # Neynar API for Farcaster
FARCASTER_BOT_FID=12345                      # Bot's Farcaster ID
FARCASTER_BOT_SIGNER_UUID=uuid_here          # Signing key for posts
FARCASTER_BOT_USERNAME=botname               # Bot username for filtering
```

#### **Performance Tuning**
```bash
# Core System
OBSERVATION_INTERVAL=2.0                      # Seconds between observation cycles
MAX_CYCLES_PER_HOUR=300                      # Rate limiting for AI cycles
CHATBOT_DB_PATH=chatbot.db                   # Database file location

# AI Payload Optimization
AI_CONVERSATION_HISTORY_LENGTH=10            # Messages per channel for AI
AI_ACTION_HISTORY_LENGTH=5                   # Action history depth
AI_THREAD_HISTORY_LENGTH=5                   # Thread message depth
AI_OTHER_CHANNELS_SUMMARY_COUNT=3            # Secondary channels to include
AI_INCLUDE_DETAILED_USER_INFO=true           # Full user metadata vs summary
```

### ⚙️ Advanced Configuration

The configuration system supports:
- **Environment Variable Override**: All settings can be overridden via environment variables
- **Development vs Production**: Different configurations for different deployment environments
- **Secrets Management**: Secure handling of API keys and credentials
- **Runtime Reconfiguration**: Some settings can be adjusted without restart (future enhancement)

## 🚀 Deployment Options

## Docker Setup in Dev Container

If you're using a dev container and need Docker support:

1. **Configure Docker support**:
```bash
./scripts/setup-docker.sh
```

2. **Rebuild your dev container**:
   - Open VS Code Command Palette (Ctrl+Shift+P)
   - Run: "Dev Containers: Rebuild Container"

## 🧪 Testing & Quality Assurance

The project includes comprehensive testing infrastructure to ensure reliability and maintainability.

### 🔬 Test Structure

#### **Unit Tests**
- **Core Component Tests**: Complete coverage of world state, AI engine, and orchestrator components
- **Tool System Tests**: Individual tool testing with mocked dependencies
- **Integration Tests**: End-to-end testing of platform integrations
- **Configuration Tests**: Validation of configuration loading and environment handling

#### **Test Categories**
```
tests/
├── test_ai_engine.py                 # AI decision engine testing
├── test_core.py                      # Core component unit tests
├── test_orchestrator_extended.py     # Orchestrator integration tests
├── test_world_state_extended.py      # World state management tests
├── test_tool_system.py              # Tool registry and execution tests
├── test_matrix_tools_and_observer.py # Matrix platform integration
├── test_farcaster_tools_follow_dm.py # Farcaster platform features
├── test_integration.py              # Full system integration tests
└── test_robust_json_parsing.py      # AI response parsing reliability
```

### 🎯 Quality Metrics

#### **Code Quality Tools**
- **Black**: Consistent code formatting across the entire codebase
- **isort**: Import statement organization and optimization
- **flake8**: Code style enforcement and basic linting
- **mypy**: Static type checking for improved reliability
- **pytest**: Comprehensive test framework with async support

#### **Coverage Reporting**
```bash
# Run tests with coverage
poetry run pytest tests/ --cov=chatbot --cov-report=html --cov-report=term

# View HTML coverage report
open htmlcov/index.html
```

### 🔧 Development Workflow

#### **Available Tasks**
```bash
# Main application
poetry run python -m chatbot.main

# Testing
poetry run pytest tests/ -v                           # Run all tests
poetry run pytest tests/ --cov=chatbot               # With coverage

# Code Quality
poetry run black chatbot/ && poetry run isort chatbot/  # Format code
poetry run flake8 chatbot/ && poetry run mypy chatbot/  # Lint and type check

# Development Tools
poetry run python control_panel.py                    # Control panel interface
```

#### **VS Code Tasks**
The project includes pre-configured VS Code tasks for common operations:
- **Run Chatbot Main Application**: Starts the main bot with background execution
- **Run Control Panel**: Launches the web-based control interface
- **Run Tests**: Executes the full test suite
- **Run Tests with Coverage**: Tests with HTML coverage reporting
- **Format Code**: Applies Black and isort formatting
- **Lint Code**: Runs flake8 and mypy validation

## 🐛 Debugging & Troubleshooting

### 📋 Common Issues

#### **Connection Problems**
```bash
# Check Matrix connectivity
grep "matrix_connected" chatbot.log

# Verify Farcaster API access
grep "farcaster_connected" chatbot.log

# Monitor rate limiting
grep "rate_limit" chatbot.log
```

#### **State Management Issues**
```bash
# Check world state consistency
grep "WorldState:" chatbot.log

# Monitor message deduplication
grep "Deduplicated message" chatbot.log

# Track action execution
grep "Action completed" chatbot.log
```

### 🔍 Debug Tools

#### **Enhanced Logging**
```bash
# Set debug level logging
export LOG_LEVEL=DEBUG

# Monitor specific components
grep "ContextAwareOrchestrator" chatbot.log
grep "ToolRegistry" chatbot.log
grep "WorldStateManager" chatbot.log
```

#### **Control Panel Interface**
The system includes a web-based control panel for real-time monitoring:
```bash
poetry run python control_panel.py
# Access at http://localhost:5000
```

Features:
- **Real-time State Monitoring**: Live view of world state and recent activities
- **Action History**: Complete audit trail of bot actions and results
- **Platform Status**: Connection status and health metrics for all platforms
- **Configuration Viewer**: Current configuration settings and environment variables

## 📚 API Documentation

### 🔌 Tool Development

#### **Creating Custom Tools**
```python
from chatbot.tools.base import ToolInterface, ActionContext
from typing import Dict, Any

class CustomTool(ToolInterface):
    @property
    def name(self) -> str:
        return "custom_action"
    
    @property
    def description(self) -> str:
        return "Performs a custom action with specified parameters"
    
    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "parameter1": "string (description of parameter)",
            "parameter2": "integer (another parameter description)"
        }
    
    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        # Implementation here
        return {
            "status": "success",
            "message": "Action completed successfully",
            "timestamp": time.time()
        }

# Register the tool
registry.register_tool(CustomTool())
```

#### **Tool Best Practices**
- **Parameter Validation**: Always validate input parameters before execution
- **Error Handling**: Provide meaningful error messages and proper exception handling
- **State Updates**: Use the context to update world state appropriately
- **Rate Limiting**: Respect platform rate limits and implement backoff strategies
- **Logging**: Include comprehensive logging for debugging and monitoring

### 🌐 Platform Integration

#### **Adding New Platforms**
1. **Observer Implementation**: Create an observer class for the new platform
2. **Tool Development**: Implement platform-specific tools following the ToolInterface
3. **Message Model Extensions**: Extend the Message class for platform-specific metadata
4. **Configuration Updates**: Add necessary configuration parameters
5. **Integration Testing**: Develop comprehensive tests for the new platform

## 📈 Performance & Scalability

### ⚡ Optimization Features

#### **Memory Management**
- **Message Rotation**: Automatic cleanup of old messages to prevent memory bloat
- **Action History Limits**: Configurable limits on action history retention
- **State Compression**: Efficient serialization and storage of world state
- **Garbage Collection**: Proactive cleanup of unused objects and references

#### **Processing Efficiency**
- **Async Architecture**: Fully asynchronous design for maximum concurrency
- **Batch Processing**: Efficient batch processing of multiple messages
- **Smart Filtering**: Intelligent filtering to reduce unnecessary processing
- **Cache Optimization**: Strategic caching of frequently accessed data

### 📊 Monitoring & Metrics

#### **Built-in Metrics**
- **Cycle Performance**: Monitoring of observation and decision cycle times
- **Platform Health**: Connection status and API response times for all platforms
- **Action Success Rates**: Tracking of tool execution success and failure rates
- **Memory Usage**: Monitoring of world state size and memory consumption
- **Rate Limit Status**: Real-time tracking of API rate limit utilization

#### **External Monitoring**
The system supports integration with external monitoring solutions:
- **Structured Logging**: JSON-formatted logs for easy parsing and analysis
- **Metrics Export**: Prometheus-compatible metrics endpoints (future enhancement)
- **Health Checks**: HTTP health check endpoints for load balancer integration
- **Alert Integration**: Support for webhook-based alerting systems

## 🤝 Contributing

### 📋 Development Guidelines

#### **Code Standards**
- Follow the existing code style enforced by Black and isort
- Maintain type hints for all public interfaces
- Include comprehensive docstrings for all classes and methods
- Write tests for all new functionality

#### **Pull Request Process**
1. **Fork & Branch**: Create a feature branch from the main branch
2. **Development**: Implement changes following code standards
3. **Testing**: Ensure all tests pass and add tests for new features
4. **Documentation**: Update documentation for any API or configuration changes
5. **Review**: Submit pull request with clear description of changes

#### **Architecture Decisions**
- **Tool-Based Extensions**: New functionality should be implemented as tools when possible
- **Platform Abstraction**: Maintain clean separation between platform-specific and core logic
- **Configuration Driven**: New features should be configurable rather than hard-coded
- **Backwards Compatibility**: Maintain backwards compatibility for configuration and APIs

## 📄 License & Support

### 📞 Getting Help

- **Documentation**: Check this README and inline code documentation first
- **Issues**: Report bugs and feature requests via GitHub issues
- **Discussions**: Use GitHub discussions for questions and community support
- **Contributing**: See the contributing guidelines above for development questions

### 🔄 Versioning

The project follows semantic versioning (SemVer):
- **Major versions**: Breaking changes to APIs or configuration
- **Minor versions**: New features and enhancements
- **Patch versions**: Bug fixes and security updates

Current version: `0.1.0` (Initial release with core functionality)

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

## 📄 License

Copyright (c) 2025 Ratimics

This project is licensed under the Creative Commons Attribution-NonCommercial 4.0 International License. This means:

- ✅ **You CAN**: Use, modify, and share this software for personal, educational, or research purposes
- ❌ **You CANNOT**: Use this software for commercial purposes without explicit permission
- 📝 **You MUST**: Provide attribution when using or sharing this software

### Commercial Use

For commercial licensing, partnerships, or any revenue-generating use of this software, please contact us for permission. We're open to discussing commercial licensing terms for qualified use cases.

**Contact**: github.com/cenetex

See the [LICENSE](LICENSE) file for full terms and conditions.

---

*This software is provided "as is" without warranty of any kind. Use at your own risk.*
