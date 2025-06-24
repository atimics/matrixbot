"""
Tool for searching casts on Farcaster.
"""
import hashlib
import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface
from .utils import get_farcaster_observer, create_error_response, create_success_response, _summarize_cast_for_ai

logger = logging.getLogger(__name__)


class SearchCastsTool(ToolInterface):
    """Tool to search for casts on Farcaster."""
    
    @property
    def name(self) -> str:
        return "search_casts"
    
    @property
    def description(self) -> str:
        return "Search for casts on Farcaster by query text"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for the tool parameters."""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to find relevant casts"
                },
                "channel_id": {
                    "type": "string",
                    "description": "Optional Farcaster channel ID to scope the search"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return",
                    "default": 10
                }
            },
            "required": ["query"]
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the tool to search for casts with given parameters."""
        query = params.get("query")
        limit = params.get("limit", 10)
        channel_id = params.get("channel_id")
        
        if not query:
            return create_error_response("Missing required parameter 'query'")
            
        farcaster_observer = get_farcaster_observer(context)
        if not farcaster_observer:
            return create_error_response("Farcaster observer not available")
            
        try:
            # Call the observer's search_casts method directly
            result = await farcaster_observer.search_casts(
                query=query,
                channel_id=channel_id,
                limit=min(limit, 25)
            )
            
            if result.get("success") and result.get("casts"):
                cast_summaries = []
                for cast in result["casts"][:limit]:
                    summary = _summarize_cast_for_ai(cast)
                    cast_summaries.append(summary)
                
                # Record action in world state and cache results
                if context.world_state_manager:
                    context.world_state_manager.add_action_result(
                        action_type="search_casts",
                        parameters={"query": query, "limit": limit, "channel_id": channel_id},
                        result="success",
                    )
                    
                    # Cache search results for future reference
                    query_hash = hashlib.md5(f"{query}_{channel_id or 'all'}_{limit}".encode()).hexdigest()[:12]
                    search_cache_data = {
                        "query": query,
                        "channel_id": channel_id,
                        "casts": cast_summaries,
                        "result_count": len(cast_summaries),
                        "timestamp": time.time(),
                        "fetched_by_tool": "search_casts"
                    }
                    
                    # Store in search cache
                    if hasattr(context.world_state_manager.state, 'search_cache'):
                        if not hasattr(context.world_state_manager.state.search_cache, 'get'):
                            context.world_state_manager.state.search_cache = {}
                        context.world_state_manager.state.search_cache[query_hash] = search_cache_data
                    
                    # Also cache as general tool result
                    params_key = f"{query}_{channel_id or 'all'}_{limit}"
                    context.world_state_manager.cache_tool_result(
                        "search_casts", params_key, {
                            "casts": cast_summaries,
                            "query": query,
                            "channel_id": channel_id,
                            "timestamp": time.time()
                        }
                    )
                    
                    logger.info(f"Cached search results for query: {query} (hash: {query_hash})")
                
                return create_success_response(
                    f"Found {len(cast_summaries)} casts for query: {query}",
                    query=query,
                    channel_id=channel_id,
                    casts=cast_summaries
                )
            else:
                return create_error_response(f"No casts found for query: {query}")
                
        except Exception as e:
            logger.error(f"Error in SearchCastsTool: {e}", exc_info=True)
            return create_error_response(str(e))
