"""
Farcaster feed management tools using the service-oriented architecture.
"""
import logging
import time
import hashlib
from typing import Any, Dict, List

from ..base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class AddFarcasterFeedTool(ToolInterface):
    """Tool to add a custom Farcaster feed for monitoring (e.g., specific user, channel, or search query)."""
    
    @property
    def name(self) -> str:
        return "add_farcaster_feed"

    @property
    def description(self) -> str:
        return "Add a custom Farcaster feed to monitor. This can be a user timeline, channel, or search query that will be regularly checked and included in context."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for the tool parameters."""
        return {
            "type": "object",
            "properties": {
                "feed_type": {
                    "type": "string",
                    "enum": ["user_timeline", "channel", "search_query", "trending"],
                    "description": "Type of feed to monitor"
                },
                "feed_identifier": {
                    "type": "string", 
                    "description": "The identifier for the feed (username, channel ID, search term, etc.)"
                },
                "feed_name": {
                    "type": "string",
                    "description": "Human-readable name for this feed"
                },
                "update_frequency_minutes": {
                    "type": "integer",
                    "description": "How often to check this feed in minutes (default: 15)",
                    "default": 15
                },
                "max_items": {
                    "type": "integer",
                    "description": "Maximum number of items to keep from this feed (default: 10)",
                    "default": 10
                }
            },
            "required": ["feed_type", "feed_identifier", "feed_name"]
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the tool to add a custom feed."""
        # Use service-oriented approach
        social_service = context.get_social_service("farcaster")
        if not social_service:
            return {
                "status": "failure",
                "error": "Farcaster service not available",
                "timestamp": time.time()
            }

        feed_type = params.get("feed_type")
        feed_identifier = params.get("feed_identifier")
        feed_name = params.get("feed_name")
        update_frequency = params.get("update_frequency_minutes", 15)
        max_items = params.get("max_items", 10)

        if not all([feed_type, feed_identifier, feed_name]):
            return {
                "status": "failure",
                "error": "Missing required parameters: feed_type, feed_identifier, and feed_name are required",
                "timestamp": time.time()
            }

        try:
            # Create feed configuration
            feed_config = {
                "feed_id": hashlib.md5(f"{feed_type}_{feed_identifier}".encode()).hexdigest()[:12],
                "feed_type": feed_type,
                "feed_identifier": feed_identifier,
                "feed_name": feed_name,
                "update_frequency_minutes": update_frequency,
                "max_items": max_items,
                "created_timestamp": time.time(),
                "last_updated": 0,
                "status": "active"
            }

            # Store in world state manager
            if context.world_state_manager:
                # Add to custom feeds tracking
                if not hasattr(context.world_state_manager.state, 'custom_farcaster_feeds'):
                    context.world_state_manager.state.custom_farcaster_feeds = {}
                
                context.world_state_manager.state.custom_farcaster_feeds[feed_config["feed_id"]] = feed_config
                
                # Record this action
                context.world_state_manager.add_action_result(
                    action_type="add_farcaster_feed",
                    parameters=params,
                    result="success",
                )
                
                logger.debug(f"Added custom Farcaster feed: {feed_name} ({feed_type}: {feed_identifier})")
                
                return {
                    "status": "success",
                    "message": f"Successfully added Farcaster feed: {feed_name}",
                    "feed_id": feed_config["feed_id"],
                    "feed_config": feed_config,
                    "timestamp": time.time()
                }
            else:
                return {
                    "status": "failure",
                    "error": "World state manager not available",
                    "timestamp": time.time()
                }
                
        except Exception as e:
            logger.error(f"Error in AddFarcasterFeedTool: {e}", exc_info=True)
            return {
                "status": "failure",
                "error": f"Error adding feed: {str(e)}",
                "timestamp": time.time()
            }


