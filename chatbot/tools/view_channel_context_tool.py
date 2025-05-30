#!/usr/bin/env python3
"""
View Channel Context Tool

Tool for viewing the context of any channel (Matrix room, Farcaster home, Farcaster notifications).
This allows the AI to see recent messages from any channel in the unified system.
"""

from typing import Dict, Any, List
import json
from tool_base import AbstractTool, ToolResult
from event_definitions import BaseEvent
import logging

logger = logging.getLogger(__name__)

class ViewChannelContextEvent(BaseEvent):
    """Event to request channel context."""
    
    def __init__(self, channel_id: str, limit: int = 20, **kwargs):
        super().__init__(**kwargs)
        self.channel_id = channel_id
        self.limit = limit

class ViewChannelContextTool(AbstractTool):
    """Tool to view context from any channel in the unified system."""
    
    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "view_channel_context",
                "description": "View recent messages from any channel. Use 'farcaster:home' for Farcaster home feed, 'farcaster:notifications' for Farcaster notifications, or a Matrix room ID for Matrix rooms.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "channel_id": {
                            "type": "string",
                            "description": "Channel ID to view. Use 'farcaster:home' for home feed, 'farcaster:notifications' for notifications, or Matrix room ID for Matrix rooms"
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 50,
                            "default": 20,
                            "description": "Number of recent messages to view (default: 20)"
                        }
                    },
                    "required": ["channel_id"]
                }
            }
        }
    
    async def execute(self, room_id: str, arguments: Dict[str, Any], 
                     tool_call_id: str, **kwargs) -> ToolResult:
        channel_id = arguments.get("channel_id")
        limit = arguments.get("limit", 20)
        
        if not channel_id:
            return ToolResult(
                status="failure",
                result_for_llm_history="[Error: Missing required parameter 'channel_id']",
                error_message="Missing required parameter: channel_id"
            )
        
        # Create event to request channel context
        context_event = ViewChannelContextEvent(
            channel_id=channel_id,
            limit=limit
        )
        
        return ToolResult(
            status="success",
            result_for_llm_history=f"Requesting context for channel '{channel_id}' (last {limit} messages)...",
            commands_to_publish=[context_event]
        )