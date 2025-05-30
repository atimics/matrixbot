#!/usr/bin/env python3
"""
Farcaster Channel Update Tool

Tool for updating Farcaster channels (home feed and notifications) in the unified channel system.
This allows the AI to manually refresh Farcaster content and see the context.
"""

from typing import Dict, Any, List
import json
from tool_base import AbstractTool, ToolResult
from event_definitions import BaseEvent
import logging

logger = logging.getLogger(__name__)

class UpdateFarcasterChannelEvent(BaseEvent):
    """Event to request Farcaster channel update."""
    
    def __init__(self, channel_type: str, limit: int = 25, **kwargs):
        super().__init__(**kwargs)
        self.channel_type = channel_type  # 'home' or 'notifications'
        self.limit = limit

class UpdateFarcasterChannelTool(AbstractTool):
    """Tool to update Farcaster channels with latest content."""
    
    def get_definition(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "update_farcaster_channel",
                "description": "Update a Farcaster channel (home feed or notifications) with the latest content. Use this to get fresh context from Farcaster before responding to questions about it.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "channel_type": {
                            "type": "string",
                            "enum": ["home", "notifications"],
                            "description": "Which Farcaster channel to update: 'home' for home feed, 'notifications' for mentions/replies"
                        },
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 50,
                            "default": 25,
                            "description": "Number of items to fetch (default: 25)"
                        }
                    },
                    "required": ["channel_type"]
                }
            }
        }
    
    async def execute(self, room_id: str, arguments: Dict[str, Any], 
                     tool_call_id: str, **kwargs) -> ToolResult:
        channel_type = arguments.get("channel_type")
        limit = arguments.get("limit", 25)
        
        if not channel_type:
            return ToolResult(
                status="failure",
                result_for_llm_history="[Error: Missing required parameter 'channel_type']",
                error_message="Missing required parameter: channel_type"
            )
        
        if channel_type not in ["home", "notifications"]:
            return ToolResult(
                status="failure", 
                result_for_llm_history=f"[Error: Invalid channel_type '{channel_type}'. Must be 'home' or 'notifications']",
                error_message=f"Invalid channel_type: {channel_type}"
            )
        
        # Create event to trigger Farcaster channel update
        update_event = UpdateFarcasterChannelEvent(
            channel_type=channel_type,
            limit=limit
        )
        
        return ToolResult(
            status="success",
            result_for_llm_history=f"Requested update of Farcaster {channel_type} channel (limit: {limit}). The channel will be refreshed with latest content.",
            commands_to_publish=[update_event]
        )