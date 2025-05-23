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
    MatrixImageReceivedEvent,
    ImageCaptionGeneratedEvent,
    HistoricalMessage, # Assuming this might be used or tested directly
    BatchedUserMessage, # Assuming this might be used or tested directly
    ToolCall, # Assuming this might be used or tested directly
    ToolRoleMessage, # Assuming this might be used or tested directly
    ToolFunction, # Added for corrected ToolCall instantiation
    EventType
)

# Helper to check common BaseEvent fields
def check_base_event_fields(event: BaseEvent, expected_event_type: EventType):
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
        event_id_matrix="$matrix_event_id", # Renamed from event_id
        sender_id="@user:host",
        sender_display_name="User A", # Added
        body="Hello world!", # Added
        room_display_name="Test Room" # Added
    )
    check_base_event_fields(event, EventType.MATRIX_MESSAGE_RECEIVED)
    assert event.room_id == "!room:host"
    assert event.event_id_matrix == "$matrix_event_id"
    assert event.sender_id == "@user:host"
    assert event.sender_display_name == "User A"
    assert event.body == "Hello world!"
    assert event.room_display_name == "Test Room"

def test_matrix_message_received_event_missing_fields():
    with pytest.raises(ValidationError):
        MatrixMessageReceivedEvent(room_id="!room:host")

# Test MatrixImageReceivedEvent
def test_matrix_image_received_event_valid():
    event = MatrixImageReceivedEvent(
        room_id="!room:host",
        event_id_matrix="$img_event",
        sender_id="@user:host",
        sender_display_name="User A",
        image_url="mxc://server/id",
        body="optional alt",
        room_display_name="Test Room",
    )
    check_base_event_fields(event, EventType.MATRIX_IMAGE_RECEIVED)
    assert event.image_url == "mxc://server/id"
    assert event.body == "optional alt"

def test_matrix_image_received_event_missing_fields():
    with pytest.raises(ValidationError):
        MatrixImageReceivedEvent(room_id="!room:host")

# Test SendMatrixMessageCommand
def test_send_matrix_message_command_valid():
    event = SendMatrixMessageCommand(
        room_id="!room:host",
        text="Response message",
        reply_to_event_id="$original_event"
    )
    check_base_event_fields(event, EventType.SEND_MATRIX_MESSAGE_COMMAND)
    assert event.room_id == "!room:host"
    assert event.text == "Response message"
    assert event.reply_to_event_id == "$original_event"

def test_send_matrix_message_command_valid_no_reply():
    event = SendMatrixMessageCommand(
        room_id="!room:host",
        text="General message"
    )
    check_base_event_fields(event, EventType.SEND_MATRIX_MESSAGE_COMMAND)
    assert event.room_id == "!room:host"
    assert event.text == "General message"
    assert event.reply_to_event_id is None

def test_send_matrix_message_command_missing_fields():
    with pytest.raises(ValidationError):
        SendMatrixMessageCommand(room_id="!room:host")

# Test ActivateListeningEvent
def test_activate_listening_event_valid():
    event = ActivateListeningEvent(room_id="!room:host", activation_message_event_id="$event1")
    check_base_event_fields(event, EventType.ACTIVATE_LISTENING)
    assert event.room_id == "!room:host"
    assert event.activation_message_event_id == "$event1"

# Test DeactivateListeningEvent
def test_deactivate_listening_event_valid():
    event = DeactivateListeningEvent(room_id="!room:host")
    check_base_event_fields(event, EventType.DEACTIVATE_LISTENING)
    assert event.room_id == "!room:host"

# Test ProcessMessageBatchCommand
def test_process_message_batch_command_valid():
    messages = [BatchedUserMessage(user_id="@user:host", content="Test", event_id="$event1")]
    event = ProcessMessageBatchCommand(room_id="!room:host", messages_in_batch=messages)
    check_base_event_fields(event, EventType.PROCESS_MESSAGE_BATCH_COMMAND)
    assert event.room_id == "!room:host"
    assert event.messages_in_batch == messages

# Test AIInferenceRequestEvent
def test_ai_inference_request_event_valid():
    payload = [{"role": "user", "content": "Hello"}]
    event = AIInferenceRequestEvent(
        request_id="req1", # Added
        reply_to_service_event="some_reply_event", # Added
        model_name="gpt-4", # Added
        messages_payload=payload, # Changed from ai_payload
        original_request_payload={"original_event_id": "$req_event"} # Example of storing other ids
    )
    check_base_event_fields(event, EventType.AI_INFERENCE_REQUEST)
    assert event.messages_payload == payload
    assert event.request_id == "req1"
    assert event.reply_to_service_event == "some_reply_event"
    assert event.model_name == "gpt-4"
    assert event.original_request_payload["original_event_id"] == "$req_event"

