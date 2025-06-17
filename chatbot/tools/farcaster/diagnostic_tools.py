"""
Farcaster diagnostic and monitoring tools.
"""
import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class FarcasterDiagnosticTool(ToolInterface):
    """
    Tool for diagnosing Farcaster service status and connectivity.
    """

    @property
    def name(self) -> str:
        return "check_farcaster_status"

    @property
    def description(self) -> str:
        return "Check the current status and health of the Farcaster integration, including service availability, API connectivity, and recent activity."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "detailed": {
                    "type": "boolean",
                    "description": "Whether to include detailed diagnostic information",
                    "default": False
                }
            },
            "required": []
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Farcaster diagnostic check.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")
        
        detailed = params.get("detailed", False)
        diagnosis = {
            "status": "unknown",
            "timestamp": time.time(),
            "service_registry": {},
            "observer_status": {},
            "api_connectivity": {},
            "recent_activity": {}
        }

        # Check service registry
        try:
            social_service = context.get_social_service("farcaster")
            if not social_service:
                diagnosis["service_registry"] = {
                    "registered": False,
                    "error": "Farcaster service not found in service registry"
                }
                diagnosis["status"] = "service_not_registered"
            else:
                diagnosis["service_registry"] = {
                    "registered": True,
                    "service_id": social_service.service_id,
                    "service_type": social_service.service_type
                }
                
                # Check service availability
                try:
                    is_available = await social_service.is_available()
                    diagnosis["service_registry"]["available"] = is_available
                    
                    if is_available:
                        diagnosis["status"] = "healthy"
                    else:
                        diagnosis["status"] = "service_unavailable"
                        
                except Exception as e:
                    diagnosis["service_registry"]["availability_error"] = str(e)
                    diagnosis["status"] = "availability_check_failed"

        except Exception as e:
            diagnosis["service_registry"] = {
                "error": f"Exception checking service registry: {str(e)}"
            }
            diagnosis["status"] = "registry_error"

        # Check observer status if available
        try:
            if hasattr(context, 'farcaster_observer') and context.farcaster_observer:
                observer = context.farcaster_observer
                diagnosis["observer_status"] = {
                    "exists": True,
                    "enabled": getattr(observer, 'enabled', False),
                    "api_client_exists": hasattr(observer, 'api_client') and observer.api_client is not None,
                    "bot_fid": getattr(observer, 'bot_fid', None),
                    "signer_uuid": getattr(observer, 'signer_uuid', None)
                }
                
                if detailed:
                    diagnosis["observer_status"]["api_key_configured"] = bool(getattr(observer, 'api_key', None))
                    
                    # Test API connectivity if available
                    if hasattr(observer, 'api_client') and observer.api_client:
                        try:
                            network_status = observer.api_client.get_network_status()
                            diagnosis["api_connectivity"] = {
                                "network_available": network_status.get("is_available", False),
                                "consecutive_failures": network_status.get("consecutive_failures", 0),
                                "seconds_since_last_success": network_status.get("seconds_since_last_success", 0),
                                "rate_limits": network_status.get("rate_limits", {})
                            }
                        except Exception as e:
                            diagnosis["api_connectivity"] = {
                                "error": f"Failed to check API connectivity: {str(e)}"
                            }
            else:
                diagnosis["observer_status"] = {
                    "exists": False,
                    "error": "Farcaster observer not available in context"
                }
        except Exception as e:
            diagnosis["observer_status"] = {
                "error": f"Exception checking observer: {str(e)}"
            }

        # Check recent activity from world state
        try:
            if context.world_state_manager:
                world_state = context.world_state_manager.get_state()
                
                # Count recent Farcaster actions
                recent_actions = []
                if hasattr(world_state, 'action_history'):
                    current_time = time.time()
                    for action in world_state.action_history[-10:]:  # Last 10 actions
                        if 'farcaster' in action.get('action_type', '').lower():
                            action_age = current_time - action.get('timestamp', 0)
                            if action_age < 3600:  # Last hour
                                recent_actions.append({
                                    "action_type": action.get('action_type'),
                                    "result": action.get('result'),
                                    "minutes_ago": round(action_age / 60, 1)
                                })
                
                diagnosis["recent_activity"] = {
                    "actions_last_hour": len(recent_actions),
                    "recent_actions": recent_actions if detailed else len(recent_actions)
                }
        except Exception as e:
            diagnosis["recent_activity"] = {
                "error": f"Failed to check recent activity: {str(e)}"
            }

        # Generate summary message
        if diagnosis["status"] == "healthy":
            message = "✅ Farcaster integration is healthy and operational"
        elif diagnosis["status"] == "service_not_registered":
            message = "❌ Farcaster service not registered - integration may not be configured"
        elif diagnosis["status"] == "service_unavailable":
            message = "⚠️ Farcaster service registered but not available - check API credentials"
        else:
            message = f"❌ Farcaster integration has issues - status: {diagnosis['status']}"

        return {
            "status": "success",
            "message": message,
            "farcaster_health": diagnosis["status"],
            "diagnosis": diagnosis,
            "timestamp": time.time()
        }


