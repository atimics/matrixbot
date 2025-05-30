"""Tool for posting casts to Farcaster."""

import logging
from typing import Dict, Any, Optional
from tool_base import ToolBase

logger = logging.getLogger(__name__)

class FarcasterCastTool(ToolBase):
    """Tool for posting casts to Farcaster."""
    
    def __init__(self):
        super().__init__(
            name="farcaster_cast",
            description="Post a cast (message) to Farcaster. Use this to share thoughts, respond to conversations, or engage with the Farcaster community.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text content of the cast to post. Maximum 320 characters.",
                        "maxLength": 320
                    },
                    "parent_url": {
                        "type": "string",
                        "description": "Optional. URL of the cast being replied to (for threaded conversations)."
                    },
                    "embeds": {
                        "type": "array",
                        "description": "Optional. Array of embed objects (links, images, etc.)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "url": {"type": "string", "description": "URL to embed"},
                                "metadata": {"type": "object", "description": "Additional metadata for the embed"}
                            }
                        }
                    }
                },
                "required": ["text"]
            }
        )
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the farcaster_cast tool."""
        try:
            text = kwargs.get("text", "").strip()
            parent_url = kwargs.get("parent_url")
            embeds = kwargs.get("embeds", [])
            
            if not text:
                return {
                    "success": False,
                    "error": "Cast text cannot be empty"
                }
            
            if len(text) > 320:
                return {
                    "success": False,
                    "error": f"Cast text too long ({len(text)} characters). Maximum is 320 characters."
                }
            
            # The actual execution will be handled by ActionExecutionService
            return {
                "success": True,
                "message": f"Cast posted successfully: '{text[:50]}{'...' if len(text) > 50 else ''}'"
            }
            
        except Exception as e:
            logger.error(f"Error in farcaster_cast tool: {e}")
            return {
                "success": False,
                "error": f"Failed to post cast: {str(e)}"
            }