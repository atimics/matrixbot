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
    assert definition["function"]["name"] == "manage_channel_summary"
    assert "description" in definition["function"]
    # Parameters are now under function.parameters.properties
    assert "action" in definition["function"]["parameters"]["properties"]
    action_param_details = definition["function"]["parameters"]["properties"]["action"]
    # Ensure 'required' is checked correctly at the top level of parameters
    assert "action" in definition["function"]["parameters"]["required"]
    assert action_param_details["type"] == "string"
    assert "request_update" in action_param_details["enum"]
    assert "get_current" in action_param_details["enum"]

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
        llm_provider_info=None, # Added missing llm_provider_info
        conversation_history_snapshot=[], # Added missing conversation_history_snapshot
        last_user_event_id=None, # Added missing last_user_event_id
        db_path="dummy_db.sqlite"
    )

    assert result.status == "success"
    assert result.result_for_llm_history == "AI summary update requested for this channel." # Updated expected message
    assert len(result.commands_to_publish) == 1
    command = result.commands_to_publish[0]
    assert isinstance(command, RequestAISummaryCommand)
    assert command.room_id == room_id
    assert command.force_update is True # Updated from force_generation to force_update

@pytest.mark.asyncio
async def test_manage_channel_summary_tool_execute_get_current_summary_exists(summary_tool_instance):
    tool, mock_db = summary_tool_instance
    room_id = "!test_room:matrix.org"
    arguments = {"action": "get_current"}
    tool_call_id = "call_sum_get_exists"
    summary_text = "This is the current summary."
    last_event_id = "$event_sum_id"
    # Ensure the mock returns a tuple (summary_text, last_event_id_summarized) as per database.get_summary
    mock_db.get_summary.return_value = (summary_text, last_event_id)

    result = await tool.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info=None, # Added
        conversation_history_snapshot=[], # Added
        last_user_event_id=None, # Added
        db_path="dummy_db.sqlite"
    )

    mock_db.get_summary.assert_called_once_with("dummy_db.sqlite", room_id)
    assert result.status == "success"
    # Updated expected message to match tool's new output format
    expected_text = f"Current summary (last updated for event {last_event_id}):\\n{summary_text}"
    assert result.result_for_llm_history == expected_text
    assert not result.commands_to_publish

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
        llm_provider_info=None, # Added
        conversation_history_snapshot=[], # Added
        last_user_event_id=None, # Added
        db_path="dummy_db.sqlite"
    )

    mock_db.get_summary.assert_called_once_with("dummy_db.sqlite", room_id)
    assert result.status == "success"
    assert result.result_for_llm_history == "No summary is currently available for this channel." # Updated
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
        llm_provider_info=None, # Added
        conversation_history_snapshot=[], # Added
        last_user_event_id=None, # Added
        db_path="dummy_db.sqlite"
    )

    assert result.status == "failure"
    # The tool returns a more specific message now, but the test checks for inclusion.
    assert "Invalid action specified: delete_summary" in result.error_message
    assert result.result_for_llm_history == "[Tool manage_channel_summary failed: Invalid action 'delete_summary']" # Check new llm history message
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
        llm_provider_info=None, # Added
        conversation_history_snapshot=[], # Added
        last_user_event_id=None, # Added
        db_path="dummy_db.sqlite"
    )

    assert result.status == "failure"
    assert "Missing required argument: action" in result.error_message # Updated expected error message
    assert result.result_for_llm_history == "[Tool manage_channel_summary failed: Missing required argument 'action']" # Check new llm history message
    assert not result.commands_to_publish
