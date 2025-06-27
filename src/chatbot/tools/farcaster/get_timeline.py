"""
Tool for getting user timelines from Farcaster.
"""
import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface
from .utils import get_farcaster_observer, create_error_response, create_success_response, _summarize_cast_for_ai

logger = logging.getLogger(__name__)


class GetUserTimelineTool(ToolInterface):
    """
    Tool for fetching a user's timeline (recent casts) from Farcaster.
    """

    @property
    def name(self) -> str:
        return "get_user_timeline"

    @property
    def description(self) -> str:
        return "Fetch recent casts from a specific user's timeline on Farcaster. Use this to see what someone has been posting recently."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "user_identifier": {
                    "type": "string",
                    "description": "Username (without @) or FID of the user whose timeline to fetch"
                },
                "limit": {
                    "type": "integer",
                    "description": "Number of casts to retrieve (default: 10, max: 50)",
                    "default": 10
                }
            },
            "required": ["user_identifier"]
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the get user timeline action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Get Farcaster observer through ServiceRegistry
        farcaster_observer = get_farcaster_observer(context)
        if not farcaster_observer:
            return create_error_response("Farcaster integration (observer) not configured.")

        # Extract and validate parameters
        user_identifier = params.get("user_identifier")
        limit = params.get("limit", 10)

        if not user_identifier:
            return create_error_response("Missing required parameter 'user_identifier'")

        try:
            limit = int(limit)
            if limit < 1 or limit > 50:
                limit = min(max(limit, 1), 50)  # Clamp to valid range
        except (ValueError, TypeError):
            limit = 10

        try:
            result = await farcaster_observer.get_user_casts(
                user_identifier=user_identifier, limit=limit
            )

            # Check if the observer operation was successful
            if result.get("success", True):  # Default to True for backward compatibility
                logger.info(f"Retrieved {len(result.get('casts', []))} casts for user {user_identifier}")
                
                # Create AI-optimized summaries of the casts
                cast_summaries = [
                    _summarize_cast_for_ai(cast) for cast in result.get("casts", [])
                ]
                
                # Store timeline data in world state for persistent access
                if context.world_state_manager and result.get("user_info"):
                    try:
                        fid = result.get("user_info", {}).get("fid")
                        if fid:
                            timeline_cache_data = {
                                "casts": cast_summaries,
                                "last_fetched": time.time(),
                                "fetched_by_tool": "get_user_timeline",
                                "limit": limit,
                                "query_params": {
                                    "user_identifier": user_identifier,
                                    "limit": limit
                                }
                            }
                            
                            # Update user details with cached timeline
                            context.world_state_manager.update_farcaster_user_timeline_cache(
                                str(fid), timeline_cache_data
                            )
                            
                            # Also cache for general tool result retrieval
                            params_key = f"{user_identifier}_{limit}"
                            context.world_state_manager.cache_tool_result(
                                "get_user_timeline", params_key, {
                                    "casts": cast_summaries,
                                    "user_info": result.get("user_info"),
                                    "timestamp": time.time()
                                }
                            )
                            
                            logger.info(f"Cached timeline data for Farcaster user FID {fid}")
                    except Exception as cache_error:
                        logger.warning(f"Failed to cache timeline data: {cache_error}")
                
                return create_success_response(
                    f"Retrieved {len(cast_summaries)} casts for user {user_identifier}",
                    user_identifier=user_identifier,
                    casts=cast_summaries,  # Use summarized data
                    user_info=result.get("user_info"),
                    count=len(cast_summaries)
                )
            else:
                error_msg = result.get("error", "Unknown error from observer")
                logger.warning(f"Observer returned error for user {user_identifier}: {error_msg}")
                return create_error_response(error_msg)
                
        except Exception as e:
            logger.error(f"Error in GetUserTimelineTool: {e}", exc_info=True)
            return create_error_response(str(e))
