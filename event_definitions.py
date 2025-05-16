import time

from typing import List, Dict, Optional, Literal, Any
from pydantic import BaseModel, Field

class BaseEvent(BaseModel):
    event_type: str = Field(..., description="The type of the event")
    timestamp: float = Field(default_factory=time.time, description="Event creation timestamp")

class MatrixMessageReceivedEvent(BaseEvent):
    event_type: str = "matrix_message_received"
    room_id: str
    event_id: str
    sender_id: str
    sender_display_name: str
    body: str
    room_display_name: str # Added for context

class SendMatrixMessageCommand(BaseEvent):
    event_type: str = "send_matrix_message_command"
    room_id: str
    text: str

class AIInferenceRequestEvent(BaseEvent):
    event_type: str = "ai_inference_request"
    request_id: str # For correlating responses
    reply_to_service_event: str # Event type the original requester is waiting for
    original_request_payload: Dict[str, Any] = {} # To carry room_id, etc.
    
    model_name: str
    messages_payload: List[Dict[str, Any]] # Changed from List[Dict[str, str]]
    tools: Optional[List[Dict[str, Any]]] = None # Added for tool calling
    tool_choice: Optional[str] = None # Added for tool calling, e.g., "auto", "none", or {"type": "function", "function": {"name": "my_function"}}

class AIInferenceResponseEvent(BaseEvent):
    event_type: str = "ai_inference_response"
    request_id: str # Correlates to AIInferenceRequestEvent
    original_request_payload: Dict[str, Any] = {} # Passed through from request
    
    success: bool
    text_response: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None # Added for tool calling
    error_message: Optional[str] = None

class OpenRouterInferenceRequestEvent(AIInferenceRequestEvent):
    event_type: str = "openrouter_inference_request"

class OpenRouterInferenceResponseEvent(AIInferenceResponseEvent):
    event_type: str = "openrouter_inference_response"

class OllamaInferenceRequestEvent(AIInferenceRequestEvent):
    event_type: str = "ollama_inference_request"

class OllamaInferenceResponseEvent(AIInferenceResponseEvent):
    event_type: str = "ollama_inference_response"

class ActivateListeningEvent(BaseEvent):
    event_type: str = "activate_listening_event"
    room_id: str
    triggering_event_id: str # The event_id of the message that triggered activation

class ProcessMessageBatchCommand(BaseEvent):
    event_type: str = "process_message_batch_command"
    room_id: str

# class GenerateSummaryRequestEvent(BaseEvent): # No longer needed, RoomLogicService directly calls for AI summary
#     event_type: str = "generate_summary_request_event"
#     room_id: str
#     force_update: bool = False
#     # Potentially include messages_to_summarize if not fetched from memory by summarizer

class SummaryGeneratedEvent(BaseEvent): # Optional, if other services need to know
    event_type: str = "summary_generated_event"
    room_id: str
    summary_text: str
    last_event_id_in_summary: str

class ReactToMessageCommand(BaseEvent):
    event_type: str = "react_to_message_command"
    room_id: str
    target_event_id: str
    reaction_key: str

class SendReplyCommand(BaseEvent):
    event_type: str = "send_reply_command"
    room_id: str
    text: str
    reply_to_event_id: str

class BotDisplayNameReadyEvent(BaseEvent):
    event_type: str = "bot_display_name_ready"
    display_name: str

class SetTypingIndicatorCommand(BaseModel):
    """Command to instruct the Matrix Gateway to set the typing status."""
    event_type: Literal["set_typing_indicator_command"] = Field(default="set_typing_indicator_command", frozen=True)
    room_id: str
    typing: bool
    timeout: int = 10000 # Timeout in milliseconds (nio default is 10000ms = 10s)

class SetPresenceCommand(BaseModel):
    """Command to instruct the Matrix Gateway to set the bot's presence."""
    event_type: Literal["set_presence_command"] = Field(default="set_presence_command", frozen=True)
    presence: Literal["online", "offline", "unavailable"] # Nio uses these states
    status_msg: Optional[str] = None
    # Removed unused timeout field