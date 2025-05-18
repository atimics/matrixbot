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
    assert definition["name"] == "send_reply"
    assert "description" in definition
    assert len(definition["parameters"]) == 2
    param_names = [p.name for p in definition["parameters"]]
    assert "text" in param_names
    assert "reply_to_event_id" in param_names
    text_param = next(p for p in definition["parameters"] if p.name == "text")
    assert text_param.required is True

@pytest.mark.asyncio
async def test_send_reply_tool_execute_success(send_reply_tool_instance: SendReplyTool):
    room_id = "!test_room:matrix.org"
    arguments = {"text": "Hello there!", "reply_to_event_id": "$event1"}
    tool_call_id = "call123"

    result = await send_reply_tool_instance.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info=None,
        conversation_history_snapshot=[],
        last_user_event_id=None
    )

    assert result.status == "success"
    assert result.result_text == "Reply sent."
    assert len(result.commands_to_publish) == 1
    command = result.commands_to_publish[0]
    assert isinstance(command, SendMatrixMessageCommand)
    assert command.room_id == room_id
    assert command.text == "Hello there!"
    assert command.reply_to_event_id == "$event1"

@pytest.mark.asyncio
async def test_send_reply_tool_execute_success_no_reply_id(send_reply_tool_instance: SendReplyTool):
    room_id = "!test_room:matrix.org"
    arguments = {"text": "General Kenobi!"}
    tool_call_id = "call456"

    result = await send_reply_tool_instance.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info=None,
        conversation_history_snapshot=[],
        last_user_event_id=None
    )

    assert result.status == "success"
    assert result.result_text == "Reply sent."
    command = result.commands_to_publish[0]
    assert isinstance(command, SendMatrixMessageCommand)
    assert command.text == "General Kenobi!"
    assert command.reply_to_event_id is None

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
    assert "Missing required argument: text" in result.error_message
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
    tool_call_id = "callDEF"

    result = await send_reply_tool_instance.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info=None,
        conversation_history_snapshot=[],
        last_user_event_id=None # Context is missing
    )

    assert result.status == "failure"
    assert "Cannot resolve $event:last_user_message, last_user_event_id is not available." in result.error_message
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
    assert "Text argument cannot be empty." in result.error_message
    assert not result.commands_to_publish