class ListFarcasterFeedsTool(ToolInterface):
    """Tool to list all currently monitored Farcaster feeds."""
    
    @property
    def name(self) -> str:
        return "list_farcaster_feeds"

    @property
    def description(self) -> str:
        return "List all currently monitored Farcaster feeds including their status and recent activity."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for the tool parameters."""
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the tool to list all feeds."""
        try:
            feeds_summary = []
            
            # Get custom feeds if they exist
            if context.world_state_manager and hasattr(context.world_state_manager.state, 'custom_farcaster_feeds'):
                custom_feeds = context.world_state_manager.state.custom_farcaster_feeds
                for feed_id, feed_config in custom_feeds.items():
                    feeds_summary.append({
                        "feed_id": feed_id,
                        "feed_name": feed_config.get("feed_name"),
                        "feed_type": feed_config.get("feed_type"),
                        "feed_identifier": feed_config.get("feed_identifier"),
                        "status": feed_config.get("status", "active"),
                        "last_updated": feed_config.get("last_updated", 0),
                        "update_frequency_minutes": feed_config.get("update_frequency_minutes", 15)
                    })
            
            # Add ecosystem token holders feed
            if (context.world_state_manager and 
                context.world_state_manager.state.monitored_token_holders):
                holders_count = len(context.world_state_manager.state.monitored_token_holders)
                feeds_summary.append({
                    "feed_id": "ecosystem_token_holders",
                    "feed_name": "Ecosystem Token Holders",
                    "feed_type": "token_holders",
                    "feed_identifier": "top_holders",
                    "status": "active",
                    "holders_count": holders_count,
                    "note": "Built-in feed for ecosystem token top holders"
                })
            
            return {
                "status": "success",
                "feeds": feeds_summary,
                "total_feeds": len(feeds_summary),
                "timestamp": time.time()
            }
            
        except Exception as e:
            logger.error(f"Error in ListFarcasterFeedsTool: {e}", exc_info=True)
            return {
                "status": "failure",
                "error": f"Error listing feeds: {str(e)}",
                "timestamp": time.time()
            }


class RemoveFarcasterFeedTool(ToolInterface):
    """Tool to remove a custom Farcaster feed from monitoring."""
    
    @property
    def name(self) -> str:
        return "remove_farcaster_feed"

    @property
    def description(self) -> str:
        return "Remove a custom Farcaster feed from monitoring."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        """Return the JSON schema for the tool parameters."""
        return {
            "type": "object",
            "properties": {
                "feed_id": {
                    "type": "string",
                    "description": "The ID of the feed to remove"
                }
            },
            "required": ["feed_id"]
        }

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
        """Execute the tool to remove a feed."""
        feed_id = params.get("feed_id")
        
        if not feed_id:
            return {
                "status": "failure",
                "error": "Missing required parameter: feed_id",
                "timestamp": time.time()
            }

        try:
            if (context.world_state_manager and 
                hasattr(context.world_state_manager.state, 'custom_farcaster_feeds') and
                feed_id in context.world_state_manager.state.custom_farcaster_feeds):
                
                feed_config = context.world_state_manager.state.custom_farcaster_feeds[feed_id]
                feed_name = feed_config.get("feed_name", feed_id)
                
                # Remove the feed
                del context.world_state_manager.state.custom_farcaster_feeds[feed_id]
                
                # Record this action
                context.world_state_manager.add_action_result(
                    action_type="remove_farcaster_feed",
                    parameters=params,
                    result="success",
                )
                
                logger.debug(f"Removed custom Farcaster feed: {feed_name} ({feed_id})")
                
                return {
                    "status": "success",
                    "message": f"Successfully removed Farcaster feed: {feed_name}",
                    "feed_id": feed_id,
                    "timestamp": time.time()
                }
            else:
                return {
                    "status": "failure",
                    "error": f"Feed with ID '{feed_id}' not found",
                    "timestamp": time.time()
                }
                
        except Exception as e:
            logger.error(f"Error in RemoveFarcasterFeedTool: {e}", exc_info=True)
            return {
                "status": "failure",
                "error": f"Error removing feed: {str(e)}",
                "timestamp": time.time()
            }
