"""Test utilities and helper functions for the Matrix bot test suite."""

import asyncio
import tempfile
import sqlite3
from pathlib import Path
from typing import Dict, Any, List, Optional
from unittest.mock import AsyncMock, MagicMock
import pytest

from message_bus import MessageBus
from event_definitions import *
import database


class MockMessageBus:
    """Enhanced mock message bus for testing with subscription tracking."""
    
    def __init__(self):
        self.published_events: List[Any] = []
        self.subscriptions: Dict[str, List[callable]] = {}
        self.publish_calls: List[Dict[str, Any]] = []
    
    async def publish(self, event):
        """Mock publish that tracks all published events."""
        self.published_events.append(event)
        self.publish_calls.append({
            'event': event,
            'event_type': getattr(event, 'event_type', type(event).__name__)
        })
        
        # Simulate calling subscribed handlers
        event_type = getattr(event, 'event_type', type(event).__name__)
        if event_type in self.subscriptions:
            for handler in self.subscriptions[event_type]:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
    
    def subscribe(self, event_type: str, handler: callable):
        """Mock subscribe that tracks subscriptions."""
        if event_type not in self.subscriptions:
            self.subscriptions[event_type] = []
        self.subscriptions[event_type].append(handler)
    
    async def shutdown(self):
        """Mock shutdown."""
        pass
    
    def get_published_events_of_type(self, event_type: type) -> List[Any]:
        """Get all published events of a specific type."""
        return [event for event in self.published_events if isinstance(event, event_type)]
    
    def clear_events(self):
        """Clear all tracked events."""
        self.published_events.clear()
        self.publish_calls.clear()


class DatabaseTestHelper:
    """Helper for database operations in tests."""
    
    @staticmethod
    async def create_test_database() -> str:
        """Create a temporary test database and return its path."""
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        db_path = temp_file.name
        temp_file.close()
        
        await database.initialize_database(db_path)
        return db_path
    
    @staticmethod
    async def setup_test_data(db_path: str, room_id: str = "!test:matrix.example.com"):
        """Set up common test data in the database."""
        # Add default prompts
        if not await database.get_prompt(db_path, "system_default"):
            await database.update_prompt(db_path, "system_default", "You are a helpful assistant.")
        
        if not await database.get_prompt(db_path, "summarization_default"):
            await database.update_prompt(db_path, "summarization_default", "Summarize the conversation.")
        
        # Add a test channel summary
        await database.update_summary(db_path, room_id, "Test channel summary", "$test_event")
    
    @staticmethod
    def cleanup_database(db_path: str):
        """Clean up test database file."""
        try:
            Path(db_path).unlink(missing_ok=True)
        except Exception:
            pass


class MatrixClientMock:
    """Enhanced Matrix client mock for testing."""
    
    def __init__(self, user_id: str = "@testbot:matrix.example.com"):
        self.user_id = user_id
        self.logged_in = True
        self.device_id = "TEST_DEVICE"
        self.access_token = "test_token"
        
        # Mock methods
        self.room_send = AsyncMock()
        self.room_typing = AsyncMock()
        self.set_presence = AsyncMock()
        self.joined_members = AsyncMock()
        self.room_get_state_event = AsyncMock()
        self.get_profile = AsyncMock()
        self.whoami = AsyncMock()
        self.login = AsyncMock()
        self.sync_forever = AsyncMock()
        self.add_event_callback = MagicMock()
        
        # Setup default return values
        self.setup_default_responses()
    
    def setup_default_responses(self):
        """Setup default responses for common operations."""
        from nio import ProfileGetResponse, WhoamiResponse
        
        # Profile response
        profile_response = MagicMock(spec=ProfileGetResponse)
        profile_response.displayname = "TestBot"
        self.get_profile.return_value = profile_response
        
        # Whoami response
        whoami_response = MagicMock(spec=WhoamiResponse)
        whoami_response.user_id = self.user_id
        whoami_response.device_id = self.device_id
        self.whoami.return_value = whoami_response


