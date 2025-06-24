"""
Tool for sending replies to Farcaster posts.
"""
import asyncio
import logging
import time
from typing import Any, Dict

from ..base import ActionContext, ToolInterface
from ...utils.markdown_utils import strip_markdown
from .utils import get_farcaster_observer, create_error_response, create_success_response

logger = logging.getLogger(__name__)


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

        # Get Farcaster observer through ServiceRegistry
        farcaster_observer = get_farcaster_observer(context)
        if not farcaster_observer:
            return create_error_response("Farcaster integration (observer) not configured.")

        # Extract and validate parameters
        content = params.get("content")
        reply_to_hash = params.get("reply_to_hash")

        missing_params = []
        if not content:
            missing_params.append("content")
        if not reply_to_hash:
            missing_params.append("reply_to_hash")

        if missing_params:
            return create_error_response(f"Missing required parameters for Farcaster reply: {', '.join(missing_params)}")

        # Strip markdown formatting for Farcaster
        content = strip_markdown(str(content))

        # Truncate content if too long for Farcaster
        MAX_FARCASTER_CONTENT_LENGTH = 1024
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

        reply_q = getattr(farcaster_observer, "reply_queue", None)
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

                farcaster_observer.schedule_reply(
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
                return create_error_response(error_msg)
                
        # Fallback immediate execution
        try:
            result = await farcaster_observer.reply_to_cast(
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
                return create_error_response(result.get("error", "unknown"))
                
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

            return create_error_response(error_msg)
