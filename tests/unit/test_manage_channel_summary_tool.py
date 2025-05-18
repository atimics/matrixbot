
import pytest
from unittest.mock import MagicMock, AsyncMock

from available_tools.manage_channel_summary_tool import ManageChannelSummaryTool
from tool_base import ToolResult, ToolParameter
from event_definitions import RequestAISummaryCommand, SendMatrixMessageCommand
from database import SummaryData

@pytest.fixture
def summary_tool_instance(mocker):
    # Mock the database dependency for this tool
    mock_db = MagicMock()
    # Patch the database module where ManageChannelSummaryTool will import it from
    mocker.patch('available_tools.manage_channel_summary_tool.database', mock_db)
    return ManageChannelSummaryTool(), mock_db

def test_manage_channel_summary_tool_get_definition(summary_tool_instance):
    tool, _ = summary_tool_instance
    definition = tool.get_definition()
    assert definition["name"] == "manage_channel_summary"
    assert "description" in definition
    assert len(definition["parameters"]) == 1
    param_names = [p.name for p in definition["parameters"]]
    assert "action" in param_names
    action_param = next(p for p in definition["parameters"] if p.name == "action")
    assert action_param.required is True
    assert action_param.type == "string"
    assert "request_update" in action_param.enum
    assert "get_current" in action_param.enum

@pytest.mark.asyncio
async def test_manage_channel_summary_tool_execute_request_update(summary_tool_instance):
    tool, mock_db = summary_tool_instance
    room_id = "!test_room:matrix.org"
    arguments = {"action": "request_update"}
    tool_call_id = "call_sum_update"

    result = await tool.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info=None,
        conversation_history_snapshot=[],
        last_user_event_id=None
    )

    assert result.status == "success"
    assert result.result_text == "AI summary update requested for this channel."
    assert len(result.commands_to_publish) == 1
    command = result.commands_to_publish[0]
    assert isinstance(command, RequestAISummaryCommand)
    assert command.room_id == room_id
    assert command.force_generation is True # Specific to this action

@pytest.mark.asyncio
async def test_manage_channel_summary_tool_execute_get_current_summary_exists(summary_tool_instance):
    tool, mock_db = summary_tool_instance
    room_id = "!test_room:matrix.org"
    arguments = {"action": "get_current"}
    tool_call_id = "call_sum_get_exists"
    summary_text = "This is the current summary."
    last_event_id = "$event_sum_id"
    mock_db.get_summary.return_value = SummaryData(summary_text=summary_text, last_event_id_summarized=last_event_id)

    result = await tool.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info=None,
        conversation_history_snapshot=[],
        last_user_event_id=None
    )

    mock_db.get_summary.assert_called_once_with(None, room_id) # DB path is None by default in tool
    assert result.status == "success"
    expected_text = f"Current summary (last updated for event {last_event_id}):\n{summary_text}"
    assert result.result_text == expected_text
    assert not result.commands_to_publish # Should not publish commands, only return text

@pytest.mark.asyncio
async def test_manage_channel_summary_tool_execute_get_current_no_summary(summary_tool_instance):
    tool, mock_db = summary_tool_instance
    room_id = "!test_room:matrix.org"
    arguments = {"action": "get_current"}
    tool_call_id = "call_sum_get_none"
    mock_db.get_summary.return_value = None

    result = await tool.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info=None,
        conversation_history_snapshot=[],
        last_user_event_id=None
    )

    mock_db.get_summary.assert_called_once_with(None, room_id)
    assert result.status == "success"
    assert result.result_text == "No summary is currently available for this channel."
    assert not result.commands_to_publish

@pytest.mark.asyncio
async def test_manage_channel_summary_tool_execute_invalid_action(summary_tool_instance):
    tool, _ = summary_tool_instance
    room_id = "!test_room:matrix.org"
    arguments = {"action": "delete_summary"} # Invalid action
    tool_call_id = "call_sum_invalid"

    result = await tool.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info=None,
        conversation_history_snapshot=[],
        last_user_event_id=None
    )

    assert result.status == "failure"
    assert "Invalid action specified: delete_summary" in result.error_message
    assert not result.commands_to_publish

@pytest.mark.asyncio
async def test_manage_channel_summary_tool_execute_missing_action(summary_tool_instance):
    tool, _ = summary_tool_instance
    room_id = "!test_room:matrix.org"
    arguments = {} # Missing 'action'
    tool_call_id = "call_sum_missing_arg"

    result = await tool.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info=None,
        conversation_history_snapshot=[],
        last_user_event_id=None
    )

    assert result.status == "failure"
    assert "Missing required argument: action" in result.error_message
    assert not result.commands_to_publish
