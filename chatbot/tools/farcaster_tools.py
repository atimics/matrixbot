"""
Farcaster platform-specific tools.
"""
import logging
import time
from typing import Any, Dict

from .base import ActionContext, ToolInterface
from ..utils.markdown_utils import strip_markdown

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
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The text content of the cast to post"
                },
                "channel": {
                    "type": "string",
                    "description": "The channel to post in (if not provided, posts to user's timeline)"
                },
                "image_s3_url": {
                    "type": "string",
                    "description": "S3 URL of an image to attach to the post"
                },
                "video_s3_url": {
                    "type": "string",
                    "description": "S3 URL of a video to attach to the post"
                }
            },
            "required": ["content"]
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
        image_s3_url = params.get("image_s3_url")  # Optional
        video_s3_url = params.get("video_s3_url")  # Optional

        if not content:
            error_msg = "Missing required parameter 'content' for Farcaster post"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg, "timestamp": time.time()}

        # Strip markdown formatting for Farcaster
        content = strip_markdown(content)

        # Truncate content if too long for Farcaster
        MAX_FARCASTER_CONTENT_LENGTH = 320
        if len(content) > MAX_FARCASTER_CONTENT_LENGTH:
            content = content[:MAX_FARCASTER_CONTENT_LENGTH - 3] + "..."
            logger.warning(f"Farcaster content truncated to {MAX_FARCASTER_CONTENT_LENGTH} chars.")

        # Prepare embeds for media attachments
        embeds = []
        media_type = None
        media_s3_url = None

        if image_s3_url:
            embeds.append({"url": image_s3_url})
            media_type = "image"
            media_s3_url = image_s3_url
            logger.info(f"Adding image embed to Farcaster post: {image_s3_url}")

        if video_s3_url:
            embeds.append({"url": video_s3_url})
            media_type = "video"
            media_s3_url = video_s3_url
            logger.info(f"Adding video embed to Farcaster post: {video_s3_url}")

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
                        parameters={
                            "content": content,
                            "channel": channel,
                            "embeds": embeds,
                        },
                        result="scheduled",
                    )

                # Note: The schedule_post method now handles embeds properly
                context.farcaster_observer.schedule_post(
                    content, channel, action_id, embeds
                )
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
            # Prepare embed URLs for the observer
            embed_urls = []
            if image_s3_url:
                embed_urls.append(image_s3_url)
            if video_s3_url:
                embed_urls.append(video_s3_url)

            result = await context.farcaster_observer.post_cast(
                content=content,
                channel=channel,
                embed_urls=embed_urls if embed_urls else None
            )
            logger.info(f"Farcaster observer post_cast returned: {result}")

            # Record this action in world state
            if context.world_state_manager:
                if result.get("success"):
                    cast_hash = result.get("cast", {}).get("hash")
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={
                            "content": content,
                            "channel": channel,
                            "cast_hash": cast_hash,
                        },
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
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The text content of the reply"
                },
                "reply_to_hash": {
                    "type": "string",
                    "description": "The hash of the cast to reply to"
                }
            },
            "required": ["content", "reply_to_hash"]
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

        # Strip markdown formatting for Farcaster
        content = strip_markdown(content)

        # Truncate content if too long for Farcaster
        MAX_FARCASTER_CONTENT_LENGTH = 320
        if len(content) > MAX_FARCASTER_CONTENT_LENGTH:
            content = content[:MAX_FARCASTER_CONTENT_LENGTH - 3] + "..."
            logger.warning(f"Farcaster reply content truncated to {MAX_FARCASTER_CONTENT_LENGTH} chars.")

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

                context.farcaster_observer.schedule_reply(
                    content, reply_to_hash, action_id
                )
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
                        parameters={
                            "content": content,
                            "reply_to_hash": reply_to_hash,
                            "cast_hash": cast_hash,
                        },
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
            "type": "object",
            "properties": {
                "cast_hash": {
                    "type": "string",
                    "description": "The hash of the cast to like"
                }
            },
            "required": ["cast_hash"]
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
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Your commentary/thoughts to add to the quoted cast"
                },
                "quoted_cast_hash": {
                    "type": "string",
                    "description": "The hash of the cast to quote"
                },
                "channel": {
                    "type": "string",
                    "description": "The channel to post in (if not provided, posts to user's timeline)"
                }
            },
            "required": ["content", "quoted_cast_hash"]
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

        # Strip markdown formatting for Farcaster
        content = strip_markdown(content)

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
                    cast_hash = result.get("cast", {}).get(
                        "hash", result.get("cast_hash", "unknown")
                    )
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={
                            "content": content,
                            "quoted_cast_hash": quoted_cast_hash,
                            "channel": channel,
                            "cast_hash": cast_hash,
                        },
                        result="success",
                    )
                else:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={
                            "content": content,
                            "quoted_cast_hash": quoted_cast_hash,
                            "channel": channel,
                        },
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
                    parameters={
                        "content": content,
                        "quoted_cast_hash": quoted_cast_hash,
                        "channel": channel,
                    },
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
        return {
            "type": "object",
            "properties": {
                "fid": {
                    "type": "integer",
                    "description": "The Farcaster ID of the user to follow"
                }
            },
            "required": ["fid"]
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
        return {
            "type": "object",
            "properties": {
                "fid": {
                    "type": "integer",
                    "description": "The Farcaster ID of the user to unfollow"
                }
            },
            "required": ["fid"]
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
    Tool for sending a direct message (DM) to a Farcaster user - DEPRECATED.
    """

    @property
    def name(self) -> str:
        return "send_farcaster_dm"

    @property
    def description(self) -> str:
        return "DEPRECATED: Send a direct message to a Farcaster user by FID. DM functionality is not supported by the Farcaster API."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "fid": {
                    "type": "integer",
                    "description": "The Farcaster ID of the recipient"
                },
                "content": {
                    "type": "string",
                    "description": "The DM content"
                }
            },
            "required": ["fid", "content"]
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        logger.info(f"Executing deprecated tool '{self.name}' with params: {params}")
        return {
            "status": "failure", 
            "error": "Farcaster DM functionality is not supported by the API", 
            "timestamp": time.time()
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
            if result.get(
                "success", True
            ):  # Default to True for backward compatibility
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
                error_msg = result.get("error", "Unknown error from observer")
                logger.warning(
                    f"Observer returned error for user {user_identifier}: {error_msg}"
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
        if not context.farcaster_observer:
            return {
                "status": "failure",
                "error": "Farcaster observer not available",
                "timestamp": time.time()
            }
            
        try:
            results = await context.farcaster_observer.collect_world_state_now()
            
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
    
    name = "get_trending_casts"
    description = "Get trending casts from Farcaster to see what's popular on the platform"

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
        if not context.farcaster_observer:
            return {
                "status": "failure",
                "error": "Farcaster observer not available",
                "timestamp": time.time()
            }
        try:
            channel_id = params.get("channel_id")
            timeframe_hours = params.get("timeframe_hours", 24)
            limit = params.get("limit", 10)
            # Get trending casts using the observer (mocked in tests)
            if hasattr(context.farcaster_observer, "get_trending_casts"):
                result = await context.farcaster_observer.get_trending_casts(
                    channel_id=channel_id, timeframe_hours=timeframe_hours, limit=limit
                )
            else:
                # Fallback to API client if method missing
                if not context.farcaster_observer.api_client:
                    return {
                        "status": "failure",
                        "error": "Farcaster API client not initialized",
                        "timestamp": time.time()
                    }
                result = await context.farcaster_observer.api_client.get_trending_casts(
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
                        timestamp=time.time(),
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
        except Exception as e:
            logger.error(f"Error in GetTrendingCastsTool: {e}", exc_info=True)
            return {
                "status": "failure",
                "error": str(e),
                "timestamp": time.time(),
            }


class SearchCastsTool(ToolInterface):
    """Tool to search for casts on Farcaster."""
    
    name = "search_casts"
    description = "Search for casts on Farcaster by query text"

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
            
        if not context.farcaster_observer:
            return {"status": "failure", "error": "Farcaster observer not available", "timestamp": time.time()}
            
        try:
            # Call the observer's search_casts method directly
            result = await context.farcaster_observer.search_casts(
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
                        timestamp=time.time(),
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
                return {"status": "failure", "error": f"No casts found for query: {query}", "timestamp": time.time()}
                
        except Exception as e:
            logger.error(f"Error in SearchCastsTool: {e}", exc_info=True)
            return {
                "status": "failure", 
                "error": str(e),
                "timestamp": time.time(),
            }


class GetCastByUrlTool(ToolInterface):
    """Tool to get a specific cast by its URL or hash."""
    
    name = "get_cast_by_url"
    description = "Get details about a specific Farcaster cast by its URL or hash"

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
        if not context.farcaster_observer:
            return {
                "status": "failure",
                "error": "Farcaster observer not available",
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
            # Call the observer's get_cast_by_url method directly
            result = await context.farcaster_observer.get_cast_by_url(
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

