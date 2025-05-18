
import pytest
from pydantic import ValidationError
from datetime import datetime, timezone

from event_definitions import (
    BaseEvent,
    MatrixMessageReceivedEvent,
    SendMatrixMessageCommand,
    ActivateListeningEvent,
    DeactivateListeningEvent,
    ProcessMessageBatchCommand,
    AIInferenceRequestEvent,
    AIInferenceResponseEvent,
    OpenRouterInferenceRequestEvent,
    OpenRouterInferenceResponseEvent,
    OllamaInferenceRequestEvent,
    OllamaInferenceResponseEvent,
    ExecuteToolRequest,
    ToolExecutionResponse,
    SetTypingIndicatorCommand,
    ReactToMessageCommand,
    RequestAISummaryCommand,
    SummaryGeneratedEvent,
    BotDisplayNameReadyEvent,
    HistoricalMessage, # Assuming this might be used or tested directly
    BatchedUserMessage, # Assuming this might be used or tested directly
    ToolCall, # Assuming this might be used or tested directly
    ToolRoleMessage # Assuming this might be used or tested directly
)

# Helper to check common BaseEvent fields
def check_base_event_fields(event: BaseEvent, expected_event_type: str):
    assert isinstance(event.event_id, str)
    assert len(event.event_id) > 0
    assert isinstance(event.timestamp, datetime)
    # Check if timestamp is timezone-aware and UTC
    assert event.timestamp.tzinfo == timezone.utc
    assert event.event_type == expected_event_type

# Test MatrixMessageReceivedEvent
def test_matrix_message_received_event_valid():
    event = MatrixMessageReceivedEvent(
        room_id="!room:host",
        sender_id="@user:host",
        message_content="Hello world!",
        event_id_matrix="$matrix_event_id"
    )
    check_base_event_fields(event, "matrix_message_received")
    assert event.room_id == "!room:host"
    assert event.sender_id == "@user:host"
    assert event.message_content == "Hello world!"
    assert event.event_id_matrix == "$matrix_event_id"

def test_matrix_message_received_event_missing_fields():
    with pytest.raises(ValidationError):
        MatrixMessageReceivedEvent(room_id="!room:host")

# Test SendMatrixMessageCommand
def test_send_matrix_message_command_valid():
    event = SendMatrixMessageCommand(
        room_id="!room:host",
        text="Response message",
        reply_to_event_id="$original_event"
    )
    check_base_event_fields(event, "send_matrix_message_command")
    assert event.room_id == "!room:host"
    assert event.text == "Response message"
    assert event.reply_to_event_id == "$original_event"

def test_send_matrix_message_command_valid_no_reply():
    event = SendMatrixMessageCommand(
        room_id="!room:host",
        text="General message"
    )
    check_base_event_fields(event, "send_matrix_message_command")
    assert event.room_id == "!room:host"
    assert event.text == "General message"
    assert event.reply_to_event_id is None

def test_send_matrix_message_command_missing_fields():
    with pytest.raises(ValidationError):
        SendMatrixMessageCommand(room_id="!room:host")

# Test ActivateListeningEvent
def test_activate_listening_event_valid():
    event = ActivateListeningEvent(room_id="!room:host", activation_message_event_id="$event1")
    check_base_event_fields(event, "activate_listening")
    assert event.room_id == "!room:host"
    assert event.activation_message_event_id == "$event1"

# Test DeactivateListeningEvent
def test_deactivate_listening_event_valid():
    event = DeactivateListeningEvent(room_id="!room:host")
    check_base_event_fields(event, "deactivate_listening")
    assert event.room_id == "!room:host"

# Test ProcessMessageBatchCommand
def test_process_message_batch_command_valid():
    messages = [BatchedUserMessage(user_id="@user:host", content="Test", event_id="$event1")]
    event = ProcessMessageBatchCommand(room_id="!room:host", messages_in_batch=messages)
    check_base_event_fields(event, "process_message_batch_command")
    assert event.room_id == "!room:host"
    assert event.messages_in_batch == messages

# Test AIInferenceRequestEvent
def test_ai_inference_request_event_valid():
    payload = [{"role": "user", "content": "Hello"}]
    event = AIInferenceRequestEvent(
        room_id="!room:host",
        ai_payload=payload,
        original_request_event_id="$req_event",
        follow_up_ai_request_event_id="$followup_event",
        request_topic="some_topic"
    )
    check_base_event_fields(event, "ai_inference_request")
    assert event.ai_payload == payload
    assert event.original_request_event_id == "$req_event"
    assert event.follow_up_ai_request_event_id == "$followup_event"
    assert event.request_topic == "some_topic"

