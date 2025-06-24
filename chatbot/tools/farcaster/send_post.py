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
        return ("Send a post (cast) to Farcaster. Can be used for both new posts and thread replies. "
                "IMPORTANT: Replies are only allowed within established thread contexts - never reply directly to individual casts. "
                "If reply_to_hash is provided, it must be part of an active thread conversation. "
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
                "quoted_cast_hash": {
                    "type": "string",
                    "description": "The hash of the cast to quote. When provided, this cast will be embedded in the new post."
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
        quoted_cast_hash = params.get("quoted_cast_hash")  # Optional - if provided, embeds the quoted cast
        channel = params.get("channel")  # Optional
        embed_url = params.get("embed_url")  # Optional

        # Handle reply-specific validation and duplicate checking
        if reply_to_hash:
            # For replies, content is always required
            if not content:
                return create_error_response("Content is required for Farcaster replies")

            # CRITICAL: THREAD CONTEXT VALIDATION
            # The bot should NEVER reply to individual casts outside of established thread contexts
            # This prevents spam and ensures coherent conversation flow
            if not context.world_state_manager:
                error_msg = "CRITICAL: Cannot validate thread context - world state manager not available. ABORTING reply."
                logger.error(error_msg)
                return create_error_response(error_msg)
            
            # Check if this reply is happening within an established thread context
            thread_id = f"farcaster:{reply_to_hash}"
            is_active_thread = context.world_state_manager.is_thread_active(thread_id)
            
            if not is_active_thread:
                error_msg = f"THREAD CONTEXT VIOLATION: Bot attempted to reply to cast {reply_to_hash} outside of an established thread context. This is not allowed to prevent spam behavior."
                logger.error(error_msg)
                return {
                    "status": "blocked",
                    "message": "Reply blocked: Not within active thread context",
                    "reason": "thread_context_violation", 
                    "reply_to_hash": reply_to_hash,
                    "timestamp": time.time()
                }
                
            logger.info(f"Thread context validation PASSED: Reply to {reply_to_hash} is within active thread {thread_id}")
                
            # 1. INTERNAL STATE CHECK (Fast Path)
            if context.world_state_manager.has_replied_to_cast(reply_to_hash):
                error_msg = f"Internal state check failed: Already replied to cast {reply_to_hash}."
                logger.warning(error_msg)
                return {
                    "status": "skipped", 
                    "message": error_msg,
                    "reason": "already_replied_internal",
                    "reply_to_hash": reply_to_hash,
                    "timestamp": time.time()
                }

            # 2. AUTHORITATIVE ON-CHAIN CHECK (Definitive Source of Truth)
            # This is CRITICAL - we must verify against the live Farcaster data
            if farcaster_observer and farcaster_observer.api_client:
                bot_fid = farcaster_observer.bot_fid
                if bot_fid:
                    try:
                        logger.info(f"CRITICAL: Performing authoritative duplicate check for cast {reply_to_hash} with bot FID {bot_fid}")
                        conversation = await farcaster_observer.api_client.lookup_cast_conversation(reply_to_hash)
                        
                        if conversation and "result" in conversation and "conversation" in conversation["result"]:
                            # Check direct replies to the target cast
                            all_replies = conversation["result"]["conversation"].get("cast", {}).get("direct_replies", [])
                            
                            for reply in all_replies:
                                if reply and "author" in reply and "fid" in reply["author"]:
                                    if str(reply["author"]["fid"]) == str(bot_fid):
                                        # DUPLICATE DETECTED - Bot has already replied on-chain
                                        error_msg = f"AUTHORITATIVE CHECK FAILED: Bot (FID {bot_fid}) has already replied to cast {reply_to_hash} on-chain. Reply hash: {reply.get('hash', 'unknown')}"
                                        logger.error(error_msg)
                                        
                                        # Correct internal state if there's a discrepancy
                                        if context.world_state_manager:
                                            context.world_state_manager.add_action_result(
                                                action_type=self.name,
                                                parameters={"content": "Correcting internal state", "reply_to_hash": reply_to_hash},
                                                result="skipped_duplicate_on_chain",
                                            )
                                        
                                        return {
                                            "status": "skipped", 
                                            "message": "DUPLICATE REPLY BLOCKED: Reply already exists in the Farcaster thread",
                                            "reason": "already_replied_onchain",
                                            "reply_to_hash": reply_to_hash,
                                            "existing_reply_hash": reply.get("hash"),
                                            "timestamp": time.time()
                                        }
                        
                        logger.info(f"Authoritative check PASSED: No existing reply found for cast {reply_to_hash}")
                        
                    except Exception as e:
                        # If the API check fails, we MUST NOT proceed - safer to fail than spam
                        error_msg = f"CRITICAL: Authoritative duplicate check failed due to API error: {e}. ABORTING reply to prevent potential spam."
                        logger.error(error_msg, exc_info=True)
                        return create_error_response(error_msg)
                else:
                    # If we can't get bot_fid, we cannot do authoritative checking
                    error_msg = "CRITICAL: Cannot perform authoritative duplicate check - bot_fid not available. ABORTING reply."
                    logger.error(error_msg)
                    return create_error_response(error_msg)
            else:
                # If we can't access the API client, we cannot do authoritative checking
                error_msg = "CRITICAL: Cannot perform authoritative duplicate check - API client not available. ABORTING reply."
                logger.error(error_msg)
                return create_error_response(error_msg)

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
                        timestamp = last_media.get('timestamp', 0)
                        # Ensure timestamp is a number, not a mock
                        if isinstance(timestamp, (int, float)) and timestamp > 0:
                            media_age = time.time() - timestamp
                            if media_age <= 300:  # 5 minutes
                                embed_url = recent_media_url
                                logger.info(f"Auto-attaching recently generated media to Farcaster post: {embed_url}")

        # Prepare embeds
        embeds = []
        if embed_url:
            embeds.append({"url": embed_url})
            logger.info(f"Adding embed to Farcaster post: {embed_url}")
        
        # Handle quote casting
        if quoted_cast_hash:
            # Fetch the author FID of the cast to be quoted
            try:
                cast_details_result = await farcaster_observer.get_cast_details(quoted_cast_hash)
                if cast_details_result.get("cast"):
                    quoted_author_fid = cast_details_result["cast"]["author"]["fid"]
                    embeds.append({"cast_id": {"hash": quoted_cast_hash, "fid": quoted_author_fid}})
                    logger.info(f"Adding quote embed for cast: {quoted_cast_hash}")
                else:
                    logger.warning(f"Could not get details for cast to be quoted: {quoted_cast_hash}. Proceeding without quote.")
            except Exception as e:
                logger.error(f"Error fetching details for quoted cast: {e}")
                return create_error_response(f"Failed to fetch quoted cast details: {str(e)}")

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

    @staticmethod
    def _is_valid_cast_hash(cast_hash: str) -> bool:
        """
        Validate if a cast hash has the expected format.
        Farcaster cast hashes are typically 32-byte hashes encoded as 0x-prefixed hex strings.
        """
        if not cast_hash:
            return False
        
        # Remove 0x prefix if present
        hash_without_prefix = cast_hash.lower().replace('0x', '')
        
        # Check if it's a valid hex string of expected length (64 characters for 32 bytes)
        if len(hash_without_prefix) != 64:
            return False
        
        try:
            int(hash_without_prefix, 16)
            return True
        except ValueError:
            return False
