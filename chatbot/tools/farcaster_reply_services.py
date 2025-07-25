"""
Reply eligibility service for Farcaster tools.
Addresses point 4: Over-complex reply tool.
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional, Tuple
from .farcaster_utils import FarcasterCastUtils
from ..config import settings

logger = logging.getLogger(__name__)


class ReplyEligibilityService:
    """
    Service to determine if a bot can reply to a cast under cast-first policy.
    Extracted from SendFarcasterReplyTool to reduce complexity.
    """
    
    def __init__(self, farcaster_observer=None, world_state_manager=None):
        self.farcaster_observer = farcaster_observer
        self.world_state_manager = world_state_manager
    
    async def check_reply_eligibility(
        self, 
        reply_to_hash: str, 
        bot_username: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Check if bot is allowed to reply to a cast.
        
        Args:
            reply_to_hash: Hash of the cast to reply to
            bot_username: Bot's username for mention detection
            
        Returns:
            Tuple of (allowed: bool, reason: str)
        """
        try:
            if not self.farcaster_observer or not self.farcaster_observer.api_client:
                return False, "Farcaster API client not available"
                
            # Get the original cast details
            cast_details = await self.farcaster_observer.api_client.lookup_cast_by_hash(reply_to_hash)
            if not cast_details or "result" not in cast_details or "cast" not in cast_details["result"]:
                return False, f"Could not retrieve cast details for {reply_to_hash}"
            
            cast_data = cast_details["result"]["cast"]
            cast_text = cast_data.get("text", "")
            
            # Use bot username from settings if not provided
            if not bot_username:
                bot_username = settings.FARCASTER_BOT_USERNAME
            
            # HIGH PRIORITY: Check if this cast mentions the bot
            if FarcasterCastUtils.is_mention_to_bot(
                cast_content=cast_text,
                bot_fid=self.farcaster_observer.bot_fid,
                bot_username=bot_username
            ):
                return True, "Direct mention detected"
            
            # MEDIUM PRIORITY: Check if this is a reply to bot's own cast
            if cast_data.get("parent_hash") and self.world_state_manager:
                parent_hash = cast_data.get("parent_hash")
                if self.world_state_manager.is_bot_cast(parent_hash):
                    return True, "Reply to bot's own cast thread"
            
            # Check if this is a direct reply to one of bot's casts
            if cast_data.get("parent_author", {}).get("fid") == self.farcaster_observer.bot_fid:
                return True, "Direct reply to bot's cast"
            
            # If none of the above conditions are met, reject the reply
            return False, (
                f"Reply blocked by cast-first policy. Bot only replies to: "
                f"1) Direct mentions (@{bot_username}), "
                f"2) Replies in bot's own cast threads. "
                f"Cast {reply_to_hash} doesn't meet these criteria."
            )
            
        except Exception as e:
            logger.warning(f"Error checking reply eligibility for cast {reply_to_hash}: {e}")
            return False, f"Could not verify reply eligibility: {str(e)}"
    
    async def is_mention_to_bot(self, reply_to_hash: str, bot_username: Optional[str] = None) -> bool:
        """
        Check if a specific cast mentions the bot.
        
        Args:
            reply_to_hash: Hash of the cast to check
            bot_username: Bot's username
            
        Returns:
            True if the cast mentions the bot
        """
        try:
            if not self.farcaster_observer or not self.farcaster_observer.api_client:
                return False
                
            cast_details = await self.farcaster_observer.api_client.lookup_cast_by_hash(reply_to_hash)
            if cast_details and "result" in cast_details and "cast" in cast_details["result"]:
                cast_data = cast_details["result"]["cast"]
                cast_text = cast_data.get("text", "")
                
                if not bot_username:
                    bot_username = settings.FARCASTER_BOT_USERNAME
                
                return FarcasterCastUtils.is_mention_to_bot(
                    cast_content=cast_text,
                    bot_fid=self.farcaster_observer.bot_fid,
                    bot_username=bot_username
                )
            
            return False
            
        except Exception as e:
            logger.warning(f"Could not check if cast {reply_to_hash} is a mention: {e}")
            return False


