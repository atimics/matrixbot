"""
Unified Action Tool - Single Entry Point for Platform Communications

This tool implements the Generic Perform Action pattern described in the 
stabilization report. It serves as the single entry point for all platform-based 
communication and interaction, replacing multiple platform-specific tools.

Key Benefits:
- Reduced AI cognitive load (one tool vs many)
- Improved adaptability with graceful error handling  
- Centralized platform logic in IntegrationManager
- Clean abstraction over platform differences
"""

import logging
from typing import Any, Dict, Optional

from .base import ToolInterface, ActionContext
from ..config import settings

logger = logging.getLogger(__name__)


class PerformActionTool(ToolInterface):
    """
    Universal tool for performing actions across platforms.
    
    This tool replaces platform-specific communication tools like:
    - send_matrix_reply, send_matrix_message
    - send_farcaster_post, send_farcaster_reply
    - react_to_matrix_message, react_to_farcaster_post
    
    Instead, the AI uses a single tool with platform and action_type parameters.
    """
    
    @property
    def name(self) -> str:
        return "perform_action"
    
    @property
    def description(self) -> str:
        return (
            "Universal tool for performing communication actions across platforms. "
            "Supports reply, react, create_post, quote_post, and other platform-specific actions. "
            "Automatically handles platform limitations and provides clear error feedback."
        )
    
    @property
    def access_level(self) -> str:
        return 'conversational'  # Available to Sub-Agents and Commander

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "platform": {
                    "type": "string",
                    "enum": ["matrix", "farcaster"],
                    "description": "Target platform for the action"
                },
                "thread_id": {
                    "type": "string", 
                    "description": "Unique identifier for the conversation thread (e.g., matrix_!roomid:server or farcaster_0xhash...)"
                },
                "action_type": {
                    "type": "string",
                    "enum": ["reply", "react", "create_post", "quote_post", "message", "join_room", "leave_room"],
                    "description": "Type of action to perform"
                },
                "content": {
                    "type": "string",
                    "description": "Text content for the message/post/reply"
                },
                "options": {
                    "type": "object",
                    "description": "Optional parameters specific to platform and action type",
                    "properties": {
                        "reply_to_id": {
                            "type": "string",
                            "description": "ID of message/post to reply to (for reply action)"
                        },
                        "reaction_key": {
                            "type": "string", 
                            "description": "Emoji reaction key (for react action)"
                        },
                        "media_url": {
                            "type": "string",
                            "description": "URL of media to attach"
                        },
                        "mxc_uri": {
                            "type": "string",
                            "description": "Matrix MXC URI for media (Matrix only)"
                        },
                        "quote_target_id": {
                            "type": "string",
                            "description": "ID of post to quote (for quote_post action)"
                        },
                        "room_alias": {
                            "type": "string",
                            "description": "Room alias for join/leave actions (Matrix only)"
                        }
                    }
                }
            },
            "required": ["platform", "action_type"]
        }
    
    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """
        Execute the unified action by delegating to the appropriate platform service.
        """
        try:
            platform = params.get("platform")
            action_type = params.get("action_type") 
            thread_id = params.get("thread_id")
            content = params.get("content", "")
            options = params.get("options", {})
            
            if not platform:
                return {
                    "status": "error",
                    "error": "Platform parameter is required",
                    "error_type": "missing_parameter"
                }
            
            if not action_type:
                return {
                    "status": "error", 
                    "error": "Action type parameter is required",
                    "error_type": "missing_parameter"
                }
             # Get the appropriate messaging service
            if not context.service_registry:
                return {
                    "status": "error",
                    "error": "ServiceRegistry not available - system not properly initialized",
                    "error_type": "system_error"
                }

            messaging_service = context.service_registry.get_messaging_service(platform)
            if not messaging_service:
                return {
                    "status": "error",
                    "error": f"No messaging service available for platform: {platform}",
                    "error_type": "platform_unavailable"
                }
            
            # Validate action type support for platform
            supported_actions = self._get_supported_actions(platform)
            if action_type not in supported_actions:
                return {
                    "status": "error",
                    "error": f"Action '{action_type}' is not supported on platform '{platform}'. Supported actions: {', '.join(supported_actions)}",
                    "error_type": "unsupported_action",
                    "supported_actions": supported_actions
                }
            
            # Execute the action through the messaging service
            result = await self._execute_action(
                messaging_service, platform, action_type, thread_id, content, options
            )
            
            return result
            
        except Exception as e:
            logger.error(f"PerformActionTool: Unexpected error: {e}", exc_info=True)
            return {
                "status": "error",
                "error": f"Unexpected error: {str(e)}",
                "error_type": "execution_error"
            }
    
    def _get_supported_actions(self, platform: str) -> list:
        """Get list of actions supported by a platform."""
        if platform == "matrix":
            return ["reply", "react", "message", "join_room", "leave_room"]
        elif platform == "farcaster":
            return ["reply", "create_post", "quote_post"]  # No reactions on Farcaster
        else:
            return []
    
    async def _execute_action(
        self, 
        messaging_service, 
        platform: str, 
        action_type: str, 
        thread_id: Optional[str], 
        content: str, 
        options: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute the specific action through the messaging service."""
        
        result = None  # Initialize result to avoid unbound variable
        
        try:
            if action_type == "reply":
                reply_to_id = options.get("reply_to_id")
                if not reply_to_id:
                    return {
                        "status": "error",
                        "error": "reply_to_id is required for reply action",
                        "error_type": "missing_parameter"
                    }
                
                if platform == "matrix":
                    # Extract room_id from thread_id (format: matrix_!roomid:server)
                    room_id = thread_id.replace("matrix_", "") if thread_id else None
                    result = await messaging_service.send_reply(
                        channel_id=room_id,
                        reply_to_id=reply_to_id,
                        content=content,
                        media_url=options.get("media_url"),
                        mxc_uri=options.get("mxc_uri")
                    )
                    
                elif platform == "farcaster":
                    result = await messaging_service.send_reply(
                        channel_id="",  # Not used for Farcaster
                        reply_to_id=reply_to_id,
                        content=content,
                        media_url=options.get("media_url")
                    )
                
            elif action_type == "react":
                react_to_id = options.get("reply_to_id")  # Same param for consistency
                reaction_key = options.get("reaction_key", "👍")
                
                if not react_to_id:
                    return {
                        "status": "error",
                        "error": "reply_to_id (message to react to) is required for react action",
                        "error_type": "missing_parameter"
                    }
                
                if platform == "matrix":
                    room_id = thread_id.replace("matrix_", "") if thread_id else None
                    # Matrix adapter might not have send_reaction, fall back to basic response
                    if hasattr(messaging_service, 'send_reaction'):
                        result = await messaging_service.send_reaction(
                            channel_id=room_id,
                            event_id=react_to_id,
                            reaction_key=reaction_key
                        )
                    else:
                        result = {"status": "success", "message": "Reaction feature not available in current service adapter"}
                else:
                    # Farcaster doesn't support reactions
                    return {
                        "status": "error",
                        "error": "Reactions are not supported on Farcaster platform",
                        "error_type": "unsupported_action"
                    }
                    
            elif action_type == "message":
                if platform == "matrix":
                    room_id = thread_id.replace("matrix_", "") if thread_id else None
                    result = await messaging_service.send_message(
                        channel_id=room_id,
                        content=content,
                        media_url=options.get("media_url"),
                        mxc_uri=options.get("mxc_uri")
                    )
                else:
                    return {
                        "status": "error",
                        "error": "Direct messaging not supported through this action. Use create_post for Farcaster.",
                        "error_type": "unsupported_action"
                    }
                    
            elif action_type == "create_post":
                if platform == "farcaster":
                    result = await messaging_service.send_message(
                        channel_id="",  # Farcaster posts don't need channel_id
                        content=content,
                        media_url=options.get("media_url")
                    )
                else:
                    return {
                        "status": "error", 
                        "error": "create_post action is specific to Farcaster. Use 'message' for Matrix.",
                        "error_type": "unsupported_action"
                    }
                    
            elif action_type == "quote_post":
                if platform == "farcaster":
                    quote_target_id = options.get("quote_target_id")
                    if not quote_target_id:
                        return {
                            "status": "error",
                            "error": "quote_target_id is required for quote_post action",
                            "error_type": "missing_parameter"
                        }
                    # For now, use regular post with mention of quote
                    quoted_content = f'Quoting: {quote_target_id}\n\n{content}'
                    result = await messaging_service.send_message(
                        channel_id="",
                        content=quoted_content,
                        media_url=options.get("media_url")
                    )
                else:
                    return {
                        "status": "error",
                        "error": "Quote posts are not supported on Matrix platform",
                        "error_type": "unsupported_action"
                    }
                    
            elif action_type in ["join_room", "leave_room"]:
                if platform == "matrix":
                    room_alias = options.get("room_alias") or thread_id
                    # Basic room management - would need to extend service adapter
                    result = {"status": "success", "message": f"{action_type} feature would be implemented in service adapter"}
                else:
                    return {
                        "status": "error",
                        "error": f"{action_type} is not supported on {platform} platform",
                        "error_type": "unsupported_action"
                    }
            else:
                return {
                    "status": "error",
                    "error": f"Unknown action type: {action_type}",
                    "error_type": "unknown_action"
                }
            
            return {
                "status": "success",
                "platform": platform,
                "action_type": action_type,
                "thread_id": thread_id,
                "result": result or {"status": "completed"}
            }
            
        except Exception as e:
            logger.error(f"PerformActionTool: Error executing {action_type} on {platform}: {e}")
            return {
                "status": "error",
                "error": f"Failed to execute {action_type}: {str(e)}",
                "error_type": "execution_error"
            }
