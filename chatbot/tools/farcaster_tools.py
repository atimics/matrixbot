"""
Farcaster platform-specific tools.
"""
import logging
import time
from typing import Any, Dict

from .base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class SendFarcasterPostTool(ToolInterface):
    """
    Tool for sending new posts to Farcaster.
    """

    @property
    def name(self) -> str:
        return "send_farcaster_post"

    @property
    def description(self) -> str:
        return "Send a new post (cast) to Farcaster. Use this when you want to share something with the Farcaster community."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "content": "string - The text content of the cast to post",
            "channel": "string (optional) - The channel to post in (if not provided, posts to user's timeline)",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Farcaster post action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Check if Farcaster integration is available
        if not context.farcaster_observer:
            error_msg = "Farcaster integration (observer) not configured."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        content = params.get("content")
        channel = params.get("channel")  # Optional

        if not content:
            error_msg = "Missing required parameter 'content' for Farcaster post"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Prevent duplicate posts with identical content
        if (
            context.world_state_manager
            and context.world_state_manager.has_sent_farcaster_post(content)
        ):
            error_msg = "Already sent Farcaster post with identical content. Skipping duplicate."
            logger.warning(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # If observer supports scheduling (has a real asyncio.Queue), enqueue; otherwise, execute immediately
        import asyncio

        post_q = getattr(context.farcaster_observer, "post_queue", None)
        if isinstance(post_q, asyncio.Queue):
            try:
                # Record scheduling and get action_id for tracking
                action_id = None
                if context.world_state_manager:
                    action_id = context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"content": content, "channel": channel},
                        result="scheduled",
                    )
                
                context.farcaster_observer.schedule_post(content, channel, action_id)
                success_msg = "Scheduled Farcaster post via scheduler"
                logger.info(success_msg)
                return {
                    "status": "scheduled",
                    "message": success_msg,
                    "content": content,
                    "channel": channel,
                    "action_id": action_id,  # Return action_id for tracking
                    "timestamp": time.time(),
                }
            except Exception as e:
                error_msg = f"Error scheduling Farcaster post: {e}"
                logger.exception(error_msg)
                return {
                    "status": "failure",
                    "error": error_msg,
                    "timestamp": time.time(),
                }
        # Immediate execution fallback
        try:
            result = await context.farcaster_observer.post_cast(content, channel)
            logger.info(f"Farcaster observer post_cast returned: {result}")
            
            # Record this action in world state
            if context.world_state_manager:
                if result.get("success"):
                    cast_hash = result.get("cast", {}).get("hash")
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"content": content, "channel": channel, "cast_hash": cast_hash},
                        result="success",
                    )
                else:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"content": content, "channel": channel},
                        result=f"failure: {result.get('error', 'unknown')}",
                    )
            
            if result.get("success"):
                return {"status": "success", **result}
            else:
                return {
                    "status": "failure",
                    "error": result.get("error", "unknown"),
                    "timestamp": time.time(),
                }
        except Exception as e:
            error_msg = f"Error executing send_farcaster_post: {e}"
            logger.exception(error_msg)
            
            # Record this action failure in world state
            if context.world_state_manager:
                context.world_state_manager.add_action_result(
                    action_type=self.name,
                    parameters={"content": content, "channel": channel},
                    result=f"failure: {str(e)}",
                )
            
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class SendFarcasterReplyTool(ToolInterface):
    """
    Tool for replying to specific casts on Farcaster.
    """

    @property
    def name(self) -> str:
        return "send_farcaster_reply"

    @property
    def description(self) -> str:
        return "Reply to a specific cast on Farcaster. Use this when you want to respond directly to someone's cast."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "content": "string - The text content of the reply",
            "reply_to_hash": "string - The hash of the cast to reply to",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Farcaster reply action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Check if Farcaster integration is available
        if not context.farcaster_observer:
            error_msg = "Farcaster integration (observer) not configured."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        content = params.get("content")
        reply_to_hash = params.get("reply_to_hash")

        missing_params = []
        if not content:
            missing_params.append("content")
        if not reply_to_hash:
            missing_params.append("reply_to_hash")

        if missing_params:
            error_msg = f"Missing required parameters for Farcaster reply: {', '.join(missing_params)}"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Check if we've already replied to this cast
        if (
            context.world_state_manager
            and context.world_state_manager.has_replied_to_cast(reply_to_hash)
        ):
            error_msg = f"Already replied to cast {reply_to_hash}. Cannot reply to the same cast twice."
            logger.warning(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        import asyncio

        reply_q = getattr(context.farcaster_observer, "reply_queue", None)
        # If scheduling supported, enqueue
        if isinstance(reply_q, asyncio.Queue):
            try:
                # Record scheduling and get action_id for tracking
                action_id = None
                if context.world_state_manager:
                    action_id = context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"content": content, "reply_to_hash": reply_to_hash},
                        result="scheduled",
                    )
                
                context.farcaster_observer.schedule_reply(content, reply_to_hash, action_id)
                success_msg = f"Scheduled Farcaster reply to cast {reply_to_hash}"
                logger.info(success_msg)
                return {
                    "status": "scheduled",
                    "message": success_msg,
                    "reply_to_hash": reply_to_hash,
                    "content": content,
                    "action_id": action_id,  # Return action_id for tracking
                    "timestamp": time.time(),
                }
            except Exception as e:
                error_msg = f"Error scheduling Farcaster reply: {e}"
                logger.exception(error_msg)
                return {
                    "status": "failure",
                    "error": error_msg,
                    "timestamp": time.time(),
                }
        # Fallback immediate execution
        try:
            result = await context.farcaster_observer.reply_to_cast(
                content, reply_to_hash
            )
            logger.info(f"Farcaster observer reply_to_cast returned: {result}")
            
            # Record this action in world state for duplicate prevention
            if context.world_state_manager:
                if result.get("success"):
                    cast_hash = result.get("cast", {}).get("hash")
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"content": content, "reply_to_hash": reply_to_hash, "cast_hash": cast_hash},
                        result="success",
                    )
                else:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"content": content, "reply_to_hash": reply_to_hash},
                        result=f"failure: {result.get('error', 'unknown')}",
                    )
            
            if result.get("success"):
                return {"status": "success", **result}
            else:
                return {
                    "status": "failure",
                    "error": result.get("error", "unknown"),
                    "timestamp": time.time(),
                }
        except Exception as e:
            error_msg = f"Error executing send_farcaster_reply: {e}"
            logger.exception(error_msg)
            
            # Record this action failure in world state
            if context.world_state_manager:
                context.world_state_manager.add_action_result(
                    action_type=self.name,
                    parameters={"content": content, "reply_to_hash": reply_to_hash},
                    result=f"failure: {str(e)}",
                )
            
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class LikeFarcasterPostTool(ToolInterface):
    """
    Tool for liking (reacting to) posts on Farcaster.
    """

    @property
    def name(self) -> str:
        return "like_farcaster_post"

    @property
    def description(self) -> str:
        return "Like (react to) a specific cast on Farcaster. Use this to show appreciation for content you find valuable or interesting."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "cast_hash": "string - The hash of the cast to like",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Farcaster like action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Check if Farcaster integration is available
        if not context.farcaster_observer:
            error_msg = "Farcaster integration (observer) not configured."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        cast_hash = params.get("cast_hash")

        if not cast_hash:
            error_msg = "Missing required parameter for Farcaster like: cast_hash"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Check if we've already liked this cast
        if context.world_state_manager and context.world_state_manager.has_liked_cast(
            cast_hash
        ):
            error_msg = (
                f"Already liked cast {cast_hash}. Cannot like the same cast twice."
            )
            logger.warning(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Use the observer's like_cast method
            result = await context.farcaster_observer.like_cast(cast_hash)
            logger.info(f"Farcaster observer like_cast returned: {result}")

            # Record this action in world state
            if context.world_state_manager:
                if result.get("success"):
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"cast_hash": cast_hash},
                        result="success",
                    )
                else:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"cast_hash": cast_hash},
                        result=f"failure: {result.get('error', 'unknown')}",
                    )

            if result.get("success"):
                success_msg = f"Successfully liked Farcaster cast: {cast_hash}"
                logger.info(success_msg)

                return {
                    "status": "success",
                    "message": success_msg,
                    "cast_hash": cast_hash,
                    "timestamp": time.time(),
                }
            else:
                error_msg = f"Failed to like Farcaster cast via observer: {result.get('error', 'unknown error')}"
                logger.error(error_msg)
                return {
                    "status": "failure",
                    "error": error_msg,
                    "timestamp": time.time(),
                }

        except Exception as e:
            error_msg = f"Error executing {self.name}: {str(e)}"
            logger.exception(error_msg)
            
            # Record this action failure in world state
            if context.world_state_manager:
                context.world_state_manager.add_action_result(
                    action_type=self.name,
                    parameters={"cast_hash": cast_hash},
                    result=f"failure: {str(e)}",
                )
            
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class QuoteFarcasterPostTool(ToolInterface):
    """
    Tool for quote casting (reposting with commentary) on Farcaster.
    """

    @property
    def name(self) -> str:
        return "quote_farcaster_post"

    @property
    def description(self) -> str:
        return "Quote cast (repost with your own commentary) a specific cast on Farcaster. Use this to share someone's cast while adding your own thoughts or context."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "content": "string - Your commentary/thoughts to add to the quoted cast",
            "quoted_cast_hash": "string - The hash of the cast to quote",
            "channel": "string (optional) - The channel to post in (if not provided, posts to user's timeline)",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Farcaster quote cast action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Check if Farcaster integration is available
        if not context.farcaster_observer:
            error_msg = "Farcaster integration (observer) not configured."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        content = params.get("content")
        quoted_cast_hash = params.get("quoted_cast_hash")
        channel = params.get("channel")  # Optional

        missing_params = []
        if not content:
            missing_params.append("content")
        if not quoted_cast_hash:
            missing_params.append("quoted_cast_hash")

        if missing_params:
            error_msg = f"Missing required parameters for Farcaster quote cast: {', '.join(missing_params)}"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Check if we've already quoted this cast
        if context.world_state_manager and context.world_state_manager.has_quoted_cast(
            quoted_cast_hash
        ):
            error_msg = f"Already quoted cast {quoted_cast_hash}. Cannot quote the same cast twice."
            logger.warning(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Use the observer's quote_cast method
            result = await context.farcaster_observer.quote_cast(
                content, quoted_cast_hash, channel
            )
            logger.info(f"Farcaster observer quote_cast returned: {result}")

            # Record this action in world state
            if context.world_state_manager:
                if result.get("success"):
                    cast_hash = result.get("cast", {}).get("hash", result.get("cast_hash", "unknown"))
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"content": content, "quoted_cast_hash": quoted_cast_hash, "channel": channel, "cast_hash": cast_hash},
                        result="success",
                    )
                else:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"content": content, "quoted_cast_hash": quoted_cast_hash, "channel": channel},
                        result=f"failure: {result.get('error', 'unknown')}",
                    )

            if result.get("success"):
                cast_hash = result.get("cast_hash", "unknown")
                quoted_cast = result.get("quoted_cast", quoted_cast_hash)
                success_msg = f"Successfully posted quote cast (hash: {cast_hash}) quoting {quoted_cast}"
                logger.info(success_msg)

                return {
                    "status": "success",
                    "message": success_msg,
                    "cast_hash": cast_hash,
                    "quoted_cast_hash": quoted_cast,
                    "channel": channel,
                    "sent_content": content,  # For AI Blindness Fix
                    "timestamp": time.time(),
                }
            else:
                error_msg = f"Failed to post quote cast via observer: {result.get('error', 'unknown error')}"
                logger.error(error_msg)
                return {
                    "status": "failure",
                    "error": error_msg,
                    "timestamp": time.time(),
                }

        except Exception as e:
            error_msg = f"Error executing {self.name}: {str(e)}"
            logger.exception(error_msg)
            
            # Record this action failure in world state
            if context.world_state_manager:
                context.world_state_manager.add_action_result(
                    action_type=self.name,
                    parameters={"content": content, "quoted_cast_hash": quoted_cast_hash, "channel": channel},
                    result=f"failure: {str(e)}",
                )
            
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class FollowFarcasterUserTool(ToolInterface):
    """
    Tool for following a Farcaster user.
    """

    @property
    def name(self) -> str:
        return "follow_farcaster_user"

    @property
    def description(self) -> str:
        return "Follow a Farcaster user by FID."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {"fid": "integer - The Farcaster ID of the user to follow"}

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        logger.info(f"Executing tool '{self.name}' with params: {params}")
        if not context.farcaster_observer:
            err = "Farcaster integration not configured."
            logger.error(err)
            return {"status": "failure", "error": err, "timestamp": time.time()}
        fid = params.get("fid")
        if fid is None:
            err = "Missing required parameter: fid"
            logger.error(err)
            return {"status": "failure", "error": err, "timestamp": time.time()}
        result = await context.farcaster_observer.follow_user(fid)
        if result.get("success"):
            return {"status": "success", "fid": fid, "timestamp": time.time()}
        return {
            "status": "failure",
            "error": result.get("error"),
            "timestamp": time.time(),
        }