class DuplicateGuardService:
    """
    Service for comprehensive duplicate checking.
    Extracted from SendFarcasterReplyTool to reduce complexity.
    """
    
    def __init__(self, world_state_manager=None, farcaster_observer=None):
        self.world_state_manager = world_state_manager
        self.farcaster_observer = farcaster_observer
    
    def check_self_reply(self, reply_to_hash: str) -> bool:
        """Check if trying to reply to own cast."""
        if not self.world_state_manager:
            return False
        return self.world_state_manager.is_bot_cast(reply_to_hash)
    
    def check_already_replied(self, reply_to_hash: str) -> bool:
        """Check if bot has already replied to this cast."""
        if not self.world_state_manager:
            return False
        return self.world_state_manager.has_replied_to_cast(reply_to_hash)
    
    def check_conversation_flow(self, reply_to_hash: str, bot_fid: str) -> bool:
        """Check if bot was last to reply in thread."""
        try:
            if not self.world_state_manager or not bot_fid:
                return False
                
            # This would need implementation in world_state_manager
            if hasattr(self.world_state_manager, 'was_last_to_reply_in_thread'):
                # Get thread hash (this is simplified)
                thread_hash = reply_to_hash  # In real implementation, get from cast data
                return self.world_state_manager.was_last_to_reply_in_thread(thread_hash, bot_fid)
            
            return False
            
        except Exception as e:
            logger.warning(f"Could not check conversation flow for {reply_to_hash}: {e}")
            return False
    
    async def authoritative_duplicate_check(self, reply_to_hash: str, bot_fid: str) -> bool:
        """
        Check on-chain state for existing bot replies.
        
        Returns:
            True if duplicate found (should not reply)
        """
        try:
            if not self.farcaster_observer or not self.farcaster_observer.api_client or not bot_fid:
                return False
                
            conversation = await self.farcaster_observer.api_client.lookup_cast_conversation(reply_to_hash)
            
            if conversation and "result" in conversation and "conversation" in conversation["result"]:
                # Check both direct replies and nested conversation
                all_casts = conversation["result"]["conversation"].get("cast", {}).get("direct_replies", [])
                
                # Also check if the conversation has a nested structure
                if "casts" in conversation["result"]["conversation"]:
                    all_casts.extend(conversation["result"]["conversation"]["casts"])
                
                for cast in all_casts:
                    if cast and "author" in cast and "fid" in cast["author"]:
                        if str(cast["author"]["fid"]) == str(bot_fid):
                            logger.warning(f"Authoritative check: Bot (FID {bot_fid}) already replied to cast {reply_to_hash}")
                            return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed authoritative duplicate check for cast {reply_to_hash}: {e}")
            return False  # Don't block on API errors


class ReplyExecutor:
    """
    Service for executing replies with proper error handling.
    Extracted from SendFarcasterReplyTool to reduce complexity.
    """
    
    def __init__(self, farcaster_observer=None, world_state_manager=None):
        self.farcaster_observer = farcaster_observer
        self.world_state_manager = world_state_manager
    
    async def execute_reply(
        self, 
        content: str, 
        reply_to_hash: str,
        action_type: str = "send_farcaster_reply"
    ) -> Dict[str, Any]:
        """
        Execute a reply with proper scheduling or immediate execution.
        
        Args:
            content: Reply content
            reply_to_hash: Hash of cast to reply to
            action_type: Type of action for logging
            
        Returns:
            Result dictionary
        """
        try:
            if not self.farcaster_observer:
                return {
                    "status": "failure",
                    "error": "Farcaster observer not available",
                    "timestamp": time.time()
                }
            
            # Check if scheduling is supported
            reply_q = getattr(self.farcaster_observer, "reply_queue", None)
            
            if isinstance(reply_q, asyncio.Queue):
                # Scheduled execution
                return await self._schedule_reply(content, reply_to_hash, action_type)
            else:
                # Immediate execution
                return await self._immediate_reply(content, reply_to_hash, action_type)
                
        except Exception as e:
            error_msg = f"Error executing reply: {e}"
            logger.exception(error_msg)
            return {
                "status": "failure",
                "error": error_msg,
                "timestamp": time.time()
            }
    
    async def _schedule_reply(self, content: str, reply_to_hash: str, action_type: str) -> Dict[str, Any]:
        """Handle scheduled reply execution."""
        action_id = None
        if self.world_state_manager:
            action_id = self.world_state_manager.add_action_result(
                action_type=action_type,
                parameters={"content": content, "reply_to_hash": reply_to_hash},
                result="scheduled",
            )

        self.farcaster_observer.schedule_reply(content, reply_to_hash, action_id)
        
        return {
            "status": "scheduled",
            "message": f"Scheduled Farcaster reply to cast {reply_to_hash}",
            "reply_to_hash": reply_to_hash,
            "content": content,
            "action_id": action_id,
            "timestamp": time.time(),
        }
    
    async def _immediate_reply(self, content: str, reply_to_hash: str, action_type: str) -> Dict[str, Any]:
        """Handle immediate reply execution."""
        result = await self.farcaster_observer.reply_to_cast(content, reply_to_hash)
        
        # Record the action
        if self.world_state_manager:
            if result.get("success"):
                cast_hash = result.get("cast", {}).get("hash")
                self.world_state_manager.add_action_result(
                    action_type=action_type,
                    parameters={
                        "content": content,
                        "reply_to_hash": reply_to_hash,
                        "cast_hash": cast_hash,
                    },
                    result="success",
                )
            else:
                self.world_state_manager.add_action_result(
                    action_type=action_type,
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
