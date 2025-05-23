from typing import List, Dict, Optional, Literal, Any
from pydantic import BaseModel, Field, field_validator
from enum import Enum
from datetime import datetime, timezone
import uuid


class EventType(str, Enum):
    MATRIX_MESSAGE_RECEIVED = "matrix_message_received"
    MATRIX_IMAGE_RECEIVED = "matrix_image_received"
    SEND_MATRIX_MESSAGE_COMMAND = "send_matrix_message_command"
    AI_INFERENCE_REQUEST = "ai_inference_request"
    AI_INFERENCE_RESPONSE = "ai_inference_response"
    OPEN_ROUTER_INFERENCE_REQUEST = "open_router_inference_request"
    OPEN_ROUTER_INFERENCE_RESPONSE = "open_router_inference_response"
    OLLAMA_INFERENCE_REQUEST = "ollama_inference_request"
    OLLAMA_INFERENCE_RESPONSE = "ollama_inference_response"
    ACTIVATE_LISTENING = "activate_listening"
    DEACTIVATE_LISTENING = "deactivate_listening"
    PROCESS_MESSAGE_BATCH_COMMAND = "process_message_batch_command"
    SUMMARY_GENERATED = "summary_generated"
    REACT_TO_MESSAGE_COMMAND = "react_to_message_command"
    SEND_REPLY_COMMAND = "send_reply_command"
    BOT_DISPLAY_NAME_READY = "bot_display_name_ready"
    IMAGE_CAPTION_GENERATED = "image_caption_generated"
    SET_TYPING_INDICATOR_COMMAND = "set_typing_indicator_command"
    SET_PRESENCE_COMMAND = "set_presence_command"
    REQUEST_AI_SUMMARY_COMMAND = "request_ai_summary_command"
    REQUEST_MATRIX_ROOM_INFO_COMMAND = "request_matrix_room_info_command"
    MATRIX_ROOM_INFO_RESPONSE_EVENT = "matrix_room_info_response_event"
    EXECUTE_TOOL_REQUEST = "execute_tool_request"
    TOOL_EXECUTION_RESPONSE = "tool_execution_response"
    DELEGATED_OPENROUTER_RESPONSE_FOR_TOOL = "delegated_openrouter_response_for_tool"

# Helper function to generate a default UUID string if needed elsewhere,
# but Pydantic's default_factory is usually sufficient for default field values.

class BaseEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique identifier for the event")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Event creation timestamp")
    event_type: EventType = Field(..., description="The type of the event")

    @field_validator('timestamp', mode='before')
    def ensure_timezone_aware(cls, v):
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        if isinstance(v, (int, float)): # Support for float timestamps
            return datetime.fromtimestamp(v, tz=timezone.utc)
        return v

    @classmethod
    def get_event_type(cls) -> EventType:
        """Return the default event type for this class."""
        if hasattr(cls, "model_fields"):
            return cls.model_fields["event_type"].default  # type: ignore[attr-defined]
        return cls.__fields__["event_type"].default  # type: ignore[attr-defined]

class MatrixMessageReceivedEvent(BaseEvent):
    event_type: EventType = Field(EventType.MATRIX_MESSAGE_RECEIVED, frozen=True)
    room_id: str
    event_id_matrix: str # Renamed from event_id to avoid clash with BaseEvent.event_id
    sender_id: str
    sender_display_name: str
    body: str
    room_display_name: str

class MatrixImageReceivedEvent(BaseEvent):
    """Event emitted when an image message is received from Matrix."""
    event_type: EventType = Field(EventType.MATRIX_IMAGE_RECEIVED, frozen=True)
    room_id: str
    event_id_matrix: str
    sender_id: str
    sender_display_name: str
    room_display_name: str
    image_url: str
    body: Optional[str] = None
    image_info: Optional[Dict[str, Any]] = None

class SendMatrixMessageCommand(BaseEvent):
    event_type: EventType = Field(EventType.SEND_MATRIX_MESSAGE_COMMAND, frozen=True)
    room_id: str
    text: str
    reply_to_event_id: Optional[str] = None # Added from test

class AIInferenceRequestEvent(BaseEvent):
    event_type: EventType = Field(EventType.AI_INFERENCE_REQUEST, frozen=True) # Changed from "ai_inference_request"
    request_id: str 
    reply_to_service_event: str 
    original_request_payload: Dict[str, Any] = Field(default_factory=dict)
    
    model_name: str
    messages_payload: List[Dict[str, Any]] 
    tools: Optional[List[Dict[str, Any]]] = None 
    tool_choice: Optional[str] = None 

