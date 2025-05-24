"""Tests for ManageSummarizationPromptTool."""

import pytest
import tempfile
import os
from unittest.mock import AsyncMock, patch
from available_tools.manage_summarization_prompt_tool import ManageSummarizationPromptTool
from tool_base import ToolResult
import database
import pytest_asyncio


@pytest.mark.unit
class TestManageSummarizationPromptTool:
    """Test ManageSummarizationPromptTool functionality."""

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
        """Create ManageSummarizationPromptTool instance."""
        return ManageSummarizationPromptTool()

    def test_get_definition(self, tool):
        """Test tool definition structure."""
        definition = tool.get_definition()
        
        assert definition["type"] == "function"
        assert definition["function"]["name"] == "manage_summarization_prompt"
        assert "description" in definition["function"]
        
        params = definition["function"]["parameters"]
        assert params["type"] == "object"
        assert "action" in params["properties"]
        assert "new_prompt_text" in params["properties"]
        
        # Check action enum
        assert params["properties"]["action"]["enum"] == ["get_current", "update"]
        
        # Check required fields
        assert params["required"] == ["action"]

    @pytest.mark.asyncio
    async def test_get_current_prompt_exists(self, tool, test_db_path):
        """Test getting current prompt when it exists."""
        # First set a prompt
        await database.update_prompt(test_db_path, "summarization_default", "Test summarization prompt")
        
        result = await tool.execute(
            room_id="!test:matrix.org",
            arguments={"action": "get_current"},
            tool_call_id="call_123",
            llm_provider_info={},
            conversation_history_snapshot=[],
            last_user_event_id="$event123",
            db_path=test_db_path
        )
        
        assert result.status == "success"
        assert "Current summarization prompt is: 'Test summarization prompt'" in result.result_for_llm_history

    @pytest.mark.asyncio
    async def test_get_current_prompt_not_exists(self, tool, test_db_path):
        """Test getting current prompt when it doesn't exist."""
        # Delete the default prompt that was created during database initialization
        async with database.aiosqlite.connect(test_db_path) as db:
            await db.execute("DELETE FROM prompts WHERE prompt_name = ?", ("summarization_default",))
            await db.commit()
        
        result = await tool.execute(
            room_id="!test:matrix.org",
            arguments={"action": "get_current"},
            tool_call_id="call_123",
            llm_provider_info={},
            conversation_history_snapshot=[],
            last_user_event_id="$event123",
            db_path=test_db_path
        )
        
        assert result.status == "success"
        assert "Summarization prompt 'summarization_default' not found" in result.result_for_llm_history

    @pytest.mark.asyncio
    async def test_update_prompt_success(self, tool, test_db_path):
        """Test successfully updating the prompt."""
        result = await tool.execute(
            room_id="!test:matrix.org",
            arguments={
                "action": "update",
                "new_prompt_text": "New summarization prompt text"
            },
            tool_call_id="call_123",
            llm_provider_info={},
            conversation_history_snapshot=[],
            last_user_event_id="$event123",
            db_path=test_db_path
        )
        
        assert result.status == "success"
        assert "Summarization prompt 'summarization_default' updated successfully" in result.result_for_llm_history
        
        # Verify the prompt was actually updated
        prompt_tuple = await database.get_prompt(test_db_path, "summarization_default")
        assert prompt_tuple is not None
        assert prompt_tuple[0] == "New summarization prompt text"

    @pytest.mark.asyncio
    async def test_update_prompt_missing_text(self, tool, test_db_path):
        """Test updating prompt without required new_prompt_text."""
        result = await tool.execute(
            room_id="!test:matrix.org",
            arguments={
                "action": "update"
                # Missing new_prompt_text
            },
            tool_call_id="call_123",
            llm_provider_info={},
            conversation_history_snapshot=[],
            last_user_event_id="$event123",
            db_path=test_db_path
        )
        
        assert result.status == "failure"
        assert "Missing 'new_prompt_text' argument" in result.result_for_llm_history
        assert "Missing required argument: new_prompt_text" in result.error_message

    @pytest.mark.asyncio
    async def test_update_prompt_empty_text(self, tool, test_db_path):
        """Test updating prompt with empty text."""
        result = await tool.execute(
            room_id="!test:matrix.org",
            arguments={
                "action": "update",
                "new_prompt_text": ""  # Empty text
            },
            tool_call_id="call_123",
            llm_provider_info={},
            conversation_history_snapshot=[],
            last_user_event_id="$event123",
            db_path=test_db_path
        )
        
        assert result.status == "failure"
        assert "Missing 'new_prompt_text' argument" in result.result_for_llm_history

    @pytest.mark.asyncio
    async def test_invalid_action(self, tool, test_db_path):
        """Test using an invalid action."""
        result = await tool.execute(
            room_id="!test:matrix.org",
            arguments={"action": "invalid_action"},
            tool_call_id="call_123",
            llm_provider_info={},
            conversation_history_snapshot=[],
            last_user_event_id="$event123",
            db_path=test_db_path
        )
        
        assert result.status == "failure"
        assert "Invalid action 'invalid_action'" in result.result_for_llm_history
        assert "Must be 'get_current' or 'update'" in result.result_for_llm_history

    @pytest.mark.asyncio
    async def test_missing_db_path(self, tool):
        """Test execution without db_path."""
        result = await tool.execute(
            room_id="!test:matrix.org",
            arguments={"action": "get_current"},
            tool_call_id="call_123",
            llm_provider_info={},
            conversation_history_snapshot=[],
            last_user_event_id="$event123",
            db_path=None  # Missing db_path
        )
        
        assert result.status == "failure"
        assert "Database path not configured" in result.result_for_llm_history

    @pytest.mark.asyncio
    async def test_invalid_arguments(self, tool, test_db_path):
        """Test with invalid arguments structure."""
        result = await tool.execute(
            room_id="!test:matrix.org",
            arguments={
                "invalid_field": "invalid_value"
                # Missing required action field
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
    async def test_database_exception_handling(self, tool, test_db_path):
        """Test handling of database exceptions."""
        with patch('database.get_prompt', side_effect=Exception("Database error")):
            result = await tool.execute(
                room_id="!test:matrix.org",
                arguments={"action": "get_current"},
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
    async def test_update_database_exception_handling(self, tool, test_db_path):
        """Test handling of database exceptions during update."""
        with patch('database.update_prompt', side_effect=Exception("Update failed")):
            result = await tool.execute(
                room_id="!test:matrix.org",
                arguments={
                    "action": "update",
                    "new_prompt_text": "New prompt"
                },
                tool_call_id="call_123",
                llm_provider_info={},
                conversation_history_snapshot=[],
                last_user_event_id="$event123",
                db_path=test_db_path
            )
        
        assert result.status == "failure"
        assert "failed due to an internal error" in result.result_for_llm_history
        assert "Update failed" in result.error_message