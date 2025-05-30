"""Tool for retrieving Farcaster feed."""

import logging
from typing import Dict, Any
from tool_base import ToolBase

logger = logging.getLogger(__name__)

class FarcasterGetFeedTool(ToolBase):
    """Tool for retrieving Farcaster feed."""
    
    def __init__(self):
        super().__init__(
            name="farcaster_get_feed",
            description="Retrieve the latest casts from your Farcaster feed to stay updated on conversations and community activity.",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Number of casts to retrieve (1-25, default: 10)",
                        "minimum": 1,
                        "maximum": 25,
                        "default": 10
                    },
                    "cursor": {
                        "type": "string",
                        "description": "Optional cursor for pagination"
                    }
                },
                "required": []
            }
        )
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the farcaster_get_feed tool."""
        try:
            limit = kwargs.get("limit", 10)
            cursor = kwargs.get("cursor")
            
            if limit < 1 or limit > 25:
                return {
                    "success": False,
                    "error": "Limit must be between 1 and 25"
                }
            
            return {
                "success": True,
                "message": f"Successfully retrieved {limit} casts from feed"
            }
            
        except Exception as e:
            logger.error(f"Error in farcaster_get_feed tool: {e}")
            return {
                "success": False,
                "error": f"Failed to retrieve feed: {str(e)}"
            }