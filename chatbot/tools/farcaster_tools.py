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
        if context.world_state_manager and context.world_state_manager.has_sent_farcaster_post(content):
            error_msg = "Already sent Farcaster post with identical content. Skipping duplicate."
            logger.warning(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # If observer supports scheduling (has a real asyncio.Queue), enqueue; otherwise, execute immediately
        import asyncio
        post_q = getattr(context.farcaster_observer, 'post_queue', None)
        if isinstance(post_q, asyncio.Queue):
            try:
                context.farcaster_observer.schedule_post(content, channel)
                success_msg = "Scheduled Farcaster post via scheduler"
                logger.info(success_msg)
                return {
                    "status": "scheduled",
                    "message": success_msg,
                    "content": content,
                    "channel": channel,
                    "timestamp": time.time(),
                }
            except Exception as e:
                error_msg = f"Error scheduling Farcaster post: {e}"
                logger.exception(error_msg)
                return {"status": "failure", "error": error_msg, "timestamp": time.time()}
        # Immediate execution fallback
        try:
            result = await context.farcaster_observer.post_cast(content, channel)
            logger.info(f"Farcaster observer post_cast returned: {result}")
            if result.get("success"):
                return {"status": "success", **result}
            else:
                return {"status": "failure", "error": result.get("error", "unknown"), "timestamp": time.time()}
        except Exception as e:
            error_msg = f"Error executing send_farcaster_post: {e}"
            logger.exception(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        except Exception as e:
            error_msg = f"Error executing {self.name}: {str(e)}"
            logger.exception(error_msg)
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
        if context.world_state_manager and context.world_state_manager.has_replied_to_cast(reply_to_hash):
            error_msg = f"Already replied to cast {reply_to_hash}. Cannot reply to the same cast twice."
            logger.warning(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        import asyncio
        reply_q = getattr(context.farcaster_observer, 'reply_queue', None)
        # If scheduling supported, enqueue
        if isinstance(reply_q, asyncio.Queue):
            try:
                context.farcaster_observer.schedule_reply(content, reply_to_hash)
                success_msg = f"Scheduled Farcaster reply to cast {reply_to_hash}"
                logger.info(success_msg)
                # Record scheduling
                if context.world_state_manager:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={"content": content, "reply_to_hash": reply_to_hash},
                        result="scheduled",
                    )
                return {
                    "status": "scheduled",
                    "message": success_msg,
                    "reply_to_hash": reply_to_hash,
                    "content": content,
                    "timestamp": time.time(),
                }
            except Exception as e:
                error_msg = f"Error scheduling Farcaster reply: {e}"
                logger.exception(error_msg)
                return {"status": "failure", "error": error_msg, "timestamp": time.time()}
        # Fallback immediate execution
        try:
            result = await context.farcaster_observer.reply_to_cast(content, reply_to_hash)
            logger.info(f"Farcaster observer reply_to_cast returned: {result}")
            if result.get("success"):
                return {"status": "success", **result}
            else:
                return {"status": "failure", "error": result.get("error", "unknown"), "timestamp": time.time()}
        except Exception as e:
            error_msg = f"Error executing send_farcaster_reply: {e}"
            logger.exception(error_msg)
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
        if context.world_state_manager and context.world_state_manager.has_liked_cast(cast_hash):
            error_msg = f"Already liked cast {cast_hash}. Cannot like the same cast twice."
            logger.warning(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Use the observer's like_cast method
            result = await context.farcaster_observer.like_cast(cast_hash)
            logger.info(f"Farcaster observer like_cast returned: {result}")

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
        if context.world_state_manager and context.world_state_manager.has_quoted_cast(quoted_cast_hash):
            error_msg = f"Already quoted cast {quoted_cast_hash}. Cannot quote the same cast twice."
            logger.warning(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        try:
            # Use the observer's quote_cast method
            result = await context.farcaster_observer.quote_cast(
                content, quoted_cast_hash, channel
            )
            logger.info(f"Farcaster observer quote_cast returned: {result}")

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

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
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
        return {"status": "failure", "error": result.get("error"), "timestamp": time.time()}

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

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
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
        return {"status": "failure", "error": result.get("error"), "timestamp": time.time()}

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
        return {"fid": "integer - The Farcaster ID of the recipient", "content": "string - The DM content"}

    async def execute(self, params: Dict[str, Any], context: ActionContext) -> Dict[str, Any]:
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
            return {"status": "success", "message_id": result.get("message_id"), "timestamp": time.time()}
        return {"status": "failure", "error": result.get("error"), "timestamp": time.time()}
