
import pytest
from unittest.mock import MagicMock

from available_tools.delegate_to_openrouter_tool import DelegateToOpenRouterTool
from tool_base import ToolResult, ToolParameter
from event_definitions import (
    OpenRouterInferenceRequestEvent,
    HistoricalMessage,
    BatchedUserMessage,
    ToolCall,
    ToolRoleMessage
)

@pytest.fixture
def delegate_tool_instance():
    return DelegateToOpenRouterTool()

def test_delegate_tool_get_definition(delegate_tool_instance: DelegateToOpenRouterTool):
    definition = delegate_tool_instance.get_definition()
    assert definition["name"] == "delegate_to_openrouter"
    assert "description" in definition
    assert len(definition["parameters"]) > 0 # Expects parameters like model_name, messages_payload, etc.
    param_names = [p.name for p in definition["parameters"]]
    assert "model_name" in param_names
    assert "messages_payload" in param_names # This is the one for raw messages
    assert "prompt_text" in param_names      # This is for a simple prompt
    # Check that messages_payload is a list of dicts (approximated by type string and description)
    messages_payload_param = next(p for p in definition["parameters"] if p.name == "messages_payload")
    assert messages_payload_param.type == "array"
    assert messages_payload_param.items.type == "object" # Pydantic models are dicts/objects in schema

@pytest.mark.asyncio
async def test_delegate_tool_execute_with_messages_payload(delegate_tool_instance: DelegateToOpenRouterTool):
    room_id = "!test_room:matrix.org"
    tool_call_id = "tc_delegate_msg"
    original_llm_provider_info = {"model": "original_model"}
    conversation_history = [HistoricalMessage(role="user", content="Hello from history")]
    last_user_event_id = "$last_user_event"

    # Sample messages_payload according to the tool's expected structure
    # (which should align with OpenAI/OpenRouter message format)
    messages_payload = [
        {"role": "system", "content": "You are a specialized assistant."},
        {"role": "user", "content": "Can you help with this specific task?"}
    ]
    arguments = {
        "model_name": "openrouter/some-model",
        "messages_payload": messages_payload,
        "temperature": 0.5,
        "max_tokens": 100
    }

    result = await delegate_tool_instance.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info=original_llm_provider_info,
        conversation_history_snapshot=conversation_history,
        last_user_event_id=last_user_event_id
    )

    assert result.status == "requires_llm_followup"
    assert result.result_text == "Delegating to OpenRouter model: openrouter/some-model. Waiting for response."
    assert len(result.commands_to_publish) == 1
    command = result.commands_to_publish[0]
    assert isinstance(command, OpenRouterInferenceRequestEvent)
    assert command.room_id == room_id
    assert command.ai_payload == messages_payload # Should use the provided messages_payload
    assert command.model_name == "openrouter/some-model"
    assert command.temperature == 0.5
    assert command.max_tokens == 100
    assert command.original_request_event_id == tool_call_id # Important for routing response
    assert command.event_type_to_respond_to == "delegated_open_router_response"

    # Check the complex payload_for_openrouter_response_handler
    assert result.data_from_tool_for_followup_llm is not None
    response_handler_payload = result.data_from_tool_for_followup_llm
    assert response_handler_payload["delegated_to_model"] == "openrouter/some-model"
    assert response_handler_payload["original_tool_call_id"] == tool_call_id
    assert response_handler_payload["original_llm_provider_info"] == original_llm_provider_info
    assert response_handler_payload["original_conversation_history_snapshot"] == conversation_history
    assert response_handler_payload["original_last_user_event_id"] == last_user_event_id
    assert "original_arguments_from_tool_call" in response_handler_payload
    assert response_handler_payload["original_arguments_from_tool_call"] == arguments

@pytest.mark.asyncio
async def test_delegate_tool_execute_with_prompt_text(delegate_tool_instance: DelegateToOpenRouterTool):
    room_id = "!test_room:matrix.org"
    tool_call_id = "tc_delegate_prompt"
    prompt_text = "Summarize this for me."
    arguments = {
        "model_name": "openrouter/another-model",
        "prompt_text": prompt_text
    }

    result = await delegate_tool_instance.execute(
        room_id=room_id,
        arguments=arguments,
        tool_call_id=tool_call_id,
        llm_provider_info=None, conversation_history_snapshot=[], last_user_event_id=None
    )

    assert result.status == "requires_llm_followup"
    assert len(result.commands_to_publish) == 1
    command = result.commands_to_publish[0]
    assert isinstance(command, OpenRouterInferenceRequestEvent)
    assert command.ai_payload == [{"role": "user", "content": prompt_text}] # prompt_text converted to messages
    assert command.model_name == "openrouter/another-model"

@pytest.mark.asyncio
async def test_delegate_tool_execute_missing_model_name(delegate_tool_instance: DelegateToOpenRouterTool):
    arguments = {"prompt_text": "Hello"}
    result = await delegate_tool_instance.execute("!r:h", arguments, "tc", None, [], None)
    assert result.status == "failure"
    assert "Missing required argument: model_name" in result.error_message

@pytest.mark.asyncio
async def test_delegate_tool_execute_missing_payload_and_prompt(delegate_tool_instance: DelegateToOpenRouterTool):
    arguments = {"model_name": "some-model"} # Neither messages_payload nor prompt_text
    result = await delegate_tool_instance.execute("!r:h", arguments, "tc", None, [], None)
    assert result.status == "failure"
    assert "Either 'messages_payload' or 'prompt_text' must be provided." in result.error_message

@pytest.mark.asyncio
async def test_delegate_tool_execute_both_payload_and_prompt(delegate_tool_instance: DelegateToOpenRouterTool):
    arguments = {
        "model_name": "some-model",
        "messages_payload": [{"role": "user", "content": "From payload"}],
        "prompt_text": "From prompt"
    }
    result = await delegate_tool_instance.execute("!r:h", arguments, "tc", None, [], None)
    assert result.status == "failure"
    assert "Provide either 'messages_payload' or 'prompt_text', not both." in result.error_message

@pytest.mark.asyncio
async def test_delegate_tool_execute_default_model_if_not_provided_in_args(delegate_tool_instance: DelegateToOpenRouterTool):
    # This test assumes the tool has a default model if one isn't in args, or it uses a global default.
    # For now, model_name is required by the tool definition. If it becomes optional with a default,
    # this test would need adjustment. The current tool code makes model_name required.
    # If model_name becomes optional in the tool's Pydantic model with a default, this test would change.
    # As of now, this scenario leads to a validation error by Pydantic if model_name is not given.
    pass # Covered by test_delegate_tool_execute_missing_model_name

@pytest.mark.asyncio
async def test_delegate_tool_passes_optional_params(delegate_tool_instance: DelegateToOpenRouterTool):
    arguments = {
        "model_name": "openrouter/test-model",
        "prompt_text": "Test prompt",
        "temperature": 0.8,
        "max_tokens": 150,
        "top_p": 0.9,
        "tool_choice": "auto",
        # "tools": [], # Not testing full tool passing here, just that other params go through
    }
    result = await delegate_tool_instance.execute("!r:h", arguments, "tc", None, [], None)
    assert result.status == "requires_llm_followup"
    command = result.commands_to_publish[0]
    assert isinstance(command, OpenRouterInferenceRequestEvent)
    assert command.temperature == 0.8
    assert command.max_tokens == 150
    assert command.top_p == 0.9
    assert command.tool_choice == "auto"
