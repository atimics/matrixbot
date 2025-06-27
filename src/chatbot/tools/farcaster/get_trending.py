"""
Tool for getting trending casts from Farcaster.
"""
import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface
from .utils import get_farcaster_observer, create_error_response, create_success_response, _summarize_cast_for_ai

logger = logging.getLogger(__name__)


class GetTrendingCastsTool(ToolInterface):
    """Tool to get trending casts from Farcaster."""
    
    @property
    def name(self) -> str:
        return "get_trending_casts"
    
    @property  
    def description(self) -> str:
        return "Get trending casts from Farcaster to see what's popular on the platform"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for the tool parameters."""
        return {
            "type": "object",
            "properties": {
                "channel_id": {
                    "type": "string",
                    "description": "Optional channel ID to get trending casts from a specific channel"
                },
                "timeframe_hours": {
                    "type": "integer",
                    "description": "Timeframe in hours to look back for trending casts (default: 24)",
                    "default": 24
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of trending casts to return (default: 10)",
                    "default": 10
                }
            },
            "required": []
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the tool to get trending casts."""
        farcaster_observer = get_farcaster_observer(context)
        if not farcaster_observer:
            return create_error_response("Farcaster observer not available")
            
        try:
            channel_id = params.get("channel_id")
            timeframe_hours = params.get("timeframe_hours", 24)
            limit = params.get("limit", 10)
            
            # Get trending casts using the observer
            if hasattr(farcaster_observer, "get_trending_casts"):
                result = await farcaster_observer.get_trending_casts(
                    channel_id=channel_id, timeframe_hours=timeframe_hours, limit=limit
                )
            else:
                # Fallback to API client if method missing
                if not farcaster_observer.api_client:
                    return create_error_response("Farcaster API client not initialized")
                    
                result = await farcaster_observer.api_client.get_trending_casts(
                    limit=limit, channel=channel_id
                )
                
            if result.get("casts"):
                cast_summaries = []
                for cast in result["casts"][:limit]:
                    summary = _summarize_cast_for_ai(cast)
                    cast_summaries.append(summary)
                    
                if context.world_state_manager:
                    context.world_state_manager.add_action_result(
                        action_type="get_trending_casts",
                        parameters={"channel_id": channel_id, "timeframe_hours": timeframe_hours, "limit": limit},
                        result="success",
                    )
                    
                    # Cache trending results
                    params_key = f"{channel_id or 'all'}_{timeframe_hours}_{limit}"
                    context.world_state_manager.cache_tool_result(
                        "get_trending_casts", params_key, {
                            "casts": cast_summaries,
                            "channel_id": channel_id,
                            "timeframe_hours": timeframe_hours,
                            "timestamp": time.time()
                        }
                    )
                    logger.info(f"Cached trending casts for channel: {channel_id or 'all'}")
                
                return create_success_response(
                    f"Retrieved {len(cast_summaries)} trending casts",
                    channel_id=channel_id,
                    timeframe_hours=timeframe_hours,
                    limit=limit,
                    casts=cast_summaries
                )
            else:
                return create_error_response("No trending casts found")
                
        except Exception as e:
            logger.error(f"Error in GetTrendingCastsTool: {e}", exc_info=True)
            return create_error_response(str(e))
