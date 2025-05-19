import pytest
from unittest.mock import MagicMock

from available_tools.send_reply_tool import SendReplyTool
from tool_base import ToolResult, ToolParameter
from event_definitions import SendMatrixMessageCommand

@pytest.fixture
def send_reply_tool_instance():
    return SendReplyTool()

def test_send_reply_tool_get_definition(send_reply_tool_instance: SendReplyTool):
    definition = send_reply_tool_instance.get_definition()
    assert definition["function"]["name"] == "send_reply"
    assert "description" in definition["function"]
    assert "text" in definition["function"]["parameters"]["properties"]
    assert "reply_to_event_id" in definition["function"]["parameters"]["properties"]
    assert "text" in definition["function"]["parameters"]["required"]
    # reply_to_event_id is not strictly required if we allow resolving to last message

@pytest.mark.asyncio
async def test_send_reply_tool_execute_success(send_reply_tool_instance: SendReplyTool):
    room_id = "!test_room:matrix.org"
    event_id_to_reply_to = "$event1"
    text_to_send = "Hello there!"
    arguments = {"text": text_to_send, "reply_to_event_id": event_id_to_reply_to}
    tool_call_id = "call_reply_1"

    result = await send_reply_tool_instance.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info={},
        conversation_history_snapshot=[],
        last_user_event_id=None
    )

    assert result.status == "success"
    assert result.result_for_llm_history == f"Reply '{text_to_send}' sent to event '{event_id_to_reply_to}'." # Check result_for_llm_history
    assert len(result.commands_to_publish) == 1
    command = result.commands_to_publish[0]
    assert isinstance(command, SendMatrixMessageCommand)
    assert command.room_id == room_id
    assert command.text == "Hello there!"
    assert command.reply_to_event_id == "$event1"

@pytest.mark.asyncio
async def test_send_reply_tool_execute_success_no_reply_id(send_reply_tool_instance: SendReplyTool):
    # This test assumes the tool can function without a reply_to_event_id,
    # effectively becoming like send_message. Or it might be an invalid use case
    # depending on strictness. For now, let's assume it sends a non-reply message.
    # The tool's own logic should dictate this. The current tool implementation
    # seems to require reply_to_event_id if not resolving $event:last_user_message
    # Let's adjust the test to reflect that if it's a failure case, or ensure the tool handles it.
    # Based on current tool logic, this should fail if not resolving last_user_event_id
    room_id = "!test_room:matrix.org"
    text_to_send = "General Kenobi!"
    arguments = {"text": text_to_send} # Missing reply_to_event_id
    tool_call_id = "call_reply_no_id"
    
    # Assuming the tool is updated to handle this by sending a normal message OR
    # this test is expected to fail if reply_to_event_id is strictly needed and not $last.
    # Given the prompt, send_reply should probably fail if no event_id is given and it's not $last.
    # Let's assume it's a failure if reply_to_event_id is missing and not resolving.

    result = await send_reply_tool_instance.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info={},
        conversation_history_snapshot=[],
        last_user_event_id=None # No context for $event:last_user_message
    )

    assert result.status == "failure" # Expect failure if reply_to_event_id is mandatory and not $last
    assert "Missing required argument: reply_to_event_id" in result.error_message

@pytest.mark.asyncio
async def test_send_reply_tool_execute_missing_text_arg(send_reply_tool_instance: SendReplyTool):
    room_id = "!test_room:matrix.org"
    arguments = {"reply_to_event_id": "$event1"} # Missing 'text'
    tool_call_id = "call789"

    result = await send_reply_tool_instance.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info=None,
        conversation_history_snapshot=[],
        last_user_event_id=None
    )

    assert result.status == "failure"
    assert "Missing required argument: text" in result.error_message # Check error_message
    assert not result.commands_to_publish

@pytest.mark.asyncio
async def test_send_reply_tool_execute_resolve_last_user_event_id(send_reply_tool_instance: SendReplyTool):
    room_id = "!test_room:matrix.org"
    arguments = {"text": "Replying to last user", "reply_to_event_id": "$event:last_user_message"}
    tool_call_id = "callABC"
    last_user_event_id = "$actual_last_user_event_id"

    result = await send_reply_tool_instance.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info=None,
        conversation_history_snapshot=[],
        last_user_event_id=last_user_event_id
    )

    assert result.status == "success"
    command = result.commands_to_publish[0]
    assert isinstance(command, SendMatrixMessageCommand)
    assert command.reply_to_event_id == last_user_event_id

@pytest.mark.asyncio
async def test_send_reply_tool_execute_resolve_last_user_event_id_missing_context(send_reply_tool_instance: SendReplyTool):
    room_id = "!test_room:matrix.org"
    arguments = {"text": "Trying to reply to last user", "reply_to_event_id": "$event:last_user_message"}
    tool_call_id = "call_reply_resolve_fail"

    result = await send_reply_tool_instance.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info={},
        conversation_history_snapshot=[],
        last_user_event_id=None # Context is missing
    )

    assert result.status == "failure"
    assert "Cannot resolve $event:last_user_message, last_user_event_id is not available." in result.error_message # Check error_message
    assert not result.commands_to_publish

@pytest.mark.asyncio
async def test_send_reply_tool_execute_empty_text_arg(send_reply_tool_instance: SendReplyTool):
    room_id = "!test_room:matrix.org"
    arguments = {"text": "", "reply_to_event_id": "$event1"}
    tool_call_id = "callGHI"

    result = await send_reply_tool_instance.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info=None,
        conversation_history_snapshot=[],
        last_user_event_id=None
    )

    assert result.status == "failure"
    assert "Text argument cannot be empty." in result.error_message # Check error_message
    assert not result.commands_to_publish

