import os
import time
import json
import logging
import aiohttp
from typing import Dict, Any, List, Optional
from database import update_farcaster_bot_state, get_farcaster_bot_state

logger = logging.getLogger(__name__)

class FarcasterService:
    """Service for interacting with Farcaster via Neynar API."""
    
    def __init__(self, db_path: str, unified_channel_manager=None):
        self.db_path = db_path
        self.unified_channel_manager = unified_channel_manager
        self.neynar_api_key = os.getenv("NEYNAR_API_KEY")
        bot_fid_str = os.getenv("FARCASTER_BOT_FID")
        self.bot_signer_uuid = os.getenv("FARCASTER_BOT_SIGNER_UUID")
        self.base_url = "https://api.neynar.com/v2/farcaster"
        
        # Parse bot_fid as integer
        self.bot_fid = None
        if bot_fid_str:
            try:
                self.bot_fid = int(bot_fid_str)
            except ValueError:
                logger.error(f"FARCASTER_BOT_FID must be an integer, got: {bot_fid_str}")
                self.bot_fid = None
        
        if not self.neynar_api_key:
            logger.warning("NEYNAR_API_KEY not set - Farcaster functionality will be disabled")
        if not self.bot_fid:
            logger.warning("FARCASTER_BOT_FID not set or invalid - Farcaster functionality will be disabled")
        if not self.bot_signer_uuid:
            logger.warning("FARCASTER_BOT_SIGNER_UUID not set - Farcaster write operations will be disabled")
    
    def _get_headers(self) -> Dict[str, str]:
        """Get headers for Neynar API requests."""
        return {
            "accept": "application/json",
            "api_key": self.neynar_api_key,
            "content-type": "application/json"
        }
    
    async def post_cast(self, text: str, channel_id: Optional[str] = None, 
                       embed_urls: Optional[List[str]] = None) -> Dict[str, Any]:
        """Post a new cast to Farcaster."""
        if not self.bot_signer_uuid:
            return {"success": False, "error": "Bot signer UUID not configured"}
        
        try:
            payload = {
                "signer_uuid": self.bot_signer_uuid,
                "text": text
            }
            
            if channel_id:
                payload["channel_id"] = channel_id
                
            if embed_urls:
                payload["embeds"] = [{"url": url} for url in embed_urls]
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/cast",
                    headers=self._get_headers(),
                    json=payload
                ) as response:
                    result = await response.json()
                    
                    if response.status == 200:
                        cast_hash = result.get("cast", {}).get("hash", "unknown")
                        logger.info(f"Farcaster: Successfully posted cast {cast_hash}")
                        
                        # Trigger context summarization after posting
                        await self._trigger_context_summarization(
                            f"Posted cast: '{text}' (hash: {cast_hash})"
                        )
                        
                        return {
                            "success": True,
                            "cast_hash": cast_hash,
                            "result": result
                        }
                    else:
                        error_msg = f"Failed to post cast: {result}"
                        logger.error(f"Farcaster: {error_msg}")
                        return {"success": False, "error": error_msg}
                        
        except Exception as e:
            error_msg = f"Error posting cast: {str(e)}"
            logger.error(f"Farcaster: {error_msg}")
            return {"success": False, "error": error_msg}
    
    async def get_home_feed(self, limit: int = 25) -> Dict[str, Any]:
        """Get the home feed for the bot."""
        if not self.bot_fid:
            return {"success": False, "error": "Bot FID not configured"}
        
        try:
            params = {
                "fid": self.bot_fid,
                "limit": min(limit, 50)  # Cap at 50
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/feed/following",
                    headers=self._get_headers(),
                    params=params
                ) as response:
                    result = await response.json()
                    
                    if response.status == 200:
                        casts = result.get("casts", [])
                        logger.info(f"Farcaster: Retrieved {len(casts)} casts from home feed")
                        
                        # Update unified channel manager if available
                        if self.unified_channel_manager:
                            await self.unified_channel_manager.update_farcaster_home_feed(casts)
                        
                        # Update feed retrieval timestamp
                        await update_farcaster_bot_state(
                            self.db_path,
                            last_feed_timestamp=time.time()
                        )
                        
                        # Trigger context summarization with feed data
                        feed_summary = self._summarize_feed_casts(casts)
                        await self._trigger_context_summarization(
                            f"Retrieved home feed ({len(casts)} casts): {feed_summary}"
                        )
                        
                        return {
                            "success": True,
                            "casts": casts,
                            "count": len(casts)
                        }
                    else:
                        error_msg = f"Failed to get home feed: {result}"
                        logger.error(f"Farcaster: {error_msg}")
                        return {"success": False, "error": error_msg}
                        
        except Exception as e:
            error_msg = f"Error getting home feed: {str(e)}"
            logger.error(f"Farcaster: {error_msg}")
            return {"success": False, "error": error_msg}
    
    async def like_cast(self, target_cast_hash: str) -> Dict[str, Any]:
        """Like a specific cast."""
        if not self.bot_signer_uuid:
            return {"success": False, "error": "Bot signer UUID not configured"}
        
        try:
            payload = {
                "signer_uuid": self.bot_signer_uuid,
                "reaction_type": "like",
                "target": target_cast_hash
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/reaction",
                    headers=self._get_headers(),
                    json=payload
                ) as response:
                    result = await response.json()
                    
                    if response.status == 200:
                        logger.info(f"Farcaster: Successfully liked cast {target_cast_hash}")
                        return {
                            "success": True,
                            "target_cast_hash": target_cast_hash,
                            "result": result
                        }
                    else:
                        error_msg = f"Failed to like cast: {result}"
                        logger.error(f"Farcaster: {error_msg}")
                        return {"success": False, "error": error_msg}
                        
        except Exception as e:
            error_msg = f"Error liking cast: {str(e)}"
            logger.error(f"Farcaster: {error_msg}")
            return {"success": False, "error": error_msg}
    
    async def reply_to_cast(self, text: str, parent_cast_hash: str, 
                           channel_id: Optional[str] = None, 
                           embed_urls: Optional[List[str]] = None) -> Dict[str, Any]:
        """Reply to a specific cast."""
        if not self.bot_signer_uuid:
            return {"success": False, "error": "Bot signer UUID not configured"}
        
        try:
            payload = {
                "signer_uuid": self.bot_signer_uuid,
                "text": text,
                "parent": parent_cast_hash
            }
            
            if channel_id:
                payload["channel_id"] = channel_id
                
            if embed_urls:
                payload["embeds"] = [{"url": url} for url in embed_urls]
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/cast",
                    headers=self._get_headers(),
                    json=payload
                ) as response:
                    result = await response.json()
                    
                    if response.status == 200:
                        reply_hash = result.get("cast", {}).get("hash", "unknown")
                        logger.info(f"Farcaster: Successfully replied to cast {parent_cast_hash} with {reply_hash}")
                        
                        # Trigger context summarization after replying
                        await self._trigger_context_summarization(
                            f"Replied to cast {parent_cast_hash}: '{text}' (reply hash: {reply_hash})"
                        )
                        
                        return {
                            "success": True,
                            "reply_hash": reply_hash,
                            "parent_cast_hash": parent_cast_hash,
                            "result": result
                        }
                    else:
                        error_msg = f"Failed to reply to cast: {result}"
                        logger.error(f"Farcaster: {error_msg}")
                        return {"success": False, "error": error_msg}
                        
        except Exception as e:
            error_msg = f"Error replying to cast: {str(e)}"
            logger.error(f"Farcaster: {error_msg}")
            return {"success": False, "error": error_msg}
    
    async def get_notifications(self, limit: int = 25, 
                               filter_types: Optional[List[str]] = None) -> Dict[str, Any]:
        """Get notifications for the bot."""
        if not self.bot_fid:
            return {"success": False, "error": "Bot FID not configured"}
        
        try:
            params = {
                "fid": self.bot_fid,
                "limit": min(limit, 50)  # Cap at 50
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/notifications",
                    headers=self._get_headers(),
                    params=params
                ) as response:
                    result = await response.json()
                    
                    if response.status == 200:
                        notifications = result.get("notifications", [])
                        
                        # Filter notifications if requested
                        if filter_types:
                            notifications = [
                                n for n in notifications 
                                if n.get("type") in filter_types
                            ]
                        
                        # Filter out already processed notifications
                        state = await get_farcaster_bot_state(self.db_path)
                        processed_ids = state.get("processed_notification_ids", [])
                        new_notifications = [
                            n for n in notifications 
                            if n.get("id") not in processed_ids
                        ]
                        
                        logger.info(f"Farcaster: Retrieved {len(new_notifications)} new notifications")
                        
                        # Update unified channel manager if available
                        if self.unified_channel_manager:
                            await self.unified_channel_manager.update_farcaster_notifications(new_notifications)
                        
                        # Update processed notification IDs and timestamp
                        all_ids = processed_ids + [n.get("id") for n in new_notifications if n.get("id")]
                        # Keep only recent IDs to prevent unbounded growth
                        recent_ids = all_ids[-1000:] if len(all_ids) > 1000 else all_ids
                        
                        mentions_summary = self._summarize_notifications(new_notifications)
                        
                        await update_farcaster_bot_state(
                            self.db_path,
                            last_notification_timestamp=time.time(),
                            processed_notification_ids=recent_ids,
                            recent_mentions_summary=mentions_summary
                        )
                        
                        return {
                            "success": True,
                            "notifications": new_notifications,
                            "count": len(new_notifications),
                            "mentions_summary": mentions_summary
                        }
                    else:
                        error_msg = f"Failed to get notifications: {result}"
                        logger.error(f"Farcaster: {error_msg}")
                        return {"success": False, "error": error_msg}
                        
        except Exception as e:
            error_msg = f"Error getting notifications: {str(e)}"
            logger.error(f"Farcaster: {error_msg}")
            return {"success": False, "error": error_msg}
    
    def _summarize_feed_casts(self, casts: List[Dict[str, Any]]) -> str:
        """Create a brief summary of feed casts."""
        if not casts:
            return "No casts in feed"
        
        # Extract key information from casts
        authors = set()
        topics = []
        
        for cast in casts[:10]:  # Summarize first 10 casts
            author = cast.get("author", {}).get("username", "unknown")
            authors.add(author)
            
            text = cast.get("text", "")
            if text:
                topics.append(text[:50])  # First 50 chars
        
        summary_parts = []
        if authors:
            summary_parts.append(f"Authors: {', '.join(list(authors)[:5])}")
        if topics:
            summary_parts.append(f"Recent topics: {'; '.join(topics[:3])}")
        
        return " | ".join(summary_parts)
    
    def _summarize_notifications(self, notifications: List[Dict[str, Any]]) -> str:
        """Create a detailed summary of notifications including cast hashes for replies."""
        if not notifications:
            return ""
        
        mentions = [n for n in notifications if n.get("type") == "mention"]
        replies = [n for n in notifications if n.get("type") == "reply"]
        likes = [n for n in notifications if n.get("type") == "like"]
        
        summary_parts = []
        
        # Include mentions with cast hashes for replies
        if mentions:
            mention_details = []
            for mention in mentions[:3]:  # Limit to 3 most recent mentions
                cast = mention.get("cast", {})
                cast_hash = cast.get("hash", "unknown")
                author = cast.get("author", {}).get("username", "unknown")
                text_preview = (cast.get("text", "")[:50] + "...") if len(cast.get("text", "")) > 50 else cast.get("text", "")
                mention_details.append(f"@{author} (hash: {cast_hash}): {text_preview}")
            
            if mention_details:
                summary_parts.append(f"Recent mentions: {' | '.join(mention_details)}")
            else:
                summary_parts.append(f"{len(mentions)} mentions")
        
        # Include replies with cast hashes
        if replies:
            reply_details = []
            for reply in replies[:2]:  # Limit to 2 most recent replies
                cast = reply.get("cast", {})
                cast_hash = cast.get("hash", "unknown")
                author = cast.get("author", {}).get("username", "unknown")
                text_preview = (cast.get("text", "")[:50] + "...") if len(cast.get("text", "")) > 50 else cast.get("text", "")
                reply_details.append(f"@{author} (hash: {cast_hash}): {text_preview}")
            
            if reply_details:
                summary_parts.append(f"Recent replies: {' | '.join(reply_details)}")
            else:
                summary_parts.append(f"{len(replies)} replies")
        
        if likes:
            summary_parts.append(f"{len(likes)} likes")
        
        return " | ".join(summary_parts)
    
    async def _trigger_context_summarization(self, new_activity: str) -> None:
        """Trigger Farcaster context summarization (placeholder for now)."""
        # This will be implemented when we integrate with the AI service
        # For now, just log the activity
        logger.info(f"Farcaster: Context update - {new_activity}")
        
        # TODO: Integrate with AIInferenceService for summarization
        # This would call the Farcaster Context Summarizer AI
        pass

    async def quote_cast(self, text: str, quoted_cast_hash: str, 
                        channel_id: Optional[str] = None, 
                        embed_urls: Optional[List[str]] = None) -> Dict[str, Any]:
        """Quote a specific cast with additional commentary."""
        if not self.bot_signer_uuid:
            return {"success": False, "error": "Bot signer UUID not configured"}
        
        try:
            payload = {
                "signer_uuid": self.bot_signer_uuid,
                "text": text,
                "embeds": [{"cast_id": {"hash": quoted_cast_hash}}]
            }
            
            if channel_id:
                payload["channel_id"] = channel_id
                
            if embed_urls:
                # Add URL embeds in addition to the quoted cast
                if "embeds" not in payload:
                    payload["embeds"] = []
                payload["embeds"].extend([{"url": url} for url in embed_urls])
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/cast",
                    headers=self._get_headers(),
                    json=payload
                ) as response:
                    result = await response.json()
                    
                    if response.status == 200:
                        quote_hash = result.get("cast", {}).get("hash", "unknown")
                        logger.info(f"Farcaster: Successfully quoted cast {quoted_cast_hash} with {quote_hash}")
                        
                        # Trigger context summarization after quoting
                        await self._trigger_context_summarization(
                            f"Quoted cast {quoted_cast_hash}: '{text}' (quote hash: {quote_hash})"
                        )
                        
                        return {
                            "success": True,
                            "quote_hash": quote_hash,
                            "quoted_cast_hash": quoted_cast_hash,
                            "result": result
                        }
                    else:
                        error_msg = f"Failed to quote cast: {result}"
                        logger.error(f"Farcaster: {error_msg}")
                        return {"success": False, "error": error_msg}
                        
        except Exception as e:
            error_msg = f"Error quoting cast: {str(e)}"
            logger.error(f"Farcaster: {error_msg}")
            return {"success": False, "error": error_msg}