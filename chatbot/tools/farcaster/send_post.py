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
        return ("Send a post (cast) to Farcaster using turn-based conversation logic. "
                "CRITICAL: For replies, the bot can only respond when it's the bot's turn in the conversation. "
                "The system automatically tracks whose turn it is to prevent spam and maintain natural conversation flow. "
                "The AttentionEngine pre-validates reply context, ensuring all necessary conversation context is loaded. "
                "Use 'embed_url' parameter to attach media or frames. "
                "Recently generated media (within 5 minutes) will be automatically attached if no embed_url is provided.")

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

            if not context.world_state_manager:
                error_msg = "CRITICAL: Cannot validate thread context - world state manager not available. ABORTING reply."
                logger.error(error_msg)
                return create_error_response(error_msg)

            # === MULTI-LAYERED DUPLICATE REPLY PREVENTION ===
            logger.info(f"Starting multi-layered duplicate prevention check for reply to: {reply_to_hash}")

            # === LAYER 0: Internal State Check (Fastest) ===
            if hasattr(context.world_state_manager, 'has_replied_to_cast') and context.world_state_manager.has_replied_to_cast(reply_to_hash):
                error_msg = f"DUPLICATE ACTION BLOCKED: Internal state indicates a reply to {reply_to_hash} already exists."
                logger.warning(error_msg)
                return create_error_response(error_msg)
            logger.info(f"Layer 0 passed: No reply found in internal state for {reply_to_hash}")

            # === LAYER 1: Persistent Local Cache Check ===
            if context.database_manager:
                logger.info(f"Layer 1: Checking persistent cache for reply to: {reply_to_hash}")
                try:
                    if await context.database_manager.has_replied_to(reply_to_hash):
                        error_msg = f"DUPLICATE ACTION BLOCKED: Persistent cache indicates a reply to {reply_to_hash} already exists."
                        logger.warning(error_msg)
                        return create_error_response(error_msg)
                    logger.info(f"Layer 1 passed: No reply found in persistent cache for {reply_to_hash}")
                except Exception as e:
                    logger.error(f"Layer 1 failed: Error checking persistent cache: {e}", exc_info=True)
                    # Continue to Layer 2 as fallback
            else:
                logger.warning("Layer 1 skipped: Database manager not available for persistent cache check")

            # === LAYER 2: Authoritative API Check ===
            logger.info(f"Layer 2: Performing authoritative API check for reply to: {reply_to_hash}")
            if not farcaster_observer.api_client:
                return create_error_response("Cannot verify reply: Farcaster API client is not configured.")
            
            if not hasattr(farcaster_observer, 'bot_fid') or not farcaster_observer.bot_fid:
                return create_error_response("Cannot verify reply: Bot FID is not configured.")

            try:
                conversation_data = await farcaster_observer.api_client.lookup_cast_conversation(reply_to_hash)
                
                # Navigate the API response structure
                conversation = conversation_data.get('result', {}).get('conversation', {})
                if not conversation:
                    # Try alternative structure
                    conversation = conversation_data.get('conversation', {})
                
                cast_data = conversation.get('cast', {})
                all_replies = cast_data.get('direct_replies', [])
                
                # Also check the broader conversation casts array for replies
                broader_casts = conversation.get('casts', [])
                for cast in broader_casts:
                    if cast.get('parent_hash') == reply_to_hash:
                        all_replies.append(cast)

                # Check if bot has already replied
                bot_fid_str = str(farcaster_observer.bot_fid)
                for reply in all_replies:
                    author_fid = reply.get('author', {}).get('fid')
                    if str(author_fid) == bot_fid_str:
                        error_msg = f"DUPLICATE ACTION BLOCKED: Authoritative API check found existing reply from bot (FID: {bot_fid_str}) to cast {reply_to_hash}."
                        logger.warning(error_msg)
                        
                        # Update persistent cache with this finding
                        if context.database_manager:
                            try:
                                reply_hash = reply.get('hash', 'unknown')
                                await context.database_manager.add_replied_to_cast(reply_to_hash, reply_hash)
                                logger.info(f"Updated persistent cache with discovered reply: {reply_hash}")
                            except Exception as cache_e:
                                logger.error(f"Failed to update persistent cache: {cache_e}")
                        
                        return create_error_response(error_msg)
                
                logger.info(f"Layer 2 passed: Authoritative API check found no existing reply from bot to {reply_to_hash}")

            except Exception as e:
                logger.error(f"Layer 2 failed: Authoritative duplicate check failed due to API error: {e}", exc_info=True)
                # Fail safe: if the check fails, do not send the reply to avoid potential duplicates
                return create_error_response(f"Could not verify thread for duplicates due to an API error: {e}")

            # === LAYER 3: Simplified Thread Turn Validation ===
            # NOTE: Context hydration is now handled by AttentionEngine, so we can trust that
            # if a reply reaches this tool, the thread context should already exist in WorldState.
            logger.info(f"Layer 3: Performing thread turn validation for: {reply_to_hash}")
            try:
                thread_id = reply_to_hash  # For Farcaster, the reply target becomes the thread ID
                
                # Simple check - AttentionEngine guarantees context exists
                if not context.world_state_manager.is_bot_turn_in_thread(thread_id):
                    # Normal turn validation - bot shouldn't reply when it's not its turn
                    error_msg = f"THREAD TURN VIOLATION: It is not the bot's turn to speak in thread {thread_id}. This prevents spam and maintains natural conversation flow."
                    logger.error(error_msg)
                    return {
                        "status": "blocked",
                        "message": "Reply blocked: Not the bot's turn in this conversation",
                        "reason": "not_bot_turn",
                        "reply_to_hash": reply_to_hash,
                        "timestamp": time.time()
                    }
                
                logger.info(f"Layer 3 passed: Thread turn validation approved for {thread_id}")

            except Exception as e:
                # DEFENSIVE: Gracefully handle validation errors
                logger.error(f"Layer 3 failed: Unexpected error during thread turn validation for {reply_to_hash}: {e}", exc_info=True)
                # Don't fail the entire operation for thread turn issues if authoritative check passed
                logger.warning(f"Proceeding despite thread turn validation error - authoritative check was successful")
            
            logger.info(f"All duplicate prevention layers passed for reply to: {reply_to_hash}")

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
                    
                    # === POST-EXECUTION: Update Persistent Cache ===
                    # Record successful reply in persistent cache for future duplicate prevention
                    if reply_to_hash and cast_hash and context.database_manager:
                        try:
                            await context.database_manager.add_replied_to_cast(reply_to_hash, cast_hash)
                            logger.info(f"Successfully recorded reply to {reply_to_hash} with hash {cast_hash} in persistent cache")
                        except Exception as cache_e:
                            logger.error(f"Failed to update persistent cache for successful reply: {cache_e}")
                            # Don't fail the operation, just log the cache update failure
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
                # Record the failure in the thread for cooldown management
                error_msg = result.get("error", "unknown")
                if context.world_state_manager and reply_to_hash:
                    context.world_state_manager.record_action_failure(
                        reply_to_hash, self.name, error_msg
                    )
                return create_error_response(error_msg)
                
        except Exception as e:
            error_msg = f"Error executing send_farcaster_{'reply' if reply_to_hash else 'post'}: {e}"
            logger.exception(error_msg)

            # Record the failure in the thread for cooldown management
            if context.world_state_manager and reply_to_hash:
                context.world_state_manager.record_action_failure(
                    reply_to_hash, self.name, str(e)
                )

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
