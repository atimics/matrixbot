"""
Comprehensive Test Configuration

This module provides enhanced testing utilities, fixtures, and configuration
for the chatbot system, implementing the recommendations from the engineering report.
"""

import asyncio
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import AsyncGenerator, Dict, Generator, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

from chatbot.config import AppConfig
from chatbot.core.context import ContextManager
from chatbot.core.history_recorder import HistoryRecorder
from chatbot.core.integration_manager import IntegrationManager
from chatbot.core.orchestration import MainOrchestrator
from chatbot.core.services import ServiceRegistry
from chatbot.core.world_state import WorldStateManager
from chatbot.tools.base import ActionContext
from chatbot.tools.registry import ToolRegistry

# Configure test logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def test_config(temp_dir: Path) -> AppConfig:
    """Provide a test configuration with temporary paths."""
    return AppConfig(
        CHATBOT_DB_PATH=str(temp_dir / "test_chatbot.db"),
        LOG_LEVEL="DEBUG",
        AI_MODEL="test/model",
        OPENROUTER_API_KEY="sk-test-key",
        MATRIX_HOMESERVER="https://test.matrix.org",
        MATRIX_USER_ID="@test:matrix.org",
        MATRIX_PASSWORD="test_password",
        MATRIX_ROOM_ID="!test:matrix.org",
        OBSERVATION_INTERVAL=0.1,  # Fast for tests
        MAX_CYCLES_PER_HOUR=3600,  # High limit for tests
    )


@pytest.fixture
def world_state_manager() -> WorldStateManager:
    """Provide a clean WorldStateManager instance for testing."""
    return WorldStateManager()


@pytest_asyncio.fixture
async def context_manager(temp_dir: Path) -> AsyncGenerator[ContextManager, None]:
    """Provide a ContextManager with temporary database."""
    db_path = temp_dir / "test_context.db"
    world_state = WorldStateManager()
    context_mgr = ContextManager(world_state, str(db_path))
    
    # Initialize the database
    await context_mgr.history_recorder.initialize()
    
    try:
        yield context_mgr
    finally:
        await context_mgr.cleanup()


@pytest_asyncio.fixture
async def integration_manager(temp_dir: Path) -> AsyncGenerator[IntegrationManager, None]:
    """Provide an IntegrationManager with temporary database."""
    db_path = temp_dir / "test_integrations.db"
    integration_mgr = IntegrationManager(str(db_path))
    
    await integration_mgr.initialize()
    
    try:
        yield integration_mgr
    finally:
        await integration_mgr.cleanup()


@pytest.fixture
def service_registry() -> ServiceRegistry:
    """Provide a clean ServiceRegistry instance."""
    return ServiceRegistry()


@pytest.fixture
def tool_registry() -> ToolRegistry:
    """Provide a clean ToolRegistry instance."""
    return ToolRegistry()


@pytest.fixture
def mock_action_context(
    service_registry: ServiceRegistry,
    world_state_manager: WorldStateManager
) -> ActionContext:
    """Provide a mock ActionContext for tool testing."""
    return ActionContext(
        service_registry=service_registry,
        world_state_manager=world_state_manager,
        context_manager=AsyncMock(),
        arweave_client=AsyncMock(),
        arweave_service=AsyncMock(),
        base_nft_service=AsyncMock(),
        eligibility_service=AsyncMock(),
        current_channel_id="test_channel"
    )


@pytest_asyncio.fixture
async def orchestrator(
    test_config: AppConfig,
    temp_dir: Path
) -> AsyncGenerator[MainOrchestrator, None]:
    """Provide a MainOrchestrator instance for integration testing."""
    # Override config for testing
    import chatbot.config
    original_settings = chatbot.config.settings
    chatbot.config.settings = test_config
    
    try:
        orchestrator = MainOrchestrator()
        await orchestrator.initialize()
        yield orchestrator
    finally:
        if hasattr(orchestrator, 'cleanup'):
            await orchestrator.cleanup()
        # Restore original settings
        chatbot.config.settings = original_settings


