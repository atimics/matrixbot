import pytest
from unittest.mock import MagicMock

from available_tools.react_to_message_tool import ReactToMessageTool
from tool_base import ToolResult, ToolParameter
from event_definitions import ReactToMessageCommand

@pytest.fixture
def react_tool_instance():
    return ReactToMessageTool()

def test_react_tool_get_definition(react_tool_instance: ReactToMessageTool):
    definition = react_tool_instance.get_definition()
    assert definition["function"]["name"] == "react_to_message"
    assert "description" in definition["function"]
    assert "target_event_id" in definition["function"]["parameters"]["properties"]
    assert "reaction_key" in definition["function"]["parameters"]["properties"]
    assert "target_event_id" in definition["function"]["parameters"]["required"]
    assert "reaction_key" in definition["function"]["parameters"]["required"]

@pytest.mark.asyncio
async def test_react_tool_execute_success(react_tool_instance: ReactToMessageTool):
    room_id = "!test_room:matrix.org"
    arguments = {"target_event_id": "$event_to_react_to", "reaction_key": "👍"}
    tool_call_id = "call_react_1"

    result = await react_tool_instance.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info=None,
        conversation_history_snapshot=[],
        last_user_event_id=None
    )

    assert result.status == "success"
    assert result.result_for_llm_history == "Reaction '👍' sent to event '$event_to_react_to'."
    assert len(result.commands_to_publish) == 1
    command = result.commands_to_publish[0]
    assert isinstance(command, ReactToMessageCommand)
    assert command.room_id == room_id
    assert command.event_id_to_react_to == "$event_to_react_to"
    assert command.reaction_key == "👍"

@pytest.mark.asyncio
async def test_react_tool_execute_missing_event_id(react_tool_instance: ReactToMessageTool):
    arguments = {"reaction_key": "🤔"} # Missing target_event_id
    result = await react_tool_instance.execute("!r:h", arguments, "tc", None, [], None)
    assert result.status == "failure"
    assert "Missing required argument: target_event_id" in result.error_message
    assert not result.commands_to_publish

@pytest.mark.asyncio
async def test_react_tool_execute_missing_reaction_key(react_tool_instance: ReactToMessageTool):
    arguments = {"target_event_id": "$some_event"} # Missing reaction_key
    result = await react_tool_instance.execute("!r:h", arguments, "tc", None, [], None)
    assert result.status == "failure"
    assert "Missing required argument: reaction_key" in result.error_message
    assert not result.commands_to_publish

@pytest.mark.asyncio
async def test_react_tool_execute_resolve_last_user_event_id(react_tool_instance: ReactToMessageTool):
    room_id = "!test_room:matrix.org"
    arguments = {"target_event_id": "$event:last_user_message", "reaction_key": "🎉"}
    tool_call_id = "call_react_resolve"
    last_user_event_id = "$actual_last_user_event_id_for_reaction"

    result = await react_tool_instance.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info=None,
        conversation_history_snapshot=[],
        last_user_event_id=last_user_event_id
    )

    assert result.status == "success"
    command = result.commands_to_publish[0]
    assert isinstance(command, ReactToMessageCommand)
    assert command.event_id_to_react_to == last_user_event_id
    assert command.reaction_key == "🎉"

@pytest.mark.asyncio
async def test_react_tool_execute_resolve_last_user_event_id_missing_context(react_tool_instance: ReactToMessageTool):
    room_id = "!test_room:matrix.org"
    arguments = {"target_event_id": "$event:last_user_message", "reaction_key": "👎"}
    tool_call_id = "call_react_resolve_fail"

    result = await react_tool_instance.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info=None,
        conversation_history_snapshot=[],
        last_user_event_id=None # Context is missing
    )

    assert result.status == "failure"
    assert "Cannot resolve $event:last_user_message for reaction, last_user_event_id is not available." in result.error_message
    assert not result.commands_to_publish

@pytest.mark.asyncio
async def test_react_tool_execute_empty_reaction_key(react_tool_instance: ReactToMessageTool):
    arguments = {"target_event_id": "$some_event", "reaction_key": ""}
    result = await react_tool_instance.execute("!r:h", arguments, "tc", None, [], None)
    assert result.status == "failure"
    assert "Reaction key cannot be empty." in result.error_message
    assert not result.commands_to_publish