# --- Pydantic models for nested structures, if not already defined ---
# These were mentioned as potentially missing in the test plan.
class ToolFunction(BaseModel):
    name: str
    arguments: Any # Changed from str to Any

class ToolCall(BaseModel): # Defined based on test_event_definitions.py usage
    id: str
    type: Literal["function"] = "function"
    function: ToolFunction

    # If function_name and function_args are direct fields in some contexts:
    # function_name: Optional[str] = None 
    # function_args: Optional[str] = None

    # @model_validator(mode='before')
    # def _populate_function_details(cls, values):
    #     if 'function' in values and isinstance(values['function'], dict):
    #         values['function_name'] = values['function'].get('name')
    #         values['function_args'] = values['function'].get('arguments')
    #     return values

class AIInferenceResponseEvent(BaseEvent):
    event_type: EventType = Field(EventType.AI_INFERENCE_RESPONSE, frozen=True) # Changed from "ai_inference_response"
    request_id: str 
    original_request_payload: Dict[str, Any] = Field(default_factory=dict)
    
    success: bool
    text_response: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None # Changed to use Pydantic ToolCall
    error_message: Optional[str] = None
    # Added response_topic from test
    response_topic: Optional[str] = None


class OpenRouterInferenceRequestEvent(AIInferenceRequestEvent):
    event_type: EventType = Field(EventType.OPEN_ROUTER_INFERENCE_REQUEST, frozen=True) # Changed from "openrouter_inference_request"
    # Fields from test: original_request_payload_event_id, original_request_event_id, event_type_to_respond_to
    # These seem to map to original_request_payload, request_id, and reply_to_service_event respectively.
    # For clarity, if these are distinct, they should be added. Assuming mapping for now.
    # original_request_payload_event_id: Optional[str] = None # Example if needed
    # original_request_event_id: Optional[str] = None         # Example if needed
    # event_type_to_respond_to: Optional[str] = None          # Example if needed


class OpenRouterInferenceResponseEvent(AIInferenceResponseEvent):
    event_type: EventType = Field(EventType.OPEN_ROUTER_INFERENCE_RESPONSE, frozen=True) # Changed from "openrouter_inference_response"
    # Fields from test: original_request_payload_event_id, event_type_to_respond_to
    # original_request_payload_event_id: Optional[str] = None # Example if needed
    # event_type_to_respond_to: Optional[str] = None          # Example if needed


class OllamaInferenceRequestEvent(AIInferenceRequestEvent):
    event_type: EventType = Field(EventType.OLLAMA_INFERENCE_REQUEST, frozen=True)
    # Similar to OpenRouter, map or add distinct fields if necessary
    # original_request_payload_event_id: Optional[str] = None 
    # original_request_event_id: Optional[str] = None         
    # event_type_to_respond_to: Optional[str] = None


class OllamaInferenceResponseEvent(AIInferenceResponseEvent):
    event_type: EventType = Field(EventType.OLLAMA_INFERENCE_RESPONSE, frozen=True)
    # original_request_payload_event_id: Optional[str] = None 
    # event_type_to_respond_to: Optional[str] = None

class ActivateListeningEvent(BaseEvent):
    event_type: EventType = Field(EventType.ACTIVATE_LISTENING, frozen=True) # Changed from "activate_listening_event"
    room_id: str
    # Renamed from triggering_event_id to match test
    activation_message_event_id: str 
    # Fields from definition not in test: triggering_sender_display_name, triggering_message_body
    # Keeping them as optional as per original definition
    triggering_sender_display_name: Optional[str] = None
    triggering_message_body: Optional[str] = None


class DeactivateListeningEvent(BaseEvent): # New model based on test
    event_type: EventType = Field(EventType.DEACTIVATE_LISTENING, frozen=True)
    room_id: str

class BatchedUserMessage(BaseModel): # Defined based on test_event_definitions.py
    user_id: str
    content: str
    event_id: str


class ProcessMessageBatchCommand(BaseEvent):
    event_type: EventType = Field(EventType.PROCESS_MESSAGE_BATCH_COMMAND, frozen=True)
    room_id: str
    # Added messages_in_batch from test
    messages_in_batch: List[BatchedUserMessage]


class SummaryGeneratedEvent(BaseEvent): 
    event_type: EventType = Field(EventType.SUMMARY_GENERATED, frozen=True) # Changed from "summary_generated_event"
    room_id: str
    summary_text: str
    # Renamed from last_event_id_in_summary to match test
    last_event_id_summarized: str


class ReactToMessageCommand(BaseEvent):
    event_type: EventType = Field(EventType.REACT_TO_MESSAGE_COMMAND, frozen=True)
    room_id: str
    # Renamed from target_event_id to match test
    event_id_to_react_to: str 
    reaction_key: str