class UnfollowFarcasterUserTool(ToolInterface):
    """
    Tool for unfollowing a Farcaster user.
    """

    @property
    def name(self) -> str:
        return "unfollow_farcaster_user"

    @property
    def description(self) -> str:
        return "Unfollow a Farcaster user by FID."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {"fid": "integer - The Farcaster ID of the user to unfollow"}

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        logger.info(f"Executing tool '{self.name}' with params: {params}")
        if not context.farcaster_observer:
            err = "Farcaster integration not configured."
            logger.error(err)
            return {"status": "failure", "error": err, "timestamp": time.time()}
        fid = params.get("fid")
        if fid is None:
            err = "Missing required parameter: fid"
            logger.error(err)
            return {"status": "failure", "error": err, "timestamp": time.time()}
        result = await context.farcaster_observer.unfollow_user(fid)
        if result.get("success"):
            return {"status": "success", "fid": fid, "timestamp": time.time()}
        return {
            "status": "failure",
            "error": result.get("error"),
            "timestamp": time.time(),
        }


class SendFarcasterDMTool(ToolInterface):
    """
    Tool for sending a direct message (DM) to a Farcaster user.
    """

    @property
    def name(self) -> str:
        return "send_farcaster_dm"

    @property
    def description(self) -> str:
        return "Send a direct message to a Farcaster user by FID."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "fid": "integer - The Farcaster ID of the recipient",
            "content": "string - The DM content",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        logger.info(f"Executing tool '{self.name}' with params: {params}")
        if not context.farcaster_observer:
            err = "Farcaster integration not configured."
            logger.error(err)
            return {"status": "failure", "error": err, "timestamp": time.time()}
        fid = params.get("fid")
        content = params.get("content")
        if fid is None or not content:
            err = "Missing required parameters: fid and content"
            logger.error(err)
            return {"status": "failure", "error": err, "timestamp": time.time()}
        result = await context.farcaster_observer.send_dm(fid, content)
        if result.get("success"):
            return {
                "status": "success",
                "message_id": result.get("message_id"),
                "timestamp": time.time(),
            }
        return {
            "status": "failure",
            "error": result.get("error"),
            "timestamp": time.time(),
        }


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
            "user_identifier": "string - Username (without @) or FID of the user whose timeline to fetch",
            "limit": "integer (optional) - Number of casts to retrieve (default: 10, max: 50)",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the get user timeline action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Check if Farcaster integration is available
        if not context.farcaster_observer:
            error_msg = "Farcaster integration (observer) not configured."
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
            result = await context.farcaster_observer.get_user_casts(
                user_identifier=user_identifier, limit=limit
            )
            
            # Check if the observer operation was successful
            if result.get("success", True):  # Default to True for backward compatibility
                logger.info(f"Retrieved {len(result.get('casts', []))} casts for user {user_identifier}")
                return {
                    "status": "success",
                    "user_identifier": user_identifier,
                    "casts": result.get("casts", []),
                    "user_info": result.get("user_info"),
                    "count": len(result.get("casts", [])),
                    "timestamp": time.time(),
                }
            else:
                error_msg = result.get("error", "Unknown error from observer")
                logger.warning(f"Observer returned error for user {user_identifier}: {error_msg}")
                return {"status": "failure", "error": error_msg, "timestamp": time.time()}
        except Exception as e:
            error_msg = f"Error fetching user timeline: {e}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class SearchCastsTool(ToolInterface):
    """
    Tool for searching Farcaster casts based on keywords.
    """

    @property
    def name(self) -> str:
        return "search_casts"

    @property
    def description(self) -> str:
        return "Search for casts on Farcaster using keywords. Optionally filter by channel. Use this to find relevant content or discussions."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "query": "string - Search keywords or phrases to look for in casts",
            "channel_id": "string (optional) - Channel ID to search within (e.g., 'dev', 'warpcast', 'base')",
            "limit": "integer (optional) - Number of results to return (default: 10, max: 50)",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the search casts action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Check if Farcaster integration is available
        if not context.farcaster_observer:
            error_msg = "Farcaster integration (observer) not configured."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        query = params.get("query")
        channel_id = params.get("channel_id")
        limit = params.get("limit", 10)

        if not query:
            error_msg = "Missing required parameter 'query'"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            limit = int(limit)
            if limit < 1 or limit > 50:
                limit = min(max(limit, 1), 50)  # Clamp to valid range
        except (ValueError, TypeError):
            limit = 10

        try:
            result = await context.farcaster_observer.search_casts(
                query=query, channel_id=channel_id, limit=limit
            )
            logger.info(f"Found {len(result.get('casts', []))} casts for query '{query}'")
            return {
                "status": "success",
                "query": query,
                "channel_id": channel_id,
                "casts": result.get("casts", []),
                "count": len(result.get("casts", [])),
                "timestamp": time.time(),
            }
        except Exception as e:
            error_msg = f"Error searching casts: {e}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class GetTrendingCastsTool(ToolInterface):
    """
    Tool for fetching trending/popular casts from Farcaster.
    """

    @property
    def name(self) -> str:
        return "get_trending_casts"

    @property
    def description(self) -> str:
        return "Get trending or popular casts from Farcaster based on engagement metrics. Optionally filter by channel and timeframe."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "channel_id": "string (optional) - Channel ID to get trending casts from (e.g., 'dev', 'warpcast', 'base')",
            "timeframe_hours": "integer (optional) - Timeframe in hours to consider for trending (default: 24, max: 168)",
            "limit": "integer (optional) - Number of trending casts to return (default: 10, max: 50)",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the get trending casts action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Check if Farcaster integration is available
        if not context.farcaster_observer:
            error_msg = "Farcaster integration (observer) not configured."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        channel_id = params.get("channel_id")
        timeframe_hours = params.get("timeframe_hours", 24)
        limit = params.get("limit", 10)

        try:
            timeframe_hours = int(timeframe_hours)
            if timeframe_hours < 1 or timeframe_hours > 168:  # Max 1 week
                timeframe_hours = min(max(timeframe_hours, 1), 168)
        except (ValueError, TypeError):
            timeframe_hours = 24

        try:
            limit = int(limit)
            if limit < 1 or limit > 50:
                limit = min(max(limit, 1), 50)  # Clamp to valid range
        except (ValueError, TypeError):
            limit = 10

        try:
            result = await context.farcaster_observer.get_trending_casts(
                channel_id=channel_id, timeframe_hours=timeframe_hours, limit=limit
            )
            logger.info(f"Retrieved {len(result.get('casts', []))} trending casts")
            return {
                "status": "success",
                "channel_id": channel_id,
                "timeframe_hours": timeframe_hours,
                "casts": result.get("casts", []),
                "count": len(result.get("casts", [])),
                "timestamp": time.time(),
            }
        except Exception as e:
            error_msg = f"Error fetching trending casts: {e}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}


