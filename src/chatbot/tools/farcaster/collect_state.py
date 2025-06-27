"""
Tool for collecting Farcaster world state data.
"""
import logging
from typing import Any, Dict

from ..base import ActionContext, ToolInterface
from .utils import get_farcaster_observer, create_error_response, create_success_response

logger = logging.getLogger(__name__)


class CollectWorldStateTool(ToolInterface):
    """Tool to manually trigger Farcaster world state collection."""
    
    @property
    def name(self) -> str:
        return "collect_farcaster_world_state"

    @property
    def description(self) -> str:
        return "Manually trigger collection of Farcaster world state data including trending casts, home timeline, DMs, and notifications for enhanced AI context"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for the tool parameters."""
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute world state collection."""
        farcaster_observer = get_farcaster_observer(context)
        if not farcaster_observer:
            return create_error_response("Farcaster observer not available")
            
        try:
            results = await farcaster_observer.collect_world_state_now()
            
            if results.get("success"):
                total = results.get("total_messages", 0)
                breakdown = []
                for data_type, count in results.items():
                    if data_type not in ["total_messages", "success"] and count > 0:
                        breakdown.append(f"{data_type}: {count}")
                
                summary = f"✅ Collected {total} messages"
                if breakdown:
                    summary += f" ({', '.join(breakdown)})"
                    
                return create_success_response(
                    summary,
                    total_messages=total
                )
            else:
                error = results.get("error", "Unknown error")
                return create_error_response(f"World state collection failed: {error}")
                
        except Exception as e:
            logger.error(f"Error in CollectWorldStateTool: {e}", exc_info=True)
            return create_error_response(f"Error collecting world state: {str(e)}")
