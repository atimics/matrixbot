import pytest
from unittest.mock import MagicMock

from available_tools.send_message_tool import SendMessageTool
from tool_base import ToolResult
from event_definitions import SendMatrixMessageCommand

@pytest.fixture
def send_message_tool_instance():
    return SendMessageTool()

def test_send_message_tool_get_definition(send_message_tool_instance: SendMessageTool):
    definition = send_message_tool_instance.get_definition()
    assert definition["function"]["name"] == "send_message"
    assert "description" in definition["function"]
    assert "text" in definition["function"]["parameters"]["properties"]
    assert "text" in definition["function"]["parameters"]["required"]

@pytest.mark.asyncio
async def test_send_message_tool_execute_success(send_message_tool_instance: SendMessageTool):
    room_id = "!test_room:matrix.org"
    arguments = {"text": "Hello world!"}
    tool_call_id = "call_send_msg_1"

    result = await send_message_tool_instance.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info={},
        conversation_history_snapshot=[],
        last_user_event_id=None
    )

    assert result.status == "success"
    assert result.result_for_llm_history == "Message 'Hello world!' sent." # Check result_for_llm_history
    assert len(result.commands_to_publish) == 1
    command = result.commands_to_publish[0]
    assert isinstance(command, SendMatrixMessageCommand)
    assert command.room_id == room_id
    assert command.text == "Hello world!"
    assert command.reply_to_event_id is None

@pytest.mark.asyncio
async def test_send_message_tool_execute_missing_text(send_message_tool_instance: SendMessageTool):
    room_id = "!test_room:matrix.org"
    arguments = {}
    tool_call_id = "call_send_msg_2"

    result = await send_message_tool_instance.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info={},
        conversation_history_snapshot=[],
        last_user_event_id=None
    )

    assert result.status == "failure"
    assert "Missing required argument: text" in result.error_message
    assert not result.commands_to_publish

@pytest.mark.asyncio
async def test_send_message_tool_execute_empty_text(send_message_tool_instance: SendMessageTool):
    room_id = "!test_room:matrix.org"
    arguments = {"text": ""}
    tool_call_id = "call_send_msg_3"

    result = await send_message_tool_instance.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info={},
        conversation_history_snapshot=[],
        last_user_event_id=None
    )

    assert result.status == "failure"
    assert "Text argument cannot be empty." in result.error_message # Check error_message
    assert not result.commands_to_publish