# Test AIInferenceResponseEvent
def test_ai_inference_response_event_success_text():
    event = AIInferenceResponseEvent(
        original_request_event_id="$req_event",
        success=True,
        text_response="AI says hi",
        response_topic="some_topic"
    )
    check_base_event_fields(event, "ai_inference_response")
    assert event.success is True
    assert event.text_response == "AI says hi"
    assert event.tool_calls is None
    assert event.error_message is None
    assert event.response_topic == "some_topic"

def test_ai_inference_response_event_success_tool_calls():
    tool_calls = [ToolCall(id="tc1", function_name="func", function_args="{}")]
    event = AIInferenceResponseEvent(
        original_request_event_id="$req_event",
        success=True,
        tool_calls=tool_calls,
        response_topic="some_topic"
    )
    check_base_event_fields(event, "ai_inference_response")
    assert event.success is True
    assert event.text_response is None
    assert event.tool_calls == tool_calls

def test_ai_inference_response_event_failure():
    event = AIInferenceResponseEvent(
        original_request_event_id="$req_event",
        success=False,
        error_message="API Error",
        response_topic="some_topic"
    )
    check_base_event_fields(event, "ai_inference_response")
    assert event.success is False
    assert event.error_message == "API Error"

# Test OpenRouterInferenceRequestEvent
def test_openrouter_inference_request_event():
    payload = [{"role": "user", "content": "Hello"}]
    event = OpenRouterInferenceRequestEvent(
        room_id="!room:host",
        ai_payload=payload,
        original_request_payload_event_id="$orig_payload_id",
        original_request_event_id="$orig_req_id",
        event_type_to_respond_to="tool_response_type"
    )
    check_base_event_fields(event, "open_router_inference_request")
    assert event.ai_payload == payload
    assert event.original_request_payload_event_id == "$orig_payload_id"
    assert event.original_request_event_id == "$orig_req_id"
    assert event.event_type_to_respond_to == "tool_response_type"

# Test OpenRouterInferenceResponseEvent
def test_openrouter_inference_response_event():
    event = OpenRouterInferenceResponseEvent(
        original_request_event_id="$req_event",
        success=True,
        text_response="Hi from OR",
        original_request_payload_event_id="$orig_payload_id",
        event_type_to_respond_to="tool_response_type"
    )
    check_base_event_fields(event, "open_router_inference_response")
    assert event.text_response == "Hi from OR"
    assert event.original_request_payload_event_id == "$orig_payload_id"
    assert event.event_type_to_respond_to == "tool_response_type"

# Test OllamaInferenceRequestEvent
def test_ollama_inference_request_event():
    payload = [{"role": "user", "content": "Hello"}]
    event = OllamaInferenceRequestEvent(
        room_id="!room:host",
        ai_payload=payload,
        original_request_payload_event_id="$orig_payload_id",
        original_request_event_id="$orig_req_id",
        event_type_to_respond_to="tool_response_type"
    )
    check_base_event_fields(event, "ollama_inference_request")
    assert event.ai_payload == payload
    assert event.original_request_payload_event_id == "$orig_payload_id"
    assert event.original_request_event_id == "$orig_req_id"
    assert event.event_type_to_respond_to == "tool_response_type"

# Test OllamaInferenceResponseEvent
def test_ollama_inference_response_event():
    event = OllamaInferenceResponseEvent(
        original_request_event_id="$req_event",
        success=True,
        text_response="Hi from Ollama",
        original_request_payload_event_id="$orig_payload_id",
        event_type_to_respond_to="tool_response_type"
    )
    check_base_event_fields(event, "ollama_inference_response")
    assert event.text_response == "Hi from Ollama"
    assert event.original_request_payload_event_id == "$orig_payload_id"
    assert event.event_type_to_respond_to == "tool_response_type"

# Test ExecuteToolRequest
def test_execute_tool_request_valid():
    tool_call = ToolCall(id="tc1", function_name="send_reply", function_args='{"text":"Hi"}')
    event = ExecuteToolRequest(
        room_id="!room:host",
        tool_call=tool_call,
        original_ai_request_event_id="$ai_req",
        conversation_history_snapshot=[],
        last_user_event_id="$user_event"
    )
    check_base_event_fields(event, "execute_tool_request")
    assert event.tool_call == tool_call
    assert event.original_ai_request_event_id == "$ai_req"
    assert event.conversation_history_snapshot == []
    assert event.last_user_event_id == "$user_event"

