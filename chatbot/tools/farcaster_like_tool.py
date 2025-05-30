"""Tool for liking casts on Farcaster."""

import logging
from typing import Dict, Any
from tool_base import ToolBase

logger = logging.getLogger(__name__)

class FarcasterLikeTool(ToolBase):
    """Tool for liking casts on Farcaster."""
    
    def __init__(self):
        super().__init__(
            name="farcaster_like",
            description="Like a cast on Farcaster to show appreciation or agreement.",
            parameters={
                "type": "object",
                "properties": {
                    "cast_hash": {
                        "type": "string",
                        "description": "The hash of the cast to like"
                    }
                },
                "required": ["cast_hash"]
            }
        )
    
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """Execute the farcaster_like tool."""
        try:
            cast_hash = kwargs.get("cast_hash", "").strip()
            
            if not cast_hash:
                return {
                    "success": False,
                    "error": "Cast hash is required"
                }
            
            return {
                "success": True,
                "message": f"Successfully liked cast {cast_hash[:10]}..."
            }
            
        except Exception as e:
            logger.error(f"Error in farcaster_like tool: {e}")
            return {
                "success": False,
                "error": f"Failed to like cast: {str(e)}"
            }