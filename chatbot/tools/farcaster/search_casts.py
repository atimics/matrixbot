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
        return "Search for casts on Farcaster with enhanced semantic capabilities and filtering options"

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for the tool parameters."""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query with support for operators like +, |, *, \", -, before:, after:, etc. Examples: 'star wars', 'crypto + defi', 'after:2024-12-01'"
                },
                "channel_id": {
                    "type": "string",
                    "description": "Optional Farcaster channel ID to scope the search (e.g., 'degen', 'base')"
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of results to return (1-100)",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100
                },
                "mode": {
                    "type": "string",
                    "description": "Search mode: 'literal' (exact words), 'semantic' (meaning-based), 'hybrid' (combines both, default)",
                    "enum": ["literal", "semantic", "hybrid"],
                    "default": "hybrid"
                },
                "sort_type": {
                    "type": "string",
                    "description": "Sort results by: 'desc_chron' (newest first), 'algorithmic' (engagement + time, default)",
                    "enum": ["desc_chron", "algorithmic"],
                    "default": "algorithmic"
                },
                "author_fid": {
                    "type": "integer",
                    "description": "Search only casts by this specific Farcaster user ID",
                    "minimum": 1
                },
                "viewer_fid": {
                    "type": "integer", 
                    "description": "Personalize results for this viewer (respects their mutes/blocks)",
                    "minimum": 1
                },
                "parent_url": {
                    "type": "string",
                    "description": "Search within specific parent URL context (for conversations)"
                }
            },
            "required": ["query"]
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the tool to search for casts with enhanced parameters."""
        query = params.get("query")
        limit = params.get("limit", 10)
        channel_id = params.get("channel_id")
        mode = params.get("mode", "hybrid")
        sort_type = params.get("sort_type", "algorithmic") 
        author_fid = params.get("author_fid")
        viewer_fid = params.get("viewer_fid")
        parent_url = params.get("parent_url")
        
        if not query:
            return create_error_response("Missing required parameter 'query'")
            
        farcaster_observer = get_farcaster_observer(context)
        if not farcaster_observer:
            return create_error_response("Farcaster observer not available")
            
        try:
            # Call the observer's search_casts method with enhanced parameters
            result = await farcaster_observer.search_casts(
                query=query,
                channel_id=channel_id,
                limit=min(limit, 25),
                mode=mode,
                sort_type=sort_type,
                author_fid=author_fid,
                viewer_fid=viewer_fid,
                parent_url=parent_url
            )
            
            if result.get("success") and result.get("casts"):
                cast_summaries = []
                for cast in result["casts"][:limit]:
                    summary = _summarize_cast_for_ai(cast)
                    cast_summaries.append(summary)
                
                # Record action in world state and cache results
                if context.world_state_manager:
                    # Updated to include all search parameters for better caching
                    search_params = {
                        "query": query, 
                        "limit": limit, 
                        "channel_id": channel_id,
                        "mode": mode,
                        "sort_type": sort_type,
                        "author_fid": author_fid,
                        "viewer_fid": viewer_fid,
                        "parent_url": parent_url
                    }
                    context.world_state_manager.add_action_result(
                        action_type="search_casts",
                        parameters=search_params,
                        result="success",
                    )
                    
                    # Cache search results for future reference with enhanced parameters
                    cache_key_parts = [
                        query,
                        channel_id or 'all',
                        str(limit),
                        mode,
                        sort_type,
                        str(author_fid) if author_fid else 'any_author',
                        str(viewer_fid) if viewer_fid else 'no_viewer',
                        parent_url or 'no_parent'
                    ]
                    query_hash = hashlib.md5("_".join(cache_key_parts).encode()).hexdigest()[:12]
                    search_cache_data = {
                        "query": query,
                        "channel_id": channel_id,
                        "mode": mode,
                        "sort_type": sort_type,
                        "author_fid": author_fid,
                        "viewer_fid": viewer_fid,
                        "parent_url": parent_url,
                        "casts": cast_summaries,
                        "result_count": len(cast_summaries),
                        "timestamp": time.time(),
                        "fetched_by_tool": "search_casts_enhanced"
                    }
                    
                    # Store in search cache
                    if hasattr(context.world_state_manager.state, 'search_cache'):
                        if not hasattr(context.world_state_manager.state.search_cache, 'get'):
                            context.world_state_manager.state.search_cache = {}
                        context.world_state_manager.state.search_cache[query_hash] = search_cache_data
                    
                    # Also cache as general tool result
                    params_key = "_".join(cache_key_parts)
                    context.world_state_manager.cache_tool_result(
                        "search_casts", params_key, {
                            "casts": cast_summaries,
                            "search_params": search_params,
                            "timestamp": time.time()
                        }
                    )
                    
                    logger.info(f"Cached enhanced search results for query: {query} (hash: {query_hash})")
                
                # Enhanced success message with search parameters used
                search_details = f"mode={mode}, sort={sort_type}"
                if author_fid:
                    search_details += f", author_fid={author_fid}"
                if viewer_fid:
                    search_details += f", viewer_fid={viewer_fid}"
                if channel_id:
                    search_details += f", channel={channel_id}"
                    
                return create_success_response(
                    f"Found {len(cast_summaries)} casts for query: {query} ({search_details})",
                    query=query,
                    channel_id=channel_id,
                    casts=cast_summaries
                )
            else:
                return create_error_response(f"No casts found for query: {query}")
                
        except Exception as e:
            logger.error(f"Error in SearchCastsTool: {e}", exc_info=True)
            return create_error_response(str(e))
