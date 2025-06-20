"""
Farcaster discovery and research tools.
"""
import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


def _summarize_cast_for_ai(cast_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create an AI-optimized summary of a cast, removing verbose metadata.

    Args:
        cast_data: Full cast data dictionary from asdict() conversion

    Returns:
        Compact cast summary suitable for AI context
    """
    # Extract essential information only
    summary = {
        "id": cast_data.get("id"),
        "sender": cast_data.get("sender_username") or cast_data.get("sender"),
        "content": cast_data.get("content", "")[:200] + "..." if len(cast_data.get("content", "")) > 200 else cast_data.get("content", ""),
        "timestamp": cast_data.get("timestamp"),
        "engagement": {
            "likes": cast_data.get("metadata", {}).get("reactions", {}).get("likes_count", 0),
            "recasts": cast_data.get("metadata", {}).get("reactions", {}).get("recasts_count", 0),
            "replies": cast_data.get("metadata", {}).get("replies_count", 0)
        },
        "user_info": {
            "username": cast_data.get("sender_username"),
            "display_name": cast_data.get("sender_display_name"),
            "followers": cast_data.get("sender_follower_count"),
            "power_badge": cast_data.get("metadata", {}).get("power_badge", False)
        }
    }

    # Add reply context if it's a reply
    if cast_data.get("reply_to"):
        summary["reply_to"] = cast_data.get("reply_to")

    # Add channel if it's in a specific channel
    channel_id = cast_data.get("channel_id", "")
    if ":" in channel_id and not channel_id.endswith("_all"):
        # Extract meaningful channel name (e.g., "farcaster:trending_all:chatbfg" -> "chatbfg")
        parts = channel_id.split(":")
        if len(parts) > 2:
            summary["channel"] = parts[-1]

    return summary


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

        # Try service-oriented approach first, then fallback to direct attribute access
        farcaster_service = None
        
        # Service registry approach
        if hasattr(context, 'service_registry') and context.service_registry:
            farcaster_service = context.service_registry.get_social_service("farcaster")
        
        # Fallback to direct attribute access for backward compatibility
        if not farcaster_service and hasattr(context, 'farcaster_observer'):
            farcaster_service = getattr(context, 'farcaster_observer', None)
        
        if not farcaster_service:
            error_msg = "Farcaster service not available."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        user_identifier = params.get("user_identifier")
        limit = params.get("limit", 10)

        if not user_identifier:
            error_msg = "Missing required parameter 'user_identifier'"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            limit = int(limit)
            if limit < 1 or limit > 50:
                limit = min(max(limit, 1), 50)  # Clamp to valid range
        except (ValueError, TypeError):
            limit = 10

        try:
            result = await farcaster_service.get_user_casts(
                user_identifier=user_identifier, limit=limit
            )

            # Check if the service operation was successful
            if result.get("success", True):  # Default to True for backward compatibility
                logger.info(
                    f"Retrieved {len(result.get('casts', []))} casts for user {user_identifier}"
                )
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
                
                return {
                    "status": "success",
                    "user_identifier": user_identifier,
                    "casts": cast_summaries,  # Use summarized data
                    "user_info": result.get("user_info"),
                    "count": len(cast_summaries),
                    "timestamp": time.time(),
                }
            else:
                error_msg = result.get("error", "Unknown error from service")
                logger.warning(
                    f"Service returned error for user {user_identifier}: {error_msg}"
                )
                return {
                    "status": "failure",
                    "error": error_msg,
                    "timestamp": time.time(),
                }
        except Exception as e:
            logger.error(f"Error in GetUserTimelineTool: {e}", exc_info=True)
            return {
                "status": "failure", 
                "error": str(e),
                "timestamp": time.time(),
            }


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
        # Try service-oriented approach first, then fallback to direct attribute access
        farcaster_service = None
        
        # Service registry approach
        if hasattr(context, 'service_registry') and context.service_registry:
            farcaster_service = context.service_registry.get_social_service("farcaster")
        
        # Fallback to direct attribute access for backward compatibility
        if not farcaster_service and hasattr(context, 'farcaster_observer'):
            farcaster_service = getattr(context, 'farcaster_observer', None)
        
        if not farcaster_service:
            return {
                "status": "failure",
                "error": "Farcaster service not available",
                "timestamp": time.time()
            }
            
        try:
            results = await farcaster_service.collect_world_state_now()
            
            if results.get("success"):
                total = results.get("total_messages", 0)
                breakdown = []
                for data_type, count in results.items():
                    if data_type not in ["total_messages", "success"] and count > 0:
                        breakdown.append(f"{data_type}: {count}")
                
                summary = f"✅ Collected {total} messages"
                if breakdown:
                    summary += f" ({', '.join(breakdown)})"
                    
                return {
                    "status": "success",
                    "message": summary,
                    "total_messages": total,
                    "timestamp": time.time()
                }
            else:
                error = results.get("error", "Unknown error")
                return {
                    "status": "failure",
                    "error": f"World state collection failed: {error}",
                    "timestamp": time.time()
                }
                
        except Exception as e:
            logger.error(f"Error in CollectWorldStateTool: {e}", exc_info=True)
            return {
                "status": "failure",
                "error": f"Error collecting world state: {str(e)}",
                "timestamp": time.time()
            }


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
        # For test compatibility, expose top-level keys as well as properties
        schema = {
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
        # Add top-level keys for test compatibility
        schema["timeframe_hours"] = schema["properties"]["timeframe_hours"]
        schema["limit"] = schema["properties"]["limit"]
        return schema

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the tool to get trending casts."""
        # Try service-oriented approach first, then fallback to direct attribute access
        farcaster_service = None
        
        # Service registry approach
        if hasattr(context, 'service_registry') and context.service_registry:
            farcaster_service = context.service_registry.get_social_service("farcaster")
        
        # Fallback to direct attribute access for backward compatibility
        if not farcaster_service and hasattr(context, 'farcaster_observer'):
            farcaster_service = getattr(context, 'farcaster_observer', None)
        
        if not farcaster_service:
            return {
                "status": "failure",
                "error": "Farcaster service not available",
                "timestamp": time.time()
            }
            
        try:
            channel_id = params.get("channel_id")
            timeframe_hours = params.get("timeframe_hours", 24)
            limit = params.get("limit", 10)
            
            # Get trending casts using the service
            result = await farcaster_service.get_trending_casts(
                channel_id=channel_id, timeframe_hours=timeframe_hours, limit=limit
            )
                
            # Check if the service operation was successful
            if result.get("success", True):  # Default to True for backward compatibility
                cast_list = result.get("casts", [])
                if cast_list:
                    cast_summaries = []
                    for cast in cast_list[:limit]:
                        # Handle both dict and object formats
                        if hasattr(cast, '__dict__'):
                            cast_data = cast.__dict__
                        else:
                            cast_data = cast
                        summary = _summarize_cast_for_ai(cast_data)
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
                    
                    return {
                        "status": "success",
                        "channel_id": channel_id,
                        "timeframe_hours": timeframe_hours,
                        "limit": limit,
                        "casts": cast_summaries,
                        "timestamp": time.time(),
                    }
                else:
                    return {
                        "status": "failure",
                        "error": "No trending casts found",
                        "timestamp": time.time(),
                    }
            else:
                error_msg = result.get("error", "Service returned error")
                logger.warning(f"Get trending casts failed: {error_msg}")
                return {
                    "status": "failure",
                    "error": error_msg,
                    "timestamp": time.time(),
                }
        except Exception as e:
            logger.error(f"Error in GetTrendingCastsTool: {e}", exc_info=True)
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time(),
            }


