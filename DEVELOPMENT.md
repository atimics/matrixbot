# 🚀 Development Guide

Comprehensive development guide for the Chatbot System, including setup procedures, workflows, testing strategies, and contribution guidelines.

[![Development](https://img.shields.io/badge/development-active-green.svg)](https://github.com)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Poetry](https://img.shields.io/badge/dependency%20management-poetry-blue)](https://python-poetry.org/)

## 📋 Table of Contents

- [🛠️ Development Environment Setup](#️-development-environment-setup)
- [📁 Project Structure](#-project-structure)
- [🔄 Development Workflow](#-development-workflow)
- [🧪 Testing Guidelines](#-testing-guidelines)
- [📏 Code Quality Standards](#-code-quality-standards)
- [🐛 Debugging & Troubleshooting](#-debugging--troubleshooting)
- [🚀 Deployment Options](#-deployment-options)
- [🤝 Contributing Guidelines](#-contributing-guidelines)
- [📋 Development Roadmap](#-development-roadmap)

## 🛠️ Development Environment Setup

### Prerequisites

- **Python 3.10+**: Required for modern type hints and asyncio features
- **Poetry**: Dependency management and virtual environment handling
- **Git**: Version control and collaboration
- **VS Code** (recommended): IDE with excellent Python and dev container support

### Quick Setup

1. **Clone the Repository**:
```bash
git clone <repository-url>
cd python3-poetry-pyenv
```

2. **Install Dependencies**:
```bash
# Using Poetry (recommended)
poetry install

# Or using pip
pip install -e .
```

3. **Environment Configuration**:
```bash
cp .env.example .env
nano .env  # Configure your API keys and credentials
```

4. **Verify Installation**:
```bash
poetry run python -m chatbot.main --help
```

### Development Container Setup

For consistent development environments, use the provided dev container:

1. **Open in VS Code**:
   - Install the "Dev Containers" extension
   - Open the project folder
   - When prompted, select "Reopen in Container"

2. **Container Features**:
   - Ubuntu 22.04 LTS environment
   - Python 3.10+ with Poetry pre-installed
   - Git, Docker CLI, and common development tools
   - VS Code extensions for Python development
   - Pre-configured tasks and debugging

3. **Docker Support**:
   - Docker CLI available inside the container
   - Can build and run containers for testing
   - Access to host Docker daemon

### Manual Environment Setup

If not using the dev container:

1. **Python Environment**:
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
# or
venv\Scripts\activate  # Windows

# Install Poetry in the virtual environment
pip install poetry
poetry install
```

2. **Pre-commit Hooks** (optional but recommended):
```bash
pip install pre-commit
pre-commit install
```

3. **VS Code Configuration**:
   - Install Python extension
   - Configure Python interpreter to use the virtual environment
   - Install recommended extensions (Black, isort, Pylint)

## 📁 Project Structure

### High-Level Organization

```
chatbot-system/
├── chatbot/                    # Main application package
│   ├── core/                   # Core system components
│   ├── tools/                  # Tool system implementation
│   ├── integrations/           # Platform integrations
│   ├── storage/                # Data storage components
│   ├── config.py               # Configuration management
│   └── main.py                 # Application entry point
├── tests/                      # Test suite
├── scripts/                    # Development and deployment scripts
├── docs/                       # Additional documentation
├── .devcontainer/             # Dev container configuration
├── pyproject.toml             # Project configuration and dependencies
├── README.md                  # Project overview and setup
├── ARCHITECTURE.md            # Detailed architecture documentation
└── API.md                     # API reference documentation
```

### Core Components Deep Dive

#### `chatbot/core/`
- **`orchestrator.py`**: Main coordination and lifecycle management
- **`ai_engine.py`**: AI integration and decision-making logic
- **`world_state.py`**: Comprehensive state management system
- **`context.py`**: Conversation context and memory management

#### `chatbot/tools/`
- **`base.py`**: Tool interface definitions and base classes
- **`registry.py`**: Tool registration and management system
- **`core_tools.py`**: Essential tools (wait, observe)
- **`matrix_tools.py`**: Matrix platform tools
- **`farcaster_tools.py`**: Farcaster platform tools

#### `chatbot/integrations/`
- **`matrix/`**: Complete Matrix protocol integration
- **`farcaster/`**: Farcaster API integration via Neynar

#### `tests/`
- **Unit Tests**: Individual component testing
- **Integration Tests**: Cross-component and platform testing
- **End-to-End Tests**: Complete system workflow testing

## 🔄 Development Workflow

### Daily Development Process

1. **Start Development Environment**:
```bash
# If using Poetry
poetry shell
poetry run python -m chatbot.main

# Or using VS Code tasks
# Ctrl+Shift+P -> "Tasks: Run Task" -> "Run Chatbot Main Application"
```

2. **Monitor System**:
```bash
# Watch logs in real-time
tail -f chatbot.log

# Or use the control panel
poetry run python control_panel.py
# Access at http://localhost:5000
```

3. **Development Testing**:
```bash
# Run specific tests during development
poetry run pytest tests/test_your_component.py -v

# Run with coverage
poetry run pytest tests/ --cov=chatbot --cov-report=term
```

### Feature Development Process

1. **Create Feature Branch**:
```bash
git checkout -b feature/your-feature-name
```

2. **Develop with TDD**:
   - Write tests first for new functionality
   - Implement the minimum code to pass tests
   - Refactor and optimize while keeping tests green

3. **Continuous Testing**:
```bash
# Run tests automatically on file changes
poetry run pytest-watch tests/
```

4. **Code Quality Checks**:
```bash
# Format code
poetry run black chatbot/
poetry run isort chatbot/

# Lint and type check
poetry run flake8 chatbot/
poetry run mypy chatbot/

# Or use the VS Code task
# "Tasks: Run Task" -> "Format Code"
```

5. **Integration Testing**:
```bash
# Test with actual platforms (use test accounts)
MATRIX_ROOM_ID="#test-room:matrix.org" poetry run python -m chatbot.main
```

### Git Workflow

#### Branch Strategy
- **`main`**: Production-ready code
- **`develop`**: Integration branch for features
- **`feature/*`**: Individual feature development
- **`hotfix/*`**: Critical production fixes
- **`release/*`**: Release preparation

#### Commit Conventions
Use conventional commit messages for better automation and changelog generation:

```bash
# Feature commits
git commit -m "feat(tools): add new Farcaster quote tool"

# Bug fixes
git commit -m "fix(world-state): resolve message deduplication issue"

# Documentation
git commit -m "docs(api): update tool interface documentation"

# Refactoring
git commit -m "refactor(orchestrator): improve error handling"

# Tests
git commit -m "test(farcaster): add integration tests for posting"
```

## 🧪 Testing Guidelines

### Test Organization

#### Unit Tests
Focus on individual components in isolation:

```python
# tests/test_world_state.py
import pytest
from chatbot.core.world_state import WorldStateManager, Message

class TestWorldStateManager:
    def test_add_message_deduplication(self):
        """Test that duplicate messages are properly filtered."""
        manager = WorldStateManager()
        message1 = Message(
            id="test_msg_1",
            channel_id="test_channel",
            channel_type="matrix",
            sender="test_user",
            content="Hello world",
            timestamp=1640995200.0
        )
        message2 = message1  # Same message
        
        manager.add_message("test_channel", message1)
        manager.add_message("test_channel", message2)
        
        # Should only have one message due to deduplication
        assert len(manager.get_all_messages()) == 1
```

#### Integration Tests
Test interactions between components:

```python
# tests/test_tool_integration.py
import pytest
from chatbot.tools.registry import ToolRegistry
from chatbot.tools.core_tools import WaitTool
from chatbot.tools.base import ActionContext

@pytest.mark.asyncio
async def test_tool_execution_with_context():
    """Test tool execution with proper context injection."""
    registry = ToolRegistry()
    wait_tool = WaitTool()
    registry.register_tool(wait_tool)
    
    context = ActionContext()
    result = await wait_tool.execute({"seconds": 0.1}, context)
    
    assert result["status"] == "success"
    assert "waited" in result["message"]
```

#### End-to-End Tests
Test complete workflows:

```python
# tests/test_e2e_workflows.py
@pytest.mark.asyncio
@pytest.mark.slow
async def test_complete_message_processing_workflow():
    """Test the complete message processing workflow."""
    # This test requires actual platform connections
    # Use test accounts and isolated test rooms
    pass
```

### Test Configuration

#### pytest Configuration
```ini
# pytest.ini
[tool:pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
markers =
    slow: marks tests as slow (deselect with '-m "not slow"')
    integration: marks tests as integration tests
    unit: marks tests as unit tests
```

#### Test Categories

Run specific test categories:

```bash
# Unit tests only (fast)
poetry run pytest -m unit

# Integration tests (medium speed)
poetry run pytest -m integration

# All tests except slow ones
poetry run pytest -m "not slow"

# Specific test file
poetry run pytest tests/test_world_state.py -v

# Test with pattern matching
poetry run pytest -k "test_message" -v
```

### Mocking and Fixtures

#### Common Fixtures
```python
# tests/conftest.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from chatbot.core.world_state import WorldStateManager
from chatbot.tools.base import ActionContext

@pytest.fixture
def world_state_manager():
    """Provide a clean WorldStateManager for testing."""
    return WorldStateManager()

@pytest.fixture
def mock_action_context():
    """Provide a mocked ActionContext for tool testing."""
    context = ActionContext()
    context.matrix_observer = AsyncMock()
    context.farcaster_observer = AsyncMock()
    context.world_state_manager = MagicMock()
    return context
```

#### Platform Mocking
```python
# tests/mocks/matrix_mocks.py
from unittest.mock import AsyncMock

class MockMatrixObserver:
    def __init__(self):
        self.send_message = AsyncMock(return_value={"status": "success"})
        self.join_room = AsyncMock(return_value={"status": "success"})
        self.is_connected = True
```

## 📏 Code Quality Standards

### Code Formatting

#### Black Configuration
```toml
# pyproject.toml
[tool.black]
line-length = 88
target-version = ['py310']
include = '\.pyi?$'
extend-exclude = '''
/(
  | \.git
  | \.hg
  | \.mypy_cache
  | \.tox
  | \.venv
  | _build
  | buck-out
  | build
  | dist
)/
'''
```

#### isort Configuration
```toml
# pyproject.toml
[tool.isort]
profile = "black"
multi_line_output = 3
include_trailing_comma = true
force_grid_wrap = 0
use_parentheses = true
ensure_newline_before_comments = true
line_length = 88
```

### Type Hints

Use comprehensive type hints throughout the codebase:

```python
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass

@dataclass
class Message:
    id: str
    content: str
    timestamp: float
    metadata: Dict[str, Any]

async def process_message(
    message: Message, 
    context: ActionContext
) -> Dict[str, Union[str, bool]]:
    """Process a message with proper type annotations."""
    result: Dict[str, Union[str, bool]] = {
        "processed": True,
        "message": f"Processed message {message.id}"
    }
    return result
```

### Documentation Standards

#### Docstring Format
Use Google-style docstrings:

```python
def complex_function(
    param1: str, 
    param2: int, 
    param3: Optional[Dict[str, Any]] = None
) -> List[str]:
    """
    Brief description of what the function does.
    
    Longer description if needed, explaining the purpose and behavior
    in more detail.
    
    Args:
        param1: Description of the first parameter
        param2: Description of the second parameter
        param3: Optional parameter with default value
        
    Returns:
        List of strings representing the result
        
    Raises:
        ValueError: When param2 is negative
        KeyError: When required key is missing from param3
        
    Example:
        >>> result = complex_function("test", 42)
        >>> print(result)
        ['processed', 'test', 'with', '42']
    """
    if param2 < 0:
        raise ValueError("param2 must be non-negative")
        
    # Implementation here
    return ["processed", param1, "with", str(param2)]
```

#### Module Documentation
```python
"""
Module Name: Brief Description

This module provides comprehensive functionality for [specific purpose].
It includes classes and functions for [main use cases].

Key Classes:
    - ClassName: Description of the class
    - AnotherClass: Description of another class

Key Functions:
    - function_name(): Description of the function

Example:
    Basic usage example:
    
    >>> from module import ClassName
    >>> instance = ClassName()
    >>> result = instance.method()
"""
```

### Error Handling

#### Exception Hierarchy
```python
# chatbot/exceptions.py
class ChatbotError(Exception):
    """Base exception for all chatbot errors."""
    pass

class ConfigurationError(ChatbotError):
    """Raised when configuration is invalid."""
    pass

class PlatformError(ChatbotError):
    """Raised when platform integration fails."""
    pass

class ToolError(ChatbotError):
    """Raised when tool execution fails."""
    pass
```

#### Error Handling Patterns
```python
import logging
from typing import Optional

logger = logging.getLogger(__name__)

async def robust_operation() -> Optional[Dict[str, Any]]:
    """Example of robust error handling."""
    try:
        # Attempt the operation
        result = await risky_operation()
        logger.info("Operation completed successfully")
        return result
        
    except PlatformError as e:
        logger.error(f"Platform error: {e}")
        # Handle platform-specific errors
        return None
        
    except ToolError as e:
        logger.error(f"Tool error: {e}")
        # Handle tool-specific errors
        return None
        
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        # Handle unexpected errors
        raise ChatbotError(f"Operation failed: {e}") from e
```

## 🐛 Debugging & Troubleshooting

### Logging Configuration

#### Enhanced Logging Setup
```python
import logging
import colorlog

def setup_development_logging():
    """Setup colorized logging for development."""
    handler = colorlog.StreamHandler()
    handler.setFormatter(colorlog.ColoredFormatter(
        '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors={
            'DEBUG': 'cyan',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'red,bg_white',
        }
    ))
    
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.DEBUG)
```

#### Component-Specific Logging
```python
# Get component-specific loggers
orchestrator_logger = logging.getLogger('chatbot.core.orchestrator')
world_state_logger = logging.getLogger('chatbot.core.world_state')
matrix_logger = logging.getLogger('chatbot.integrations.matrix')

# Filter logs in development
logging.getLogger('chatbot.integrations.matrix').setLevel(logging.WARNING)
```

### Debug Tools

#### Interactive Debugging
```python
# For complex debugging, use built-in breakpoints
import pdb; pdb.set_trace()

# Or in async contexts
import asyncio
await asyncio.sleep(0)  # Add breakpoint here in debugger
```

#### Debug Scripts
Create debug scripts for specific scenarios:

```python
# debug_world_state.py
import asyncio
from chatbot.core.world_state import WorldStateManager

async def debug_world_state():
    """Debug world state operations."""
    manager = WorldStateManager()
    
    # Add test data
    # ... test operations ...
    
    # Print current state
    print(manager.to_json())
    
if __name__ == "__main__":
    asyncio.run(debug_world_state())
```

### Performance Profiling

#### Memory Profiling
```bash
# Install memory profiler
pip install memory-profiler

# Profile memory usage
python -m memory_profiler debug_script.py
```

#### Time Profiling
```python
import cProfile
import pstats

def profile_function():
    """Profile a specific function."""
    profiler = cProfile.Profile()
    profiler.enable()
    
    # Your code here
    
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative').print_stats(10)
```

### Common Issues and Solutions

#### Issue: "Module not found" errors
**Solution**: Ensure you're using the correct Python environment:
```bash
which python
poetry env info
poetry shell
```

#### Issue: Platform connection failures
**Solution**: Check configuration and network connectivity:
```bash
# Test Matrix connectivity
curl -X GET "https://matrix.org/_matrix/client/versions"

# Check environment variables
env | grep MATRIX
env | grep FARCASTER
```

#### Issue: AI API rate limiting
**Solution**: Implement proper rate limiting and error handling:
```python
import asyncio
from datetime import datetime, timedelta

class RateLimiter:
    def __init__(self, calls_per_minute: int = 60):
        self.calls_per_minute = calls_per_minute
        self.calls = []
    
    async def wait_if_needed(self):
        now = datetime.now()
        # Remove calls older than 1 minute
        self.calls = [call_time for call_time in self.calls 
                     if now - call_time < timedelta(minutes=1)]
        
        if len(self.calls) >= self.calls_per_minute:
            sleep_time = 60 - (now - self.calls[0]).total_seconds()
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
        
        self.calls.append(now)
```

## 🤝 Contributing Guidelines

### Before Contributing

1. **Read Documentation**: Familiarize yourself with the architecture and API
2. **Check Issues**: Look for existing issues or feature requests
3. **Discuss Changes**: For major changes, open an issue for discussion first

### Contribution Process

1. **Fork and Clone**:
```bash
git clone https://github.com/yourusername/chatbot-system.git
cd chatbot-system
```

2. **Create Feature Branch**:
```bash
git checkout -b feature/your-feature-name
```

3. **Develop with Tests**:
   - Write tests for new functionality
   - Ensure existing tests still pass
   - Add documentation for new features

4. **Quality Checks**:
```bash
# Format code
poetry run black chatbot/
poetry run isort chatbot/

# Run linting
poetry run flake8 chatbot/
poetry run mypy chatbot/

# Run tests
poetry run pytest tests/ --cov=chatbot
```

5. **Commit Changes**:
```bash
git add .
git commit -m "feat(component): add new feature"
```

6. **Submit Pull Request**:
   - Push to your fork
   - Create pull request with clear description
   - Include any relevant issue numbers

### Code Review Process

#### Self-Review Checklist
- [ ] Code follows project style guidelines
- [ ] All tests pass
- [ ] New functionality has tests
- [ ] Documentation is updated
- [ ] No sensitive information is committed
- [ ] Performance impact is considered

#### Review Criteria
- **Functionality**: Does the code work as intended?
- **Testing**: Are there adequate tests for the changes?
- **Documentation**: Is the code well-documented?
- **Style**: Does the code follow project conventions?
- **Performance**: Are there any performance implications?
- **Security**: Are there any security concerns?

## 🚀 Release Process

### Version Management

The project follows semantic versioning (SemVer):
- **MAJOR**: Breaking changes
- **MINOR**: New features, backwards compatible
- **PATCH**: Bug fixes

### Release Preparation

1. **Update Version**:
```bash
# Update version in pyproject.toml
poetry version patch  # or minor, major
```

2. **Update Changelog**:
```bash
# Update CHANGELOG.md with new version and changes
```

3. **Final Testing**:
```bash
# Run full test suite
poetry run pytest tests/ --cov=chatbot --cov-report=html

# Test build
poetry build
```

4. **Create Release**:
```bash
git tag v1.2.3
git push origin v1.2.3
```

### Deployment

#### Docker Deployment
```bash
# Build Docker image
docker build -t chatbot:latest .

# Deploy with docker-compose
docker-compose up -d
```

#### Direct Deployment
```bash
# Install in production environment
pip install -e .

# Run with systemd or supervisor
```

This development guide provides a comprehensive foundation for contributing to and maintaining the chatbot system. It emphasizes quality, testing, and maintainable code practices while providing practical guidance for common development scenarios.

## 🎯 Development Roadmap & Status

### ✅ Phase 1.0: Core Farcaster Integration (COMPLETE)
- **Status**: Verified and stable
- **Key Features**: Farcaster posting, replying, liking, following
- **Test Coverage**: Comprehensive test suite passing
- **Priority**: 0 (Critical foundation complete)

### ✅ Phase 1.1: Advanced Matrix Room Management (COMPLETE)
- **Status**: Implemented and verified ✅
- **Key Features**:
  - Pending Matrix invite tracking in world state
  - Channel status management (active, left_by_bot, kicked, banned, invited)
  - Comprehensive Matrix tools suite (join, leave, accept, react, get_invites)
  - Real-time event handling for invites, kicks, bans, and joins
  - AI integration with room management awareness
- **Test Coverage**: 57/57 Matrix-related tests passing
- **Demo**: Available at `demo_matrix_room_management.py`
- **Documentation**: See `PHASE_1_1_VERIFICATION.md`

### 🚧 Phase 1.2: Enhanced User Interaction (PLANNED)
- **Status**: Ready to begin
- **Key Features**:
  - Advanced message threading and context awareness
  - User preference learning and adaptation
  - Cross-platform conversation continuity
  - Enhanced reaction and response patterns

### 🚧 Phase 2.0: AI Intelligence Enhancement (PLANNED)
- **Status**: Planning phase
- **Key Features**:
  - Advanced context understanding
  - Proactive conversation management
  - Intelligent priority detection
  - Enhanced decision-making algorithms

### 📊 Current System Status
- **Farcaster Integration**: ✅ Stable and tested
- **Matrix Integration**: ✅ Advanced room management complete
- **Core Architecture**: ✅ Robust and extensible
- **Test Coverage**: ✅ Comprehensive test suites
- **Documentation**: ✅ Complete with examples and troubleshooting

### 🎉 Recent Achievements
- **June 1, 2025**: Phase 1.1 Advanced Matrix Room Management completed
- **May 2025**: Phase 1.0 Farcaster integration stabilized
- **Q1 2025**: Core architecture established

The system is now ready for Phase 1.2 development with solid foundations in both Farcaster and Matrix platforms.