# Test AIInferenceResponseEvent
def test_ai_inference_response_event_success_text():
    event = AIInferenceResponseEvent(
        request_id="req1", # Added
        success=True,
        text_response="AI says hi",
        original_request_payload={"original_event_id": "$req_event", "response_topic": "some_topic"}
    )
    check_base_event_fields(event, EventType.AI_INFERENCE_RESPONSE)
    assert event.success is True
    assert event.text_response == "AI says hi"
    assert event.tool_calls is None
    assert event.error_message is None
    assert event.original_request_payload["response_topic"] == "some_topic" # Check within payload

def test_ai_inference_response_event_success_tool_calls():
    tool_calls = [ToolCall(id="tc1", type="function", function=ToolFunction(name="func", arguments="{}"))] # Corrected ToolCall
    event = AIInferenceResponseEvent(
        request_id="req1", # Added
        success=True,
        tool_calls=tool_calls,
        original_request_payload={"original_event_id": "$req_event", "response_topic": "some_topic"}
    )
    check_base_event_fields(event, EventType.AI_INFERENCE_RESPONSE)
    assert event.success is True
    assert event.text_response is None
    assert event.tool_calls == tool_calls

def test_ai_inference_response_event_failure():
    event = AIInferenceResponseEvent(
        request_id="req1", # Added
        success=False,
        error_message="API Error",
        original_request_payload={"original_event_id": "$req_event", "response_topic": "some_topic"}
    )
    check_base_event_fields(event, EventType.AI_INFERENCE_RESPONSE)
    assert event.success is False
    assert event.error_message == "API Error"

# Test OpenRouterInferenceRequestEvent
def test_openrouter_inference_request_event():
    payload = [{"role": "user", "content": "Hello"}]
    event = OpenRouterInferenceRequestEvent(
        request_id="or_req1", # Added
        reply_to_service_event="or_reply_event", # Added
        model_name="openrouter/model", # Added
        messages_payload=payload, # Changed from ai_payload
        original_request_payload={ # Store other IDs here
            "original_request_payload_event_id": "$orig_payload_id",
            "original_request_event_id": "$orig_req_id",
            "event_type_to_respond_to": "tool_response_type"
        }
    )
    check_base_event_fields(event, EventType.OPEN_ROUTER_INFERENCE_REQUEST)
    assert event.messages_payload == payload
    assert event.original_request_payload["original_request_payload_event_id"] == "$orig_payload_id"
    assert event.original_request_payload["original_request_event_id"] == "$orig_req_id"
    assert event.original_request_payload["event_type_to_respond_to"] == "tool_response_type"

# Test OpenRouterInferenceResponseEvent
def test_openrouter_inference_response_event():
    event = OpenRouterInferenceResponseEvent(
        request_id="or_req1", # Added
        success=True,
        text_response="Hi from OR",
        original_request_payload={ # Store other IDs here
            "original_request_event_id": "$req_event",
            "original_request_payload_event_id": "$orig_payload_id",
            "event_type_to_respond_to": "tool_response_type"
        }
    )
    check_base_event_fields(event, EventType.OPEN_ROUTER_INFERENCE_RESPONSE)
    assert event.text_response == "Hi from OR"
    assert event.original_request_payload["original_request_payload_event_id"] == "$orig_payload_id"
    assert event.original_request_payload["event_type_to_respond_to"] == "tool_response_type"

# Test OllamaInferenceRequestEvent
def test_ollama_inference_request_event():
    payload = [{"role": "user", "content": "Hello"}]
    event = OllamaInferenceRequestEvent(
        request_id="ol_req1", # Added
        reply_to_service_event="ol_reply_event", # Added
        model_name="ollama/model", # Added
        messages_payload=payload, # Changed from ai_payload
        original_request_payload={ # Store other IDs here
            "original_request_payload_event_id": "$orig_payload_id",
            "original_request_event_id": "$orig_req_id",
            "event_type_to_respond_to": "tool_response_type"
        }
    )
    check_base_event_fields(event, EventType.OLLAMA_INFERENCE_REQUEST)
    assert event.messages_payload == payload
    assert event.original_request_payload["original_request_payload_event_id"] == "$orig_payload_id"
    assert event.original_request_payload["original_request_event_id"] == "$orig_req_id"
    assert event.original_request_payload["event_type_to_respond_to"] == "tool_response_type"

# Test OllamaInferenceResponseEvent
def test_ollama_inference_response_event():
    event = OllamaInferenceResponseEvent(
        request_id="ol_req1", # Added
        success=True,
        text_response="Hi from Ollama",
        original_request_payload={ # Store other IDs here
            "original_request_event_id": "$req_event",
            "original_request_payload_event_id": "$orig_payload_id",
            "event_type_to_respond_to": "tool_response_type"
        }
    )
    check_base_event_fields(event, EventType.OLLAMA_INFERENCE_RESPONSE)
    assert event.text_response == "Hi from Ollama"
    assert event.original_request_payload["original_request_payload_event_id"] == "$orig_payload_id"
    assert event.original_request_payload["event_type_to_respond_to"] == "tool_response_type"