class FarcasterRecentPostsTool(ToolInterface):
    """
    Tool for checking recent posts to verify posting functionality.
    """

    @property
    def name(self) -> str:
        return "check_farcaster_recent_posts"

    @property
    def description(self) -> str:
        return "Check recent posts from the bot on Farcaster to verify posting functionality is working."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of recent posts to check (default: 5)",
                    "default": 5
                }
            },
            "required": []
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the recent posts check.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")
        
        limit = params.get("limit", 5)
        
        try:
            # Get Farcaster observer
            if not (hasattr(context, 'farcaster_observer') and context.farcaster_observer):
                return {
                    "status": "failure",
                    "error": "❌ Farcaster observer not available",
                    "timestamp": time.time()
                }
            
            observer = context.farcaster_observer
            
            # Get recent posts
            recent_posts = await observer.get_recent_own_posts(limit=limit)
            
            if not recent_posts:
                return {
                    "status": "success",
                    "message": "⚠️ No recent posts found - posting may not be working or bot is new",
                    "recent_posts": [],
                    "post_count": 0,
                    "timestamp": time.time()
                }
            
            # Process posts for summary
            post_summaries = []
            current_time = time.time()
            
            for post in recent_posts[:limit]:
                try:
                    post_time = post.get("timestamp", "")
                    if isinstance(post_time, str):
                        from datetime import datetime
                        post_datetime = datetime.fromisoformat(post_time.replace('Z', '+00:00'))
                        post_timestamp = int(post_datetime.timestamp())
                        minutes_ago = round((current_time - post_timestamp) / 60, 1)
                    else:
                        minutes_ago = "unknown"
                    
                    post_summaries.append({
                        "content_preview": post.get("text", "")[:100] + ("..." if len(post.get("text", "")) > 100 else ""),
                        "hash": post.get("hash", "unknown"),
                        "minutes_ago": minutes_ago,
                        "replies_count": post.get("replies", {}).get("count", 0),
                        "likes_count": post.get("reactions", {}).get("likes_count", 0)
                    })
                except Exception as e:
                    logger.warning(f"Error processing post summary: {e}")
                    post_summaries.append({
                        "content_preview": "Error processing post",
                        "error": str(e)
                    })
            
            message = f"✅ Found {len(recent_posts)} recent posts - Farcaster posting appears to be working!"
            
            return {
                "status": "success",
                "message": message,
                "recent_posts": post_summaries,
                "post_count": len(recent_posts),
                "timestamp": time.time()
            }
            
        except Exception as e:
            error_msg = f"❌ Error checking recent posts: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return {
                "status": "failure",
                "error": error_msg,
                "timestamp": time.time()
            }
