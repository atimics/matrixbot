"""
Tool for sending posts to Farcaster.
"""
import asyncio
import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface
from ...utils.markdown_utils import strip_markdown
from .utils import get_farcaster_observer, create_error_response, create_success_response

logger = logging.getLogger(__name__)


class SendFarcasterPostTool(ToolInterface):
    """
    Unified tool for sending posts and replies to Farcaster.
    
    This tool consolidates the functionality of both regular posts and replies,
    eliminating the need for separate tools and simplifying the AI's decision space.
    """

    @property
    def name(self) -> str:
        return "send_farcaster_post"

    @property
    def description(self) -> str:
        return ("Send a post (cast) to Farcaster. Can be used for both new posts and replies. "
                "If reply_to_hash is provided, sends as a reply to that cast. "
                "Use the 'embed_url' parameter to attach media or frames. "
                "If no embed_url is provided, recently generated media (within 5 minutes) will be automatically attached.")

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The text content of the cast to post"
                },
                "reply_to_hash": {
                    "type": "string",
                    "description": "The hash of the cast to reply to. If provided, sends as a reply instead of a new post"
                },
                "channel": {
                    "type": "string",
                    "description": "The Farcaster channel name to post in (if not provided, posts to user's timeline). Not used for replies."
                },
                "embed_url": {
                    "type": "string",
                    "description": "A URL to embed in the cast, such as an Arweave URL for an image/video page or a frame URL."
                }
            },
            "required": ["content"]
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        """
        Execute the Farcaster post or reply action.
        """
        logger.info(f"Executing tool '{self.name}' with params: {params}")

        # Get Farcaster observer through ServiceRegistry
        farcaster_observer = get_farcaster_observer(context)
        if not farcaster_observer:
            return create_error_response("Farcaster integration (observer) not configured or ServiceRegistry not available.")

        # Extract and validate parameters
        content = params.get("content", "")
        reply_to_hash = params.get("reply_to_hash")  # Optional - if provided, sends as reply
        channel = params.get("channel")  # Optional
        embed_url = params.get("embed_url")  # Optional

        # Handle reply-specific validation and duplicate checking
        if reply_to_hash:
            # For replies, content is always required
            if not content:
                return create_error_response("Content is required for Farcaster replies")
                
            # Check if we've already replied to this cast (internal state check)
            if (
                context.world_state_manager
                and context.world_state_manager.has_replied_to_cast(reply_to_hash)
            ):
                error_msg = f"Already replied to cast {reply_to_hash}. Cannot reply to the same cast twice."
                logger.warning(error_msg)
                return create_error_response(error_msg)

            # --- AUTHORITATIVE DUPLICATE CHECK ---
            # Check the actual Farcaster thread to see if we've already replied
            # This is the definitive source of truth and prevents duplicates even if internal state is lost
            if farcaster_observer and farcaster_observer.api_client:
                try:
                    bot_fid = farcaster_observer.bot_fid
                    if bot_fid:
                        logger.debug(f"Performing authoritative duplicate check for cast {reply_to_hash} with bot FID {bot_fid}")
                        conversation = await farcaster_observer.api_client.lookup_cast_conversation(reply_to_hash)
                        
                        if conversation and "result" in conversation and "conversation" in conversation["result"]:
                            # Check both direct replies and nested conversation
                            all_casts = conversation["result"]["conversation"].get("cast", {}).get("direct_replies", [])
                            
                            # Also check if the conversation has a nested structure
                            if "casts" in conversation["result"]["conversation"]:
                                all_casts.extend(conversation["result"]["conversation"]["casts"])
                            
                            for cast in all_casts:
                                if cast and "author" in cast and "fid" in cast["author"]:
                                    if str(cast["author"]["fid"]) == str(bot_fid):
                                        # The bot has already replied to this cast on-chain
                                        error_msg = f"Authoritative check failed: Bot (FID {bot_fid}) already replied to cast {reply_to_hash}. Aborting to prevent duplicate."
                                        logger.warning(error_msg)
                                        
                                        # Update internal state to correct any drift
                                        if context.world_state_manager:
                                            context.world_state_manager.add_action_result(
                                                action_type=self.name,
                                                parameters={"content": content, "reply_to_hash": reply_to_hash},
                                                result="skipped_duplicate_on_chain",
                                            )
                                        
                                        return {
                                            "status": "skipped", 
                                            "message": "Duplicate reply already exists in the Farcaster thread",
                                            "reply_to_hash": reply_to_hash,
                                            "timestamp": time.time()
                                        }
                        
                        logger.debug(f"Authoritative check passed: No existing reply found for cast {reply_to_hash}")
                    else:
                        logger.warning("Bot FID not available for authoritative duplicate check, proceeding with caution")
                        
                except Exception as e:
                    # Log the error but proceed - we don't want API failures to completely block replies
                    logger.error(f"Failed to perform authoritative duplicate check for cast {reply_to_hash}: {e}. Proceeding with caution.")
                    # Internal check already passed, so we'll proceed

        # For non-replies, validate content and embed requirements 
        elif not content and not embed_url:
            return create_error_response("Missing required parameter 'content' for Farcaster post (content required when no embed is attached)")
        
        # Generate minimal content for embed-only posts (non-replies only)
        if not content and embed_url and not reply_to_hash:
            content = "📎"  # Simple emoji for embed posts

        # Strip markdown formatting for Farcaster (ensure content is not None)
        if content:
            content = strip_markdown(content)

        # Truncate content if too long for Farcaster
        MAX_FARCASTER_CONTENT_LENGTH = 1024
        if len(content) > MAX_FARCASTER_CONTENT_LENGTH:
            content = content[:MAX_FARCASTER_CONTENT_LENGTH - 3] + "..."
            logger.warning(f"Farcaster content truncated to {MAX_FARCASTER_CONTENT_LENGTH} chars.")

        # Auto-attachment: Check for recently generated media if no embed_url provided
        if not embed_url and context.world_state_manager:
            recent_media_url = context.world_state_manager.get_last_generated_media_url()
            if recent_media_url:
                # Check if the media was generated recently (within last 5 minutes)
                if hasattr(context.world_state_manager.state, 'generated_media_library'):
                    media_library = context.world_state_manager.state.generated_media_library
                    if media_library:
                        last_media = media_library[-1]
                        media_age = time.time() - last_media.get('timestamp', 0)
                        if media_age <= 300:  # 5 minutes
                            embed_url = recent_media_url
                            logger.info(f"Auto-attaching recently generated media to Farcaster post: {embed_url}")

        # Prepare embeds
        embeds = []
        if embed_url:
            embeds.append({"url": embed_url})
            logger.info(f"Adding embed to Farcaster post: {embed_url}")

        # For non-replies, check for duplicate posts with identical content
        if not reply_to_hash and (
            context.world_state_manager
            and context.world_state_manager.has_sent_farcaster_post(content)
        ):
            return create_error_response("Already sent Farcaster post with identical content. Skipping duplicate.")

        # Choose appropriate queue based on whether this is a post or reply
        if reply_to_hash:
            queue = getattr(farcaster_observer, "reply_queue", None)
        else:
            queue = getattr(farcaster_observer, "post_queue", None)
            
        if isinstance(queue, asyncio.Queue):
            try:
                # Record scheduling and get action_id for tracking
                action_id = None
                if context.world_state_manager:
                    action_id = context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={
                            "content": content,
                            "reply_to_hash": reply_to_hash,
                            "channel": channel,
                            "embeds": embeds,
                        },
                        result="scheduled",
                    )

                # Schedule the appropriate action
                if reply_to_hash:
                    farcaster_observer.schedule_reply(
                        content, reply_to_hash, action_id
                    )
                    success_msg = f"Scheduled Farcaster reply to cast {reply_to_hash}"
                else:
                    # Note: The schedule_post method now handles embeds properly
                    farcaster_observer.schedule_post(
                        content, channel, action_id, embeds
                    )
                    success_msg = "Scheduled Farcaster post via scheduler"
                    
                logger.info(success_msg)
                return {
                    "status": "scheduled",
                    "message": success_msg,
                    "content": content,
                    "reply_to_hash": reply_to_hash,
                    "channel": channel,
                    "action_id": action_id,  # Return action_id for tracking
                    "timestamp": time.time(),
                }
            except Exception as e:
                error_msg = f"Error scheduling Farcaster {'reply' if reply_to_hash else 'post'}: {e}"
                logger.exception(error_msg)
                return create_error_response(error_msg)
                
        # Immediate execution fallback
        try:
            if reply_to_hash:
                # Execute as reply
                result = await farcaster_observer.reply_to_cast(
                    content, reply_to_hash
                )
                logger.info(f"Farcaster observer reply_to_cast returned: {result}")
            else:
                # Execute as post
                # Prepare embed URLs for the observer
                embed_urls = [e['url'] for e in embeds if 'url' in e]

                result = await farcaster_observer.post_cast(
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
                            "reply_to_hash": reply_to_hash,
                            "channel": channel,
                            "cast_hash": cast_hash,
                            "embed_url": embed_url,
                        },
                        result="success",
                    )
                else:
                    context.world_state_manager.add_action_result(
                        action_type=self.name,
                        parameters={
                            "content": content, 
                            "reply_to_hash": reply_to_hash,
                            "channel": channel, 
                            "embed_url": embed_url,
                        },
                        result=f"failure: {result.get('error', 'unknown')}",
                    )

            if result.get("success"):
                return {"status": "success", **result}
            else:
                return create_error_response(result.get("error", "unknown"))
                
        except Exception as e:
            error_msg = f"Error executing send_farcaster_{'reply' if reply_to_hash else 'post'}: {e}"
            logger.exception(error_msg)

            # Record this action failure in world state
            if context.world_state_manager:
                context.world_state_manager.add_action_result(
                    action_type=self.name,
                    parameters={
                        "content": content, 
                        "reply_to_hash": reply_to_hash,
                        "channel": channel,
                        "embed_url": embed_url,
                    },
                    result=f"failure: {str(e)}",
                )

            return create_error_response(error_msg)