class GetCastByUrlTool(ToolInterface):
    """
    Tool for fetching cast details from a Farcaster/Warpcast URL.
    """

    @property
    def name(self) -> str:
        return "get_cast_by_url"

    @property
    def description(self) -> str:
        return "Fetch details of a specific cast using its Farcaster/Warpcast URL. Use this to get information about a cast when you have the URL."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "farcaster_url": "string - Full Farcaster/Warpcast URL of the cast (e.g., 'https://warpcast.com/username/0x123abc')",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the get cast by URL action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Check if Farcaster integration is available
        if not context.farcaster_observer:
            error_msg = "Farcaster integration (observer) not configured."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Extract and validate parameters
        farcaster_url = params.get("farcaster_url")

        if not farcaster_url:
            error_msg = "Missing required parameter 'farcaster_url'"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Basic URL validation
        if not any(domain in farcaster_url.lower() for domain in ["warpcast.com", "farcaster.xyz"]):
            error_msg = "Invalid Farcaster URL. Must be a warpcast.com or farcaster.xyz URL."
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            result = await context.farcaster_observer.get_cast_by_url(farcaster_url=farcaster_url)
            if result.get("cast"):
                logger.info(f"Successfully retrieved cast from URL: {farcaster_url}")
                return {
                    "status": "success",
                    "url": farcaster_url,
                    "cast": result.get("cast"),
                    "timestamp": time.time(),
                }
            else:
                error_msg = result.get("error", "Cast not found or URL invalid")
                logger.warning(f"Failed to retrieve cast from URL {farcaster_url}: {error_msg}")
                return {"status": "failure", "error": error_msg, "timestamp": time.time()}
        except Exception as e:
            error_msg = f"Error fetching cast by URL: {e}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}
