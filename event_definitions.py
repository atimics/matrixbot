from typing import List, Dict, Optional, Literal, Any
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timezone # Added datetime and timezone

# Helper function to generate a default UUID string if needed elsewhere,
# but Pydantic's default_factory is usually sufficient for default field values.

class BaseEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique identifier for the event") # Assuming uuid is imported or defined
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Event creation timestamp")
    event_type: str = Field(..., description="The type of the event")

    @field_validator('timestamp', mode='before')
    def ensure_timezone_aware(cls, v):
        if isinstance(v, datetime) and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        if isinstance(v, (int, float)): # Support for float timestamps
            return datetime.fromtimestamp(v, tz=timezone.utc)
        return v

    @classmethod
    def get_event_type(cls) -> str:
        """Return the default event type for this class."""
        if hasattr(cls, "model_fields"):
            return cls.model_fields["event_type"].default  # type: ignore[attr-defined]
        return cls.__fields__["event_type"].default  # type: ignore[attr-defined]

class MatrixMessageReceivedEvent(BaseEvent):
    event_type: str = Field("matrix_message_received", frozen=True)
    room_id: str
    event_id_matrix: str # Renamed from event_id to avoid clash with BaseEvent.event_id
    sender_id: str
    sender_display_name: str
    body: str
    room_display_name: str

class SendMatrixMessageCommand(BaseEvent):
    event_type: str = Field("send_matrix_message_command", frozen=True)
    room_id: str
    text: str
    reply_to_event_id: Optional[str] = None # Added from test

class AIInferenceRequestEvent(BaseEvent):
    event_type: str = Field("ai_inference_request", frozen=True) # Changed from "ai_inference_request"
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
    event_type: str = Field("ai_inference_response", frozen=True) # Changed from "ai_inference_response"
    request_id: str 
    original_request_payload: Dict[str, Any] = Field(default_factory=dict)
    
    success: bool
    text_response: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = None # Changed to use Pydantic ToolCall
    error_message: Optional[str] = None
    # Added response_topic from test
    response_topic: Optional[str] = None


class OpenRouterInferenceRequestEvent(AIInferenceRequestEvent):
    event_type: str = Field("open_router_inference_request", frozen=True) # Changed from "openrouter_inference_request"
    # Fields from test: original_request_payload_event_id, original_request_event_id, event_type_to_respond_to
    # These seem to map to original_request_payload, request_id, and reply_to_service_event respectively.
    # For clarity, if these are distinct, they should be added. Assuming mapping for now.
    # original_request_payload_event_id: Optional[str] = None # Example if needed
    # original_request_event_id: Optional[str] = None         # Example if needed
    # event_type_to_respond_to: Optional[str] = None          # Example if needed


class OpenRouterInferenceResponseEvent(AIInferenceResponseEvent):
    event_type: str = Field("open_router_inference_response", frozen=True) # Changed from "openrouter_inference_response"
    # Fields from test: original_request_payload_event_id, event_type_to_respond_to
    # original_request_payload_event_id: Optional[str] = None # Example if needed
    # event_type_to_respond_to: Optional[str] = None          # Example if needed


class OllamaInferenceRequestEvent(AIInferenceRequestEvent):
    event_type: str = Field("ollama_inference_request", frozen=True)
    # Similar to OpenRouter, map or add distinct fields if necessary
    # original_request_payload_event_id: Optional[str] = None 
    # original_request_event_id: Optional[str] = None         
    # event_type_to_respond_to: Optional[str] = None


class OllamaInferenceResponseEvent(AIInferenceResponseEvent):
    event_type: str = Field("ollama_inference_response", frozen=True)
    # original_request_payload_event_id: Optional[str] = None 
    # event_type_to_respond_to: Optional[str] = None

class ActivateListeningEvent(BaseEvent):
    event_type: str = Field("activate_listening", frozen=True) # Changed from "activate_listening_event"
    room_id: str
    # Renamed from triggering_event_id to match test
    activation_message_event_id: str 
    # Fields from definition not in test: triggering_sender_display_name, triggering_message_body
    # Keeping them as optional as per original definition
    triggering_sender_display_name: Optional[str] = None
    triggering_message_body: Optional[str] = None


class DeactivateListeningEvent(BaseEvent): # New model based on test
    event_type: str = Field("deactivate_listening", frozen=True)
    room_id: str

class BatchedUserMessage(BaseModel): # Defined based on test_event_definitions.py
    user_id: str
    content: str
    event_id: str


class ProcessMessageBatchCommand(BaseEvent):
    event_type: str = Field("process_message_batch_command", frozen=True)
    room_id: str
    # Added messages_in_batch from test
    messages_in_batch: List[BatchedUserMessage]


class SummaryGeneratedEvent(BaseEvent): 
    event_type: str = Field("summary_generated", frozen=True) # Changed from "summary_generated_event"
    room_id: str
    summary_text: str
    # Renamed from last_event_id_in_summary to match test
    last_event_id_summarized: str


class ReactToMessageCommand(BaseEvent):
    event_type: str = Field("react_to_message_command", frozen=True)
    room_id: str
    # Renamed from target_event_id to match test
    event_id_to_react_to: str 
    reaction_key: str


class SendReplyCommand(BaseEvent): # This seems to be a duplicate of SendMatrixMessageCommand if reply_to_event_id is supported there
    event_type: str = Field("send_reply_command", frozen=True)
    room_id: str
    text: str
    reply_to_event_id: str


class BotDisplayNameReadyEvent(BaseEvent):
    event_type: str = Field("bot_display_name_ready", frozen=True)
    display_name: str


class SetTypingIndicatorCommand(BaseEvent): # Changed from BaseModel to BaseEvent
    event_type: Literal["set_typing_indicator_command"] = Field("set_typing_indicator_command", frozen=True)
    room_id: str
    typing: bool
    timeout: int = 10000 


class SetPresenceCommand(BaseEvent): # Changed from BaseModel to BaseEvent
    event_type: Literal["set_presence_command"] = Field("set_presence_command", frozen=True)
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
    event_type: str = Field("request_ai_summary_command", frozen=True)
    room_id: str
    force_update: bool = False
    messages_to_summarize: Optional[List[HistoricalMessage]] = None # Changed to use HistoricalMessage
    # Added from test
    current_summary_text: Optional[str] = None 
    last_event_id_in_messages: Optional[str] = None


# --- Tool Execution Events ---
class ExecuteToolRequest(BaseEvent):
    event_type: str = Field("execute_tool_request", frozen=True)
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
    event_type: str = Field("tool_execution_response", frozen=True)
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


# Ensure uuid is available if used in default_factory for event_id
import uuid