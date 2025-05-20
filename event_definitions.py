import time

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field

class BaseEvent(BaseModel):
    event_type: str = Field(..., description="The type of the event")
    timestamp: float = Field(default_factory=time.time, description="Event creation timestamp")

    @classmethod
    def get_event_type(cls) -> str:
        """Return the default event type for this class."""
        if hasattr(cls, "model_fields"):
            return cls.model_fields["event_type"].default  # type: ignore[attr-defined]
        return cls.__fields__["event_type"].default  # type: ignore[attr-defined]

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
    messages_payload: List[Dict[str, str]]

class AIInferenceResponseEvent(BaseEvent):
    event_type: str = "ai_inference_response"
    request_id: str # Correlates to AIInferenceRequestEvent
    original_request_payload: Dict[str, Any] = {} # Passed through from request
    
    success: bool
    text_response: Optional[str] = None
    error_message: Optional[str] = None

class ActivateListeningEvent(BaseEvent):
    event_type: str = "activate_listening_event"
    room_id: str
    triggering_event_id: str # The event_id of the message that triggered activation

class ProcessMessageBatchCommand(BaseEvent):
    event_type: str = "process_message_batch_command"
    room_id: str

class GenerateSummaryRequestEvent(BaseEvent):
    event_type: str = "generate_summary_request_event"
    room_id: str
    force_update: bool = False
    # Potentially include messages_to_summarize if not fetched from memory by summarizer

class SummaryGeneratedEvent(BaseEvent): # Optional, if other services need to know
    event_type: str = "summary_generated_event"
    room_id: str
    summary_text: str
    last_event_id_in_summary: str

class BotDisplayNameReadyEvent(BaseEvent):
    event_type: str = "bot_display_name_ready"
    display_name: str