class ServiceTestBase:
    """Base class for service testing with common setup."""
    
    def setup_method(self):
        """Setup method called before each test."""
        self.mock_bus = MockMessageBus()
        self.mock_client = MatrixClientMock()
        self.test_room_id = "!test:matrix.example.com"
        self.test_user_id = "@testuser:matrix.example.com"
    
    async def create_test_database(self) -> str:
        """Create and setup a test database."""
        db_path = await DatabaseTestHelper.create_test_database()
        await DatabaseTestHelper.setup_test_data(db_path, self.test_room_id)
        return db_path
    
    def assert_event_published(self, event_type: type, count: int = 1):
        """Assert that an event of the given type was published."""
        events = self.mock_bus.get_published_events_of_type(event_type)
        assert len(events) == count, f"Expected {count} {event_type.__name__} events, got {len(events)}"
        return events
    
    def assert_no_events_published(self):
        """Assert that no events were published."""
        assert len(self.mock_bus.published_events) == 0, f"Expected no events, but {len(self.mock_bus.published_events)} were published"


async def wait_for_condition(condition_func, timeout: float = 1.0, interval: float = 0.01):
    """Wait for a condition to become true within a timeout."""
    elapsed = 0
    while elapsed < timeout:
        if condition_func():
            return True
        await asyncio.sleep(interval)
        elapsed += interval
    return False


def create_mock_tool_registry(tool_names: List[str] = None) -> MagicMock:
    """Create a mock tool registry with specified tools."""
    if tool_names is None:
        tool_names = ["send_reply", "send_message", "react_to_message"]
    
    mock_registry = MagicMock()
    mock_registry.get_all_tool_definitions.return_value = [
        {
            "function": {
                "name": name,
                "description": f"Test tool {name}",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            }
        }
        for name in tool_names
    ]
    
    # Mock get_tool method
    def mock_get_tool(tool_name):
        if tool_name in tool_names:
            mock_tool = MagicMock()
            mock_tool.get_definition.return_value = {
                "function": {
                    "name": tool_name,
                    "description": f"Test tool {tool_name}"
                }
            }
            return mock_tool
        return None
    
    mock_registry.get_tool = mock_get_tool
    return mock_registry


class AsyncContextManager:
    """Helper for creating async context managers in tests."""
    
    def __init__(self, return_value=None):
        self.return_value = return_value
    
    async def __aenter__(self):
        return self.return_value
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


def create_sample_conversation_history(length: int = 5) -> List[Dict[str, Any]]:
    """Create sample conversation history for testing."""
    history = []
    for i in range(length):
        if i % 2 == 0:
            # User message
            history.append({
                "role": "user",
                "name": f"User{i//2+1}",
                "content": f"This is user message {i//2+1}",
                "event_id": f"$user_event_{i}:matrix.example.com",
                "timestamp": 1640995200.0 + i * 60
            })
        else:
            # Assistant message
            history.append({
                "role": "assistant",
                "name": "TestBot",
                "content": f"This is assistant response {i//2+1}",
                "timestamp": 1640995200.0 + i * 60
            })
    return history


# Pytest fixtures for common test data
@pytest.fixture
def enhanced_mock_bus():
    """Provide an enhanced mock message bus."""
    return MockMessageBus()


@pytest.fixture
def mock_matrix_client():
    """Provide a mock Matrix client."""
    return MatrixClientMock()


@pytest.fixture
async def test_database():
    """Provide a temporary test database."""
    db_path = await DatabaseTestHelper.create_test_database()
    await DatabaseTestHelper.setup_test_data(db_path)
    yield db_path
    DatabaseTestHelper.cleanup_database(db_path)


@pytest.fixture
def mock_tool_registry():
    """Provide a mock tool registry."""
    return create_mock_tool_registry()


@pytest.fixture
def sample_conversation():
    """Provide sample conversation history."""
    return create_sample_conversation_history()