# Test ToolExecutionResponse
def test_tool_execution_response_success():
    event = ToolExecutionResponse(
        original_tool_call_id="tc1",
        original_ai_request_event_id="$ai_req",
        status="success",
        result_text="Tool ran okay",
        commands_to_publish=[]
    )
    check_base_event_fields(event, "tool_execution_response")
    assert event.status == "success"
    assert event.result_text == "Tool ran okay"

def test_tool_execution_response_failure():
    event = ToolExecutionResponse(
        original_tool_call_id="tc1",
        original_ai_request_event_id="$ai_req",
        status="failure",
        error_message="Tool broke"
    )
    check_base_event_fields(event, "tool_execution_response")
    assert event.status == "failure"
    assert event.error_message == "Tool broke"

def test_tool_execution_response_requires_followup():
    event = ToolExecutionResponse(
        original_tool_call_id="tc1",
        original_ai_request_event_id="$ai_req",
        status="requires_llm_followup",
        data_from_tool_for_followup_llm={"key": "value"}
    )
    check_base_event_fields(event, "tool_execution_response")
    assert event.status == "requires_llm_followup"
    assert event.data_from_tool_for_followup_llm == {"key": "value"}

# Test SetTypingIndicatorCommand
def test_set_typing_indicator_command_valid():
    event = SetTypingIndicatorCommand(room_id="!room:host", typing=True)
    check_base_event_fields(event, "set_typing_indicator_command")
    assert event.room_id == "!room:host"
    assert event.typing is True
    # Test Literal validation for event_type
    with pytest.raises(ValidationError):
        BaseEvent(event_type="invalid_type") # type: ignore

# Test ReactToMessageCommand
def test_react_to_message_command_valid():
    event = ReactToMessageCommand(room_id="!room:host", event_id_to_react_to="$event1", reaction_key="👍")
    check_base_event_fields(event, "react_to_message_command")
    assert event.reaction_key == "👍"

# Test RequestAISummaryCommand
def test_request_ai_summary_command_valid():
    messages = [HistoricalMessage(role="user", content="text")]
    event = RequestAISummaryCommand(
        room_id="!room:host",
        messages_to_summarize=messages,
        current_summary_text="Old summary",
        last_event_id_in_messages="$last_msg"
    )
    check_base_event_fields(event, "request_ai_summary_command")
    assert event.messages_to_summarize == messages
    assert event.current_summary_text == "Old summary"
    assert event.last_event_id_in_messages == "$last_msg"

# Test SummaryGeneratedEvent
def test_summary_generated_event_valid():
    event = SummaryGeneratedEvent(
        room_id="!room:host",
        summary_text="New summary",
        last_event_id_summarized="$last_event"
    )
    check_base_event_fields(event, "summary_generated")
    assert event.summary_text == "New summary"
    assert event.last_event_id_summarized == "$last_event"

# Test BotDisplayNameReadyEvent
def test_bot_display_name_ready_event_valid():
    event = BotDisplayNameReadyEvent(display_name="MyBot")
    check_base_event_fields(event, "bot_display_name_ready")
    assert event.display_name == "MyBot"

# Test default timestamp generation and awareness
def test_base_event_timestamp_defaults():
    before = datetime.now(timezone.utc)
    event = BaseEvent(event_type="test_event")
    after = datetime.now(timezone.utc)
    assert event.timestamp >= before
    assert event.timestamp <= after
    assert event.timestamp.tzinfo == timezone.utc

# Test Pydantic models used as fields
def test_historical_message_valid():
    msg = HistoricalMessage(role="user", content="A message")
    assert msg.role == "user"
    assert msg.content == "A message"
    assert msg.tool_calls is None

def test_historical_message_with_tool_calls():
    tc = ToolCall(id="t1", function_name="f1", function_args="{}")
    msg = HistoricalMessage(role="assistant", tool_calls=[tc])
    assert msg.role == "assistant"
    assert msg.content is None
    assert msg.tool_calls == [tc]

def test_batched_user_message_valid():
    msg = BatchedUserMessage(user_id="@u:h", content="Batch msg", event_id="$e1")
    assert msg.user_id == "@u:h"
    assert msg.content == "Batch msg"
    assert msg.event_id == "$e1"

def test_tool_call_valid():
    tc = ToolCall(id="t1", function_name="f1", function_args='{"arg":"val"}')
    assert tc.id == "t1"
    assert tc.type == "function"
    assert tc.function.name == "f1"
    assert tc.function.arguments == '{"arg":"val"}'

def test_tool_role_message_valid():
    msg = ToolRoleMessage(tool_call_id="t1", content="Tool output")
    assert msg.tool_call_id == "t1"
    assert msg.content == "Tool output"