class SendReplyCommand(BaseEvent): # This seems to be a duplicate of SendMatrixMessageCommand if reply_to_event_id is supported there
    event_type: EventType = Field(EventType.SEND_REPLY_COMMAND, frozen=True)
    room_id: str
    text: str
    reply_to_event_id: str


class BotDisplayNameReadyEvent(BaseEvent):
    event_type: EventType = Field(EventType.BOT_DISPLAY_NAME_READY, frozen=True)
    display_name: str
    user_id: str

class ImageCaptionGeneratedEvent(BaseEvent):
    """Event containing an image caption generated by an AI model."""
    event_type: EventType = Field(EventType.IMAGE_CAPTION_GENERATED, frozen=True)
    room_id: str
    caption_text: str
    original_event_id: str


class SetTypingIndicatorCommand(BaseEvent):
    event_type: EventType = Field(EventType.SET_TYPING_INDICATOR_COMMAND, frozen=True)
    room_id: str
    typing: bool
    timeout: int = 10000


class SetPresenceCommand(BaseEvent):
    event_type: EventType = Field(EventType.SET_PRESENCE_COMMAND, frozen=True)
    presence: Literal["online", "offline", "unavailable"]
    status_msg: Optional[str] = None


# --- Tool Related Event Definitions ---
class HistoricalMessage(BaseModel): # Defined based on test_event_definitions.py
    role: Literal["system", "user", "assistant", "tool"]
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None # Uses Pydantic ToolCall
    event_id: Optional[str] = None # Added event_id
    # If name is sometimes present for user/assistant roles:
    # name: Optional[str] = None 


class RequestAISummaryCommand(BaseEvent):
    event_type: EventType = Field(EventType.REQUEST_AI_SUMMARY_COMMAND, frozen=True)
    room_id: str
    force_update: bool = False
    messages_to_summarize: Optional[List[HistoricalMessage]] = None # Changed to use HistoricalMessage
    # Added from test
    current_summary_text: Optional[str] = None 
    last_event_id_in_messages: Optional[str] = None


class RequestMatrixRoomInfoCommand(BaseEvent):
    event_type: EventType = Field(EventType.REQUEST_MATRIX_ROOM_INFO_COMMAND, frozen=True)
    room_id: str
    aspects: List[str]
    response_event_topic: str
    original_tool_call_id: str


class MatrixRoomInfoResponseEvent(BaseEvent):
    event_type: EventType = Field(EventType.MATRIX_ROOM_INFO_RESPONSE_EVENT, frozen=True)
    room_id: str
    info: Dict[str, Any]
    original_request_event_id: str
    original_tool_call_id: str
    success: bool
    error_message: Optional[str] = None


# --- Tool Execution Events ---
class ExecuteToolRequest(BaseEvent):
    event_type: EventType = Field(EventType.EXECUTE_TOOL_REQUEST, frozen=True)
    room_id: str
    # tool_name: str # Field from definition, but test uses tool_call.function_name
    tool_call: ToolCall # Added from test, uses Pydantic ToolCall
    # original_ai_request_event_id: str # Field from test, maps to original_request_payload or a new field
    original_request_payload: Dict[str, Any] = Field(default_factory=dict) 
    llm_provider_info: Dict[str, Any] = Field(default_factory=dict)
    conversation_history_snapshot: List[HistoricalMessage] # Changed to use HistoricalMessage
    last_user_event_id: Optional[str]

    # @field_validator('tool_name', always=True)
    # def populate_tool_name_from_tool_call(cls, v, values):
    #     if not v and 'tool_call' in values and values['tool_call']:
    #         return values['tool_call'].function.name
    #     return v

class ToolRoleMessage(BaseModel): # Defined based on test_event_definitions.py
    role: Literal["tool"] = "tool"
    tool_call_id: str
    content: str
    # name: Optional[str] = None # If the function name should also be here

class ToolExecutionResponse(BaseEvent):
    event_type: EventType = Field(EventType.TOOL_EXECUTION_RESPONSE, frozen=True)
    original_tool_call_id: str 
    tool_name: str # Added tool_name field
    status: Literal["success", "failure", "requires_llm_followup"]
    # result_text: str # Field from test, maps to result_for_llm_history
    result_for_llm_history: str # Field from definition
    error_message: Optional[str] = None
    data_from_tool_for_followup_llm: Optional[Dict[str, Any]] = None
    original_request_payload: Dict[str, Any] = Field(default_factory=dict)
    # Added from test
    commands_to_publish: Optional[List[BaseEvent]] = None 
    # original_ai_request_event_id: Optional[str] = None # From test, map to original_request_payload