@pytest.fixture
def api_client(orchestrator: MainOrchestrator) -> TestClient:
    """Provide a FastAPI test client."""
    from chatbot.api_server import create_secure_api_server
    app = create_secure_api_server(orchestrator)
    return TestClient(app)


# Mock classes for external services
class MockMatrixObserver:
    """Mock Matrix observer for testing."""
    
    def __init__(self):
        self.connected = False
        self.messages = []
        
    async def connect(self):
        self.connected = True
        
    async def disconnect(self):
        self.connected = False
        
    async def send_message(self, room_id: str, message: str):
        self.messages.append({"room_id": room_id, "message": message})
        
    def get_recent_messages(self, room_id: str, limit: int = 10):
        return [m for m in self.messages if m["room_id"] == room_id][-limit:]


class MockFarcasterObserver:
    """Mock Farcaster observer for testing."""
    
    def __init__(self):
        self.connected = False
        self.casts = []
        
    async def connect(self):
        self.connected = True
        
    async def disconnect(self):
        self.connected = False
        
    async def publish_cast(self, text: str, parent_cast_hash: Optional[str] = None):
        cast = {"text": text, "parent": parent_cast_hash, "hash": f"test_hash_{len(self.casts)}"}
        self.casts.append(cast)
        return cast


@pytest.fixture
def mock_matrix_observer() -> MockMatrixObserver:
    """Provide a mock Matrix observer."""
    return MockMatrixObserver()


@pytest.fixture
def mock_farcaster_observer() -> MockFarcasterObserver:
    """Provide a mock Farcaster observer."""
    return MockFarcasterObserver()


# Test categories and markers
def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests - fast, isolated component tests"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests - test component interactions"
    )
    config.addinivalue_line(
        "markers", "service: Service tests - test external service interactions"
    )
    config.addinivalue_line(
        "markers", "slow: Slow tests - tests taking more than 1 second"
    )
    config.addinivalue_line(
        "markers", "database: Tests requiring database operations"
    )
    config.addinivalue_line(
        "markers", "network: Tests requiring network access"
    )
    config.addinivalue_line(
        "markers", "api: API endpoint tests"
    )
    config.addinivalue_line(
        "markers", "security: Security-focused tests"
    )


# Async test utilities
@pytest.fixture
def anyio_backend():
    """Use asyncio backend for anyio tests."""
    return "asyncio"


# Test data factories
class TestDataFactory:
    """Factory for generating test data."""
    
    @staticmethod
    def create_test_message(
        content: str = "Test message",
        sender: str = "@test:matrix.org",
        channel_id: str = "test_channel",
        platform: str = "matrix"
    ) -> Dict:
        """Create a test message."""
        return {
            "content": content,
            "sender": sender,
            "channel_id": channel_id,
            "platform": platform,
            "timestamp": time.time(),
            "message_id": f"test_msg_{hash(content)}"
        }
    
    @staticmethod
    def create_test_channel(
        channel_id: str = "test_channel",
        name: str = "Test Channel",
        platform: str = "matrix"
    ) -> Dict:
        """Create a test channel."""
        return {
            "id": channel_id,
            "name": name,
            "type": platform,
            "recent_messages": [],
            "last_checked": time.time()
        }


@pytest.fixture
def test_data_factory() -> TestDataFactory:
    """Provide the test data factory."""
    return TestDataFactory()


# Environment setup
@pytest.fixture(autouse=True)
def setup_test_environment(monkeypatch):
    """Set up test environment variables."""
    test_env = {
        "TESTING": "true",
        "LOG_LEVEL": "DEBUG",
        "AI_MODEL": "test/model",
        "OPENROUTER_API_KEY": "sk-test-key",
        "MATRIX_HOMESERVER": "https://test.matrix.org",
        "MATRIX_USER_ID": "@test:matrix.org",
        "MATRIX_PASSWORD": "test_password",
        "MATRIX_ROOM_ID": "!test:matrix.org",
    }
    
    for key, value in test_env.items():
        monkeypatch.setenv(key, value)
