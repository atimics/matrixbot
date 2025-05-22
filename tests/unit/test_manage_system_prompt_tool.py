import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from available_tools.manage_system_prompt_tool import ManageSystemPromptTool
from tool_base import ToolResult
import database # So we can mock its functions

@pytest.fixture
def manage_system_prompt_tool_instance():
    return ManageSystemPromptTool()

def test_manage_system_prompt_tool_get_definition(manage_system_prompt_tool_instance: ManageSystemPromptTool):
    definition = manage_system_prompt_tool_instance.get_definition()
    assert definition["function"]["name"] == "manage_system_prompt"
    assert "description" in definition["function"]
    assert "action" in definition["function"]["parameters"]["properties"]
    assert "new_prompt_text" in definition["function"]["parameters"]["properties"]
    assert "action" in definition["function"]["parameters"]["required"]

@pytest.mark.asyncio
@patch('available_tools.manage_system_prompt_tool.database', new_callable=MagicMock) # Mock database module used by the tool
async def test_manage_system_prompt_tool_get_current_success(mock_db, manage_system_prompt_tool_instance: ManageSystemPromptTool):
    mock_db.get_prompt = MagicMock(return_value=("Current system prompt", None)) # Simulate DB returning a prompt
    room_id = "!test_room:matrix.org"
    arguments = {"action": "get_current"}
    db_path_param = "dummy_db_path.db"

    result = await manage_system_prompt_tool_instance.execute(
        room_id=room_id, arguments=arguments, tool_call_id="t1", 
        llm_provider_info={}, conversation_history_snapshot=[], last_user_event_id=None, db_path=db_path_param
    )

    assert result.status == "success" # Corrected assertion
    assert "Current system prompt is: 'Current system prompt'" in result.result_for_llm_history
    mock_db.get_prompt.assert_called_once_with(db_path_param, "system_default")
    assert not result.commands_to_publish

@pytest.mark.asyncio
@patch('available_tools.manage_system_prompt_tool.database', new_callable=MagicMock)
async def test_manage_system_prompt_tool_get_current_not_found(mock_db, manage_system_prompt_tool_instance: ManageSystemPromptTool):
    mock_db.get_prompt = MagicMock(return_value=(None, None)) # Simulate DB returning no prompt
    arguments = {"action": "get_current"}
    db_path_param = "dummy_db_path.db"

    result = await manage_system_prompt_tool_instance.execute(
        room_id="!r:h", arguments=arguments, tool_call_id="t2", 
        llm_provider_info={}, conversation_history_snapshot=[], last_user_event_id=None, db_path=db_path_param
    )

    assert result.status == "success" # Corrected assertion: Still success, but indicates not found
    assert "System prompt 'system_default' not found." in result.result_for_llm_history
    mock_db.get_prompt.assert_called_once_with(db_path_param, "system_default")

@pytest.mark.asyncio
@patch('available_tools.manage_system_prompt_tool.database', new_callable=MagicMock)
async def test_manage_system_prompt_tool_update_success(mock_db, manage_system_prompt_tool_instance: ManageSystemPromptTool):
    mock_db.update_prompt = MagicMock() # No return value needed for update
    new_prompt = "This is the new system prompt."
    arguments = {"action": "update", "new_prompt_text": new_prompt}
    db_path_param = "dummy_db_path.db"

    result = await manage_system_prompt_tool_instance.execute(
        room_id="!r:h", arguments=arguments, tool_call_id="t3", 
        llm_provider_info={}, conversation_history_snapshot=[], last_user_event_id=None, db_path=db_path_param
    )

    assert result.status == "success"
    assert f"System prompt 'system_default' updated successfully." in result.result_for_llm_history
    mock_db.update_prompt.assert_called_once_with(db_path_param, "system_default", new_prompt)
    # Check for state_updates if the tool is expected to return them
    # Assuming the tool now correctly returns state_updates:
    expected_state_update_key = "manage_system_prompt.last_action"
    expected_state_update_value_fragment = "updated to: 'This is the new system prompt.'"
    assert result.state_updates is not None
    assert expected_state_update_key in result.state_updates
    assert expected_state_update_value_fragment in result.state_updates[expected_state_update_key]

@pytest.mark.asyncio
async def test_manage_system_prompt_tool_update_missing_text(manage_system_prompt_tool_instance: ManageSystemPromptTool):
    arguments = {"action": "update"} # Missing new_prompt_text
    db_path_param = "dummy_db_path.db"

    result = await manage_system_prompt_tool_instance.execute(
        room_id="!r:h", arguments=arguments, tool_call_id="t4", 
        llm_provider_info={}, conversation_history_snapshot=[], last_user_event_id=None, db_path=db_path_param
    )

    assert result.status == "failure"
    assert "Missing required argument: new_prompt_text for action 'update'" in result.error_message # Corrected expected message

@pytest.mark.asyncio
async def test_manage_system_prompt_tool_invalid_action(manage_system_prompt_tool_instance: ManageSystemPromptTool):
    arguments = {"action": "delete"} # Invalid action
    db_path_param = "dummy_db_path.db"

    result = await manage_system_prompt_tool_instance.execute(
        room_id="!r:h", arguments=arguments, tool_call_id="t5", 
        llm_provider_info={}, conversation_history_snapshot=[], last_user_event_id=None, db_path=db_path_param
    )

    assert result.status == "failure"
    assert "Invalid action specified: delete. Must be 'get_current' or 'update'." in result.error_message

@pytest.mark.asyncio
@patch('available_tools.manage_system_prompt_tool.database', new_callable=MagicMock)
async def test_manage_system_prompt_tool_db_exception_on_get(mock_db, manage_system_prompt_tool_instance: ManageSystemPromptTool):
    mock_db.get_prompt.side_effect = Exception("DB error on get")
    arguments = {"action": "get_current"}
    db_path_param = "dummy_db_path.db"

    result = await manage_system_prompt_tool_instance.execute(
        room_id="!r:h", arguments=arguments, tool_call_id="t6", 
        llm_provider_info={}, conversation_history_snapshot=[], last_user_event_id=None, db_path=db_path_param
    )
    assert result.status == "failure"
    assert "[Tool manage_system_prompt(action=get_current) failed due to an internal error.]" in result.result_for_llm_history # Corrected expected message
    assert "DB error on get" in result.error_message

@pytest.mark.asyncio
@patch('available_tools.manage_system_prompt_tool.database', new_callable=MagicMock)
async def test_manage_system_prompt_tool_db_exception_on_update(mock_db, manage_system_prompt_tool_instance: ManageSystemPromptTool):
    mock_db.update_prompt.side_effect = Exception("DB error on update")
    arguments = {"action": "update", "new_prompt_text": "test"}
    db_path_param = "dummy_db_path.db"

    result = await manage_system_prompt_tool_instance.execute(
        room_id="!r:h", arguments=arguments, tool_call_id="t7", 
        llm_provider_info={}, conversation_history_snapshot=[], last_user_event_id=None, db_path=db_path_param
    )
    assert result.status == "failure"
    assert "[Tool manage_system_prompt(action=update) failed due to an internal error.]" in result.result_for_llm_history # Corrected expected message
    assert "DB error on update" in result.error_message
