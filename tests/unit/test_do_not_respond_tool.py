import pytest
from unittest.mock import MagicMock

from available_tools.do_not_respond_tool import DoNotRespondTool
from tool_base import ToolResult

@pytest.fixture
def do_not_respond_tool_instance():
    return DoNotRespondTool()

def test_do_not_respond_tool_get_definition(do_not_respond_tool_instance: DoNotRespondTool):
    definition = do_not_respond_tool_instance.get_definition()
    assert definition["function"]["name"] == "do_not_respond"
    assert "description" in definition["function"]
    assert not definition["function"]["parameters"]["properties"] # No parameters
    assert not definition["function"]["parameters"]["required"]

@pytest.mark.asyncio
async def test_do_not_respond_tool_execute(do_not_respond_tool_instance: DoNotRespondTool):
    room_id = "!test_room:matrix.org"
    arguments = {}
    tool_call_id = "call_do_not_respond_1"

    result = await do_not_respond_tool_instance.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info={},
        conversation_history_snapshot=[],
        last_user_event_id=None
    )

    assert result.status == "success"
    assert result.result_for_llm_history == "[Tool 'do_not_respond' executed: No action taken, bot will not send a message.]"
    assert result.commands_to_publish is None
    assert result.state_updates is None