class SearchCastsTool(ToolInterface):
    """Tool to search for casts on Farcaster."""
    
    @property
    def name(self) -> str:
        return "search_casts"

    @property
    def description(self) -> str:
        return "Search for casts on Farcaster by query text"

    def __init__(self):
        self.parameters = [
            {
                "name": "query",
                "type": "string", 
                "description": "Search query to find relevant casts",
                "required": True,
            },
            {
                "name": "limit",
                "type": "integer",
                "description": "Maximum number of results to return (default: 10)",
                "required": False,
            },
        ]

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
            return {"status": "failure", "error": "Missing required parameter 'query'", "timestamp": time.time()}
            
        # Try service-oriented approach first, then fallback to direct attribute access
        farcaster_service = None
        
        # Service registry approach
        if hasattr(context, 'service_registry') and context.service_registry:
            farcaster_service = context.service_registry.get_social_service("farcaster")
        
        # Fallback to direct attribute access for backward compatibility
        if not farcaster_service and hasattr(context, 'farcaster_observer'):
            farcaster_service = getattr(context, 'farcaster_observer', None)
        
        if not farcaster_service:
            return {"status": "failure", "error": "Farcaster service not available", "timestamp": time.time()}
            
        try:
            # Call the service's search_casts method directly
            result = await farcaster_service.search_casts(
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
                    import hashlib
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
                    if query_hash not in context.world_state_manager.state.search_cache:
                        context.world_state_manager.state.search_cache[query_hash] = {}
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
                
                return {
                    "status": "success",
                    "query": query,
                    "channel_id": channel_id,
                    "casts": cast_summaries,
                    "timestamp": time.time(),
                }
            else:
                error_msg = result.get("error", f"No casts found for query: {query}")
                logger.warning(f"Search failed for query '{query}': {error_msg}")
                return {"status": "failure", "error": error_msg, "timestamp": time.time()}
                
        except Exception as e:
            logger.error(f"Error in SearchCastsTool: {e}", exc_info=True)
            return {
                "status": "failure", 
                "error": f"SearchCastsTool error: {str(e)}",
                "timestamp": time.time(),
            }


class GetCastByUrlTool(ToolInterface):
    """Tool to get a specific cast by its URL or hash."""
    
    @property
    def name(self) -> str:
        return "get_cast_by_url"

    @property
    def description(self) -> str:
        return "Get details about a specific Farcaster cast by its URL or hash"

    def __init__(self):
        self.parameters = [
            {
                "name": "farcaster_url",
                "type": "string",
                "description": "The cast URL (like https://warpcast.com/username/0x12345) or cast hash",
                "required": True,
            },
        ]

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
        # Try service-oriented approach first, then fallback to direct attribute access
        farcaster_service = None
        
        # Service registry approach
        if hasattr(context, 'service_registry') and context.service_registry:
            farcaster_service = context.service_registry.get_social_service("farcaster")
        
        # Fallback to direct attribute access for backward compatibility
        if not farcaster_service and hasattr(context, 'farcaster_observer'):
            farcaster_service = getattr(context, 'farcaster_observer', None)
        
        if not farcaster_service:
            return {
                "status": "failure",
                "error": "Farcaster service not available",
                "timestamp": time.time()
            }
        
        # Extract parameter
        farcaster_url = params.get("farcaster_url")
        if not farcaster_url:
            return {
                "status": "failure",
                "error": "Missing required parameter 'farcaster_url'",
                "timestamp": time.time()
            }
            
        try:
            # Call the service's get_cast_by_url method directly
            result = await farcaster_service.get_cast_by_url(
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
                    import hashlib
                    url_hash = hashlib.md5(farcaster_url.encode()).hexdigest()[:12]
                    context.world_state_manager.cache_tool_result(
                        "get_cast_by_url", url_hash, {
                            "cast": cast,
                            "url": farcaster_url,
                            "timestamp": time.time()
                        }
                    )
                    logger.info(f"Cached cast data for URL: {farcaster_url}")
                
                return {
                    "status": "success",
                    "url": farcaster_url,
                    "cast": cast,
                    "timestamp": time.time(),
                }
            else:
                error_msg = result.get("error", f"Cast not found: {farcaster_url}")
                if "Invalid" in error_msg:
                    error_msg = f"Invalid Farcaster URL: {farcaster_url}"
                elif "not found" not in error_msg.lower():
                    error_msg = f"Cast not found: {farcaster_url}"
                    
                return {
                    "status": "failure",
                    "error": error_msg,
                    "timestamp": time.time(),
                }
                
        except Exception as e:
            logger.error(f"Error in GetCastByUrlTool: {e}", exc_info=True)
            return {
                "status": "failure", 
                "error": str(e),
                "timestamp": time.time(),
            }
