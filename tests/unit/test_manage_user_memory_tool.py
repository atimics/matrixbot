"""Tests for ManageUserMemoryTool."""

import pytest
import tempfile
import os
from unittest.mock import AsyncMock, patch
from datetime import datetime
from available_tools.manage_user_memory_tool import ManageUserMemoryTool
from tool_base import ToolResult
import database
import pytest_asyncio


@pytest.mark.unit
class TestManageUserMemoryTool:
    """Test ManageUserMemoryTool functionality."""

    @pytest_asyncio.fixture
    async def test_db_path(self):
        """Create a temporary test database."""
        db_fd, db_path = tempfile.mkstemp(suffix='.db')
        os.close(db_fd)
        await database.initialize_database(db_path)
        yield db_path
        try:
            os.unlink(db_path)
        except OSError:
            pass

    @pytest.fixture
    def tool(self):
        """Create ManageUserMemoryTool instance."""
        return ManageUserMemoryTool()

    def test_get_definition(self, tool):
        """Test tool definition structure."""
        definition = tool.get_definition()
        
        assert definition["type"] == "function"
        assert definition["function"]["name"] == "manage_user_memory"
        assert "description" in definition["function"]
        
        params = definition["function"]["parameters"]
        assert params["type"] == "object"
        assert "action" in params["properties"]
        assert "user_id" in params["properties"]
        assert "memory_text" in params["properties"]
        assert "memory_id" in params["properties"]
        
        # Check action enum
        assert params["properties"]["action"]["enum"] == ["add", "get", "list", "delete"]
        
        # Check required fields
        assert params["required"] == ["action", "user_id"]

    @pytest.mark.asyncio
    async def test_add_memory_success(self, tool, test_db_path):
        """Test successfully adding a user memory."""
        result = await tool.execute(
            room_id="!test:matrix.org",
            arguments={
                "action": "add",
                "user_id": "@testuser:matrix.org",
                "memory_text": "User prefers technical discussions"
            },
            tool_call_id="call_123",
            llm_provider_info={},
            conversation_history_snapshot=[],
            last_user_event_id="$event123",
            db_path=test_db_path
        )
        
        assert result.status == "success"
        assert "Memory added for user '@testuser:matrix.org'" in result.result_for_llm_history
        assert result.state_updates is not None
        assert "manage_user_memory.last_action" in result.state_updates

    @pytest.mark.asyncio
    async def test_add_memory_missing_text(self, tool, test_db_path):
        """Test adding memory without required memory_text."""
        result = await tool.execute(
            room_id="!test:matrix.org",
            arguments={
                "action": "add",
                "user_id": "@testuser:matrix.org"
                # Missing memory_text
            },
            tool_call_id="call_123",
            llm_provider_info={},
            conversation_history_snapshot=[],
            last_user_event_id="$event123",
            db_path=test_db_path
        )
        
        assert result.status == "failure"
        assert "Missing 'memory_text' argument" in result.result_for_llm_history
        assert "Missing required argument: memory_text" in result.error_message

    @pytest.mark.asyncio
    async def test_get_memories_with_data(self, tool, test_db_path):
        """Test getting memories when data exists."""
        # First add some memories
        await database.add_user_memory(test_db_path, "@testuser:matrix.org", "Likes Python")
        await database.add_user_memory(test_db_path, "@testuser:matrix.org", "Prefers async code")
        
        result = await tool.execute(
            room_id="!test:matrix.org",
            arguments={
                "action": "get",
                "user_id": "@testuser:matrix.org"
            },
            tool_call_id="call_123",
            llm_provider_info={},
            conversation_history_snapshot=[],
            last_user_event_id="$event123",
            db_path=test_db_path
        )
        
        assert result.status == "success"
        assert "Memories for user '@testuser:matrix.org'" in result.result_for_llm_history
        assert "Likes Python" in result.result_for_llm_history
        assert "Prefers async code" in result.result_for_llm_history

    @pytest.mark.asyncio
    async def test_list_memories_with_data(self, tool, test_db_path):
        """Test listing memories (same as get)."""
        # Add a memory
        await database.add_user_memory(test_db_path, "@testuser:matrix.org", "Test memory")
        
        result = await tool.execute(
            room_id="!test:matrix.org",
            arguments={
                "action": "list",
                "user_id": "@testuser:matrix.org"
            },
            tool_call_id="call_123",
            llm_provider_info={},
            conversation_history_snapshot=[],
            last_user_event_id="$event123",
            db_path=test_db_path
        )
        
        assert result.status == "success"
        assert "Memories for user '@testuser:matrix.org'" in result.result_for_llm_history
        assert "Test memory" in result.result_for_llm_history

    @pytest.mark.asyncio
    async def test_get_memories_no_data(self, tool, test_db_path):
        """Test getting memories when no data exists."""
        result = await tool.execute(
            room_id="!test:matrix.org",
            arguments={
                "action": "get",
                "user_id": "@newuser:matrix.org"
            },
            tool_call_id="call_123",
            llm_provider_info={},
            conversation_history_snapshot=[],
            last_user_event_id="$event123",
            db_path=test_db_path
        )
        
        assert result.status == "success"
        assert "No memories found for user '@newuser:matrix.org'" in result.result_for_llm_history

    @pytest.mark.asyncio
    async def test_delete_memory_success(self, tool, test_db_path):
        """Test successfully deleting a memory."""
        # Add a memory first
        await database.add_user_memory(test_db_path, "@testuser:matrix.org", "Memory to delete")
        
        # Get the memory ID
        memories = await database.get_user_memories(test_db_path, "@testuser:matrix.org")
        memory_id = memories[0][0]  # First memory's ID
        
        result = await tool.execute(
            room_id="!test:matrix.org",
            arguments={
                "action": "delete",
                "user_id": "@testuser:matrix.org",
                "memory_id": memory_id
            },
            tool_call_id="call_123",
            llm_provider_info={},
            conversation_history_snapshot=[],
            last_user_event_id="$event123",
            db_path=test_db_path
        )
        
        assert result.status == "success"
        assert f"Memory with ID '{memory_id}' deleted" in result.result_for_llm_history
        assert result.state_updates is not None

    @pytest.mark.asyncio
    async def test_delete_memory_missing_id(self, tool, test_db_path):
        """Test deleting memory without required memory_id."""
        result = await tool.execute(
            room_id="!test:matrix.org",
            arguments={
                "action": "delete",
                "user_id": "@testuser:matrix.org"
                # Missing memory_id
            },
            tool_call_id="call_123",
            llm_provider_info={},
            conversation_history_snapshot=[],
            last_user_event_id="$event123",
            db_path=test_db_path
        )
        
        assert result.status == "failure"
        assert "Missing 'memory_id' argument" in result.result_for_llm_history
        assert "Missing required argument: memory_id" in result.error_message

    @pytest.mark.asyncio
    async def test_invalid_action(self, tool, test_db_path):
        """Test using an invalid action."""
        result = await tool.execute(
            room_id="!test:matrix.org",
            arguments={
                "action": "invalid_action",
                "user_id": "@testuser:matrix.org"
            },
            tool_call_id="call_123",
            llm_provider_info={},
            conversation_history_snapshot=[],
            last_user_event_id="$event123",
            db_path=test_db_path
        )
        
        assert result.status == "failure"
        assert "Invalid action 'invalid_action'" in result.result_for_llm_history
        assert "Must be 'add', 'get', 'list', or 'delete'" in result.result_for_llm_history

    @pytest.mark.asyncio
    async def test_missing_user_id(self, tool, test_db_path):
        """Test execution without user_id."""
        result = await tool.execute(
            room_id="!test:matrix.org",
            arguments={
                "action": "get"
                # Missing user_id
            },
            tool_call_id="call_123",
            llm_provider_info={},
            conversation_history_snapshot=[],
            last_user_event_id="$event123",
            db_path=test_db_path
        )
        
        assert result.status == "failure"
        assert "Invalid arguments" in result.result_for_llm_history

    @pytest.mark.asyncio
    async def test_missing_db_path(self, tool):
        """Test execution without db_path."""
        result = await tool.execute(
            room_id="!test:matrix.org",
            arguments={
                "action": "get",
                "user_id": "@testuser:matrix.org"
            },
            tool_call_id="call_123",
            llm_provider_info={},
            conversation_history_snapshot=[],
            last_user_event_id="$event123",
            db_path=None  # Missing db_path
        )
        
        assert result.status == "failure"
        assert "Database path not configured" in result.result_for_llm_history

    @pytest.mark.asyncio
    async def test_empty_user_id(self, tool, test_db_path):
        """Test execution with empty user_id."""
        result = await tool.execute(
            room_id="!test:matrix.org",
            arguments={
                "action": "get",
                "user_id": ""  # Empty user_id
            },
            tool_call_id="call_123",
            llm_provider_info={},
            conversation_history_snapshot=[],
            last_user_event_id="$event123",
            db_path=test_db_path
        )
        
        assert result.status == "failure"
        assert "Missing required argument 'user_id'" in result.result_for_llm_history

    @pytest.mark.asyncio
    async def test_database_exception_handling(self, tool, test_db_path):
        """Test handling of database exceptions."""
        with patch('database.add_user_memory', side_effect=Exception("Database error")):
            result = await tool.execute(
                room_id="!test:matrix.org",
                arguments={
                    "action": "add",
                    "user_id": "@testuser:matrix.org",
                    "memory_text": "Test memory"
                },
                tool_call_id="call_123",
                llm_provider_info={},
                conversation_history_snapshot=[],
                last_user_event_id="$event123",
                db_path=test_db_path
            )
        
        assert result.status == "failure"
        assert "failed due to an internal error" in result.result_for_llm_history
        assert "Database error" in result.error_message

    @pytest.mark.asyncio
    async def test_invalid_arguments(self, tool, test_db_path):
        """Test with completely invalid arguments structure."""
        result = await tool.execute(
            room_id="!test:matrix.org",
            arguments={
                "invalid_field": "invalid_value"
                # Missing required fields
            },
            tool_call_id="call_123",
            llm_provider_info={},
            conversation_history_snapshot=[],
            last_user_event_id="$event123",
            db_path=test_db_path
        )
        
        assert result.status == "failure"
        assert "Invalid arguments" in result.result_for_llm_history