# Test ExecuteToolRequest
def test_execute_tool_request_valid():
    tool_call = ToolCall(id="tc1", type="function", function=ToolFunction(name="send_reply", arguments='{"text":"Hi"}')) # Corrected
    event = ExecuteToolRequest(
        room_id="!room:host",
        tool_call=tool_call,
        conversation_history_snapshot=[],
        last_user_event_id="$user_event",
        original_request_payload={"original_ai_request_event_id": "$ai_req"} # Added
    )
    check_base_event_fields(event, EventType.EXECUTE_TOOL_REQUEST)
    assert event.tool_call == tool_call
    assert event.original_request_payload["original_ai_request_event_id"] == "$ai_req" # Check in payload

# Test ToolExecutionResponse
def test_tool_execution_response_success():
    event = ToolExecutionResponse(
        original_tool_call_id="tc1",
        tool_name="test_tool", # Added
        status="success",
        result_for_llm_history="Tool ran okay", # Changed from result_text
        commands_to_publish=[],
        original_request_payload={"original_ai_request_event_id": "$ai_req"} # Added
    )
    check_base_event_fields(event, EventType.TOOL_EXECUTION_RESPONSE)
    assert event.status == "success"
    assert event.result_for_llm_history == "Tool ran okay"

def test_tool_execution_response_failure():
    event = ToolExecutionResponse(
        original_tool_call_id="tc1",
        tool_name="test_tool", # Added
        status="failure",
        error_message="Tool broke",
        result_for_llm_history="", # Added required field
        original_request_payload={"original_ai_request_event_id": "$ai_req"} # Added
    )
    check_base_event_fields(event, EventType.TOOL_EXECUTION_RESPONSE)
    assert event.status == "failure"
    assert event.error_message == "Tool broke"

def test_tool_execution_response_requires_followup():
    event = ToolExecutionResponse(
        original_tool_call_id="tc1",
        tool_name="test_tool", # Added
        status="requires_llm_followup",
        data_from_tool_for_followup_llm={"key": "value"},
        result_for_llm_history="Follow up needed", # Added required field
        original_request_payload={"original_ai_request_event_id": "$ai_req"} # Added
    )
    check_base_event_fields(event, EventType.TOOL_EXECUTION_RESPONSE)
    assert event.status == "requires_llm_followup"
    assert event.data_from_tool_for_followup_llm == {"key": "value"}

# Test SetTypingIndicatorCommand
def test_set_typing_indicator_command_valid():
    event = SetTypingIndicatorCommand(room_id="!room:host", typing=True)
    check_base_event_fields(event, EventType.SET_TYPING_INDICATOR_COMMAND)
    assert event.room_id == "!room:host"
    assert event.typing is True
    # Test Literal validation for event_type
    with pytest.raises(ValidationError):
        SetTypingIndicatorCommand(room_id="!room:host", typing=True, event_type="invalid_type")

# Test ReactToMessageCommand
def test_react_to_message_command_valid():
    event = ReactToMessageCommand(room_id="!room:host", event_id_to_react_to="$event1", reaction_key="👍")
    check_base_event_fields(event, EventType.REACT_TO_MESSAGE_COMMAND)
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
    check_base_event_fields(event, EventType.REQUEST_AI_SUMMARY_COMMAND)
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
    check_base_event_fields(event, EventType.SUMMARY_GENERATED)
    assert event.summary_text == "New summary"
    assert event.last_event_id_summarized == "$last_event"

# Test BotDisplayNameReadyEvent
def test_bot_display_name_ready_event_valid():
    event = BotDisplayNameReadyEvent(display_name="MyBot", user_id="@bot:server")
    check_base_event_fields(event, EventType.BOT_DISPLAY_NAME_READY)
    assert event.display_name == "MyBot"
    assert event.user_id == "@bot:server"

# Test ImageCaptionGeneratedEvent
def test_image_caption_generated_event_valid():
    event = ImageCaptionGeneratedEvent(
        room_id="!room:host",
        caption_text="a cat",
        original_event_id="$img1",
    )
    check_base_event_fields(event, EventType.IMAGE_CAPTION_GENERATED)
    assert event.caption_text == "a cat"
    assert event.original_event_id == "$img1"

# Test default timestamp generation and awareness
def test_base_event_timestamp_defaults():
    before = datetime.now(timezone.utc)
    event = BaseEvent(event_type=EventType.MATRIX_MESSAGE_RECEIVED)
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
    tc = ToolCall(id="t1", type="function", function=ToolFunction(name="f1", arguments="{}")) # Corrected
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
    tc = ToolCall(id="t1", type="function", function=ToolFunction(name="f1", arguments='{"arg":"val"}')) # Corrected
    assert tc.id == "t1"
    assert tc.type == "function"
    assert tc.function.name == "f1"
    assert tc.function.arguments == '{"arg":"val"}'

def test_tool_role_message_valid():
    msg = ToolRoleMessage(tool_call_id="t1", content="Tool output")
    assert msg.tool_call_id == "t1"
    assert msg.content == "Tool output"

