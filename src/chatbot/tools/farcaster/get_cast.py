"""
Tool for getting specific Farcaster casts by URL or hash.
"""
import hashlib
import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface
from .utils import get_farcaster_observer, create_error_response, create_success_response

logger = logging.getLogger(__name__)


class GetCastByUrlTool(ToolInterface):
    """Tool to get a specific cast by its URL or hash."""
    
    @property
    def name(self) -> str:
        return "get_cast_by_url"

    @property
    def description(self) -> str:
        return "Get details about a specific Farcaster cast by its URL or hash"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for the tool parameters."""
        return {
            "type": "object",
            "properties": {
                "farcaster_url": {
                    "type": "string",
                    "description": "The cast URL (like https://warpcast.com/username/0x12345) or cast hash"
                }
            },
            "required": ["farcaster_url"]
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the tool to get cast details."""
        farcaster_observer = get_farcaster_observer(context)
        if not farcaster_observer:
            return create_error_response("Farcaster observer not available")
        
        # Extract parameter
        farcaster_url = params.get("farcaster_url")
        if not farcaster_url:
            return create_error_response("Missing required parameter 'farcaster_url'")
            
        try:
            # Call the observer's get_cast_by_url method directly
            result = await farcaster_observer.get_cast_by_url(
                farcaster_url=farcaster_url
            )
            
            if result.get("success") and result.get("cast"):
                cast = result["cast"]
                
                # Record action in world state and cache result
                if context.world_state_manager:
                    context.world_state_manager.add_action_result(
                        action_type="get_cast_by_url",
                        parameters={"farcaster_url": farcaster_url},
                        result="success",
                        timestamp=time.time(),
                    )
                    
                    # Cache the cast data for future reference
                    url_hash = hashlib.md5(farcaster_url.encode()).hexdigest()[:12]
                    context.world_state_manager.cache_tool_result(
                        "get_cast_by_url", url_hash, {
                            "cast": cast,
                            "url": farcaster_url,
                            "timestamp": time.time()
                        }
                    )
                    logger.info(f"Cached cast data for URL: {farcaster_url}")
                
                return create_success_response(
                    f"Retrieved cast from {farcaster_url}",
                    url=farcaster_url,
                    cast=cast
                )
            else:
                error_msg = result.get("error", f"Cast not found: {farcaster_url}")
                if "Invalid" in error_msg:
                    error_msg = f"Invalid Farcaster URL: {farcaster_url}"
                elif "not found" not in error_msg.lower():
                    error_msg = f"Cast not found: {farcaster_url}"
                    
                return create_error_response(error_msg)
                
        except Exception as e:
            logger.error(f"Error in GetCastByUrlTool: {e}", exc_info=True)
            return create_error_response(str(e))
