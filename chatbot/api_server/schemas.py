"""
Pydantic models for API requests and responses.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class ToolStatusUpdate(BaseModel):
    enabled: bool


class ConfigUpdate(BaseModel):
    key: str
    value: Any


class NodeAction(BaseModel):
    action: str  # expand, collapse, pin, unpin, refresh_summary
    node_id: str
    force: bool = False


class SystemCommand(BaseModel):
    command: str  # start, stop, restart, reset_processing_mode, force_processing_mode
    parameters: Optional[Dict[str, Any]] = None


class IntegrationConfig(BaseModel):
    integration_type: str
    display_name: str
    config: Dict[str, Any]
    credentials: Dict[str, str] = {}


class IntegrationStatus(BaseModel):
    id: str
    integration_type: str
    display_name: str
    is_active: bool
    is_connected: bool
    status_details: Dict[str, Any]


class IntegrationTestRequest(BaseModel):
    integration_type: str
    config: Dict[str, Any]
    credentials: Dict[str, str] = {}


class MemoryEntry(BaseModel):
    platform: str
    user_identifier: str
    memory_text: str
    tags: Optional[List[str]] = None


class ResearchEntry(BaseModel):
    title: str
    content: str
    tags: Optional[List[str]] = None
    references: Optional[List[str]] = None


class MediaItem(BaseModel):
    url: str
    type: str  # "image" or "video"
    title: Optional[str] = None
    description: Optional[str] = None


class MessageBody(BaseModel):
    content: str
    room_id: Optional[str] = None
    channel_id: Optional[str] = None
    reply_to: Optional[str] = None
    media_url: Optional[str] = None


class ActionRequest(BaseModel):
    action_type: str
    parameters: Dict[str, Any]
    reason: Optional[str] = None


class DebugCommand(BaseModel):
    command: str
    parameters: Optional[Dict[str, Any]] = None


class StatusResponse(BaseModel):
    """Standard API response format"""
    status: str
    message: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    timestamp: str


class SetupStep(BaseModel):
    key: str
    question: str
    type: str = "text"  # text, password, select
    options: Optional[List[str]] = None
    validation: Optional[str] = None


class SetupSubmission(BaseModel):
    step_key: str
    value: Any  # Can be str, bool, int, etc.
