"""Test configuration and fixtures."""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from chatbot.core.world_state import WorldStateManager
from chatbot.core.context import ContextManager
from chatbot.core.orchestrator import ContextAwareOrchestrator, OrchestratorConfig


@pytest.fixture
def temp_db_path():
    """Provide a temporary database path for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        yield f.name
    try:
        os.unlink(f.name)
    except FileNotFoundError:
        pass


@pytest.fixture
def world_state():
    """Provide a clean WorldStateManager instance."""
    return WorldStateManager()


@pytest.fixture
def context_manager(world_state, temp_db_path):
    """Provide a ContextManager instance with temporary database."""
    return ContextManager(world_state, temp_db_path)


@pytest.fixture
def orchestrator_config(temp_db_path):
    """Provide test configuration for orchestrator."""
    return OrchestratorConfig(
        db_path=temp_db_path,
        observation_interval=1.0,  # Fast for testing
        max_cycles_per_hour=3600,  # High limit for testing
        ai_model="test-model"
    )


@pytest.fixture
def mock_ai_engine():
    """Provide a mocked AI engine."""
    mock = AsyncMock()
    mock.make_decision.return_value = None  # Default: no decision
    return mock


@pytest.fixture
def mock_matrix_observer():
    """Provide a mocked Matrix observer."""
    mock = AsyncMock()
    mock.start = AsyncMock()
    mock.stop = AsyncMock()
    mock.add_channel = MagicMock()
    return mock


@pytest.fixture
def mock_farcaster_observer():
    """Provide a mocked Farcaster observer."""
    mock = AsyncMock()
    mock.start = AsyncMock()
    mock.stop = AsyncMock()
    return mock


@pytest.fixture
def sample_message():
    """Provide a sample message for testing."""
    return {
        "content": "Hello, world!",
        "sender": "test_user",
        "event_id": "test_event_123",
        "timestamp": 1640995200.0,  # 2022-01-01 00:00:00 UTC
        "room_id": "!test:example.com"
    }


@pytest.fixture
def sample_world_state():
    """Provide a sample world state for testing."""
    return {
        "channels": {
            "!test:example.com": {
                "id": "!test:example.com",
                "type": "matrix",
                "name": "Test Room",
                "recent_messages": [],
                "last_checked": 1640995200.0
            }
        },
        "action_history": [],
        "system_status": {
            "matrix_connected": True,
            "farcaster_connected": False,
            "last_observation_cycle": 0,
            "total_cycles": 0
        },
        "last_update": 1640995200.0
    }
