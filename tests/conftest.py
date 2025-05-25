import sys
import os
import pytest
import asyncio
from unittest.mock import MagicMock
from faker import Faker

# Add the project root to sys.path so tests can import project modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Global faker instance for consistent test data
fake = Faker()

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture
def mock_message_bus():
    """Provide a mock message bus for testing."""
    mock_bus = MagicMock()
    mock_bus.publish = MagicMock()
    mock_bus.subscribe = MagicMock()
    mock_bus.shutdown = MagicMock()
    return mock_bus

@pytest.fixture
def sample_room_id():
    """Provide a consistent test room ID."""
    return "!testroom:matrix.example.com"

@pytest.fixture
def sample_user_id():
    """Provide a consistent test user ID."""
    return "@testuser:matrix.example.com"

@pytest.fixture
def sample_event_id():
    """Provide a consistent test event ID."""
    return "$testevent123:matrix.example.com"

@pytest.fixture
def sample_matrix_event():
    """Provide a sample Matrix event for testing."""
    return {
        "event_id": "$testevent123:matrix.example.com",
        "sender": "@testuser:matrix.example.com",
        "room_id": "!testroom:matrix.example.com",
        "type": "m.room.message",
        "content": {
            "msgtype": "m.text",
            "body": "Hello, world!"
        },
        "origin_server_ts": 1640995200000
    }

@pytest.fixture
async def clean_database(tmp_path):
    """Provide a clean test database."""
    from database import initialize_database
    db_file = tmp_path / "test_clean.db"
    await initialize_database(str(db_file))
    return str(db_file)

@pytest.fixture
def example_fixture():
    return "example"