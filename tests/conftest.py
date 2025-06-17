"""
Global test configuration and fixtures.
"""

import asyncio
import logging  # Add this
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import AsyncGenerator, Generator
import pytest
import pytest_asyncio  # Import this
from unittest.mock import AsyncMock, MagicMock

from chatbot.config import AppConfig
from chatbot.core.context import ContextManager
from chatbot.core.history_recorder import HistoryRecorder
from chatbot.core.world_state import WorldStateManager
from chatbot.tools.base import ActionContext
from chatbot.tools.media_generation_tools import GenerateImageTool


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Provide a temporary directory for test files."""
    temp_path = Path(tempfile.mkdtemp())
    try:
        yield temp_path
    finally:
        shutil.rmtree(temp_path, ignore_errors=True)


@pytest.fixture
def world_state_manager() -> WorldStateManager:
    """Provide a clean WorldStateManager instance for testing."""
    return WorldStateManager()


@pytest.fixture
async def context_manager(temp_dir: Path) -> AsyncGenerator[ContextManager, None]:
    """Provide a ContextManager with temporary database."""
    world_state = WorldStateManager()
    db_path = temp_dir / "test_context.db"

    context_mgr = ContextManager(world_state, str(db_path))
    await context_mgr.initialize()

    try:
        yield context_mgr
    finally:
        await context_mgr.cleanup()


@pytest_asyncio.fixture  # Changed from @pytest.fixture
async def history_recorder(tmp_path):
    """Provides an initialized HistoryRecorder instance for async tests."""
    logging.info(f"[Fixture history_recorder] STARTING. tmp_path: {tmp_path}")
    db_path = tmp_path / "test_chat.db"
    recorder = HistoryRecorder(db_path=str(db_path))
    logging.info(f"[Fixture history_recorder] HistoryRecorder instance created: {recorder}")

    # Ensure initialize is awaited and check its type
    init_coro = recorder.initialize()
    logging.info(f"[Fixture history_recorder] recorder.initialize() called, type of result: {type(init_coro)}")
    if not asyncio.iscoroutine(init_coro):
        logging.error(f"[Fixture history_recorder] Expected coroutine, got {type(init_coro)}")
        raise TypeError(f"recorder.initialize() should return a coroutine, got {type(init_coro)}")
    else:
        logging.info("[Fixture history_recorder] Awaiting initialization...")
        await init_coro
        logging.info("[Fixture history_recorder] Initialization complete")

    yield recorder

    # Cleanup
    logging.info("[Fixture history_recorder] CLEANUP starting...")
    try:
        cleanup_coro = recorder.cleanup()
        if asyncio.iscoroutine(cleanup_coro):
            await cleanup_coro
        logging.info("[Fixture history_recorder] Cleanup complete")
    except Exception as e:
        logging.error(f"[Fixture history_recorder] Cleanup error: {e}")


@pytest.fixture
def mock_matrix_observer() -> AsyncMock:
    """Provide a mocked Matrix observer with common return values."""
    observer = AsyncMock()

    # Configure common successful responses
    observer.send_message.return_value = {
        "success": True,
        "event_id": "test_event_123",
        "room_id": "!test:matrix.org"
    }

    observer.send_reply.return_value = {
        "success": True,
        "event_id": "test_reply_123",
        "reply_to_event_id": "original_event",
        "sent_content": "Test reply"
    }

    observer.join_room.return_value = {
        "success": True,
        "room_id": "!test:matrix.org"
    }

    observer.leave_room.return_value = {
        "success": True,
        "room_id": "!test:matrix.org"
    }

    observer.is_connected = True
    return observer


@pytest.fixture
def mock_farcaster_observer() -> AsyncMock:
    """Provide a mocked Farcaster observer with common return values."""
    observer = AsyncMock()

    # Configure common successful responses
    observer.post_cast.return_value = {
        "success": True,
        "cast_hash": "0xtest123",
        "sent_content": "Test cast"
    }

    observer.reply_to_cast.return_value = {
        "success": True,
        "cast_hash": "0xreply123",
        "sent_content": "Test reply"
    }

    observer.get_user_timeline.return_value = {
        "success": True,
        "casts": [],
        "error": None
    }

    return observer


@pytest.fixture
def mock_service_registry():
    """Provide a mock service registry for testing."""
    registry = MagicMock()
    
    # Mock Matrix service
    matrix_service = AsyncMock()
    matrix_service.is_available.return_value = True
    matrix_service.send_message.return_value = {"status": "success"}
    registry.get_matrix_service.return_value = matrix_service
    
    # Mock Farcaster service
    farcaster_service = AsyncMock()
    farcaster_service.is_available.return_value = True
    farcaster_service.create_post.return_value = {"status": "success"}
    registry.get_social_service.return_value = farcaster_service
    
    return registry


@pytest.fixture
def mock_action_context(
    world_state_manager: WorldStateManager,
    mock_matrix_observer: AsyncMock,
    mock_farcaster_observer: AsyncMock,
    mock_service_registry
) -> ActionContext:
    """Provide a fully mocked ActionContext for tool testing."""
    return ActionContext(
        world_state_manager=world_state_manager,
        matrix_observer=mock_matrix_observer,
        farcaster_observer=mock_farcaster_observer,
        context_manager=None,
        service_registry=mock_service_registry
    )


@pytest.fixture
def sample_message() -> dict:
    """Provide a sample message structure for testing."""
    import time
    return {
        "id": "msg_123",
        "content": "Test message content",
        "sender": "@user:example.com",
        "timestamp": time.time(),
        "channel_id": "test_channel"
    }


@pytest.fixture
def sample_cast_data() -> dict:
    """Provide sample Farcaster cast data for testing."""
    import time
    return {
        "id": "cast123",
        "content": "This is a test cast",
        "user": {
            "fid": 123,
            "username": "testuser",
            "display_name": "Test User"
        },
        "timestamp": int(time.time()),
        "hash": "0xabcdef123456",
        "reactions": {"likes": 5, "recasts": 2},
        "replies": 0
    }


@pytest.fixture
def app_config() -> AppConfig:
    """Provide test application configuration."""
    config = AppConfig()
    # Override with test values
    config.db_path = ":memory:"
    config.log_level = "DEBUG"
    return config


@pytest.fixture
def generate_image_tool(mock_action_context: ActionContext) -> GenerateImageTool:
    """Provide a GenerateImageTool instance with mocked dependencies."""
    tool = GenerateImageTool()
    # If the tool has an init or setup method that needs action_context,
    # it should be called here. For now, we assume it's not strictly needed
    # for instantiation for this test's purpose or it's handled internally.
    # If direct injection is needed: tool.action_context = mock_action_context
    return tool


# Test categories for easier test selection
pytest_plugins = ["pytest_asyncio"]


def pytest_configure(config):
    """Configure pytest markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests - fast, isolated tests"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests - test component interactions"
    )
    config.addinivalue_line(
        "markers", "service: Service tests - test external service interactions"
    )
    config.addinivalue_line(
        "markers", "slow: Slow tests - tests that take more than 1 second"
    )
    config.addinivalue_line(
        "markers", "database: Tests requiring database operations"
    )
    config.addinivalue_line(
        "markers", "network: Tests requiring network access"
    )
    config.addinivalue_line(
        "markers", "error_handling: Tests focused on error conditions"
    )


# Async test utilities
@pytest.fixture
def anyio_backend():
    """Use asyncio backend for anyio tests."""
    return "asyncio"
