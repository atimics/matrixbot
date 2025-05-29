#!/usr/bin/env python3
"""
Unified Channel Manager Service

This service manages a unified view of all channels (Matrix rooms, Farcaster home feed, 
Farcaster notifications) as persistent objects that the AI can interact with consistently.
It automatically updates Matrix channels on new messages and provides tools for 
updating Farcaster channels.
"""

import asyncio
import logging
import time
from typing import Dict, Any, List, Optional
from message_bus import MessageBus
from event_definitions import (
    MatrixMessageReceivedEvent, SendReplyCommand, SendMatrixMessageCommand
)
import database

logger = logging.getLogger(__name__)

class UnifiedChannelManager:
    """Manages unified channel system for Matrix and Farcaster."""
    
    def __init__(self, message_bus: MessageBus, db_path: str):
        self.bus = message_bus
        self.db_path = db_path
        self._stop_event = asyncio.Event()
        
        # Channel IDs for Farcaster virtual channels
        self.FARCASTER_HOME_CHANNEL_ID = "farcaster:home"
        self.FARCASTER_NOTIFICATIONS_CHANNEL_ID = "farcaster:notifications"
    
    async def run(self) -> None:
        """Start the unified channel manager."""
        logger.info("UnifiedChannelManager: Starting service...")
        
        # Subscribe to Matrix message events to auto-update Matrix channels
        await self.bus.subscribe("matrix_message_received", self._handle_matrix_message)
        
        # Subscribe to reply commands to track AI responses
        await self.bus.subscribe("send_reply_command", self._handle_ai_reply)
        await self.bus.subscribe("send_matrix_message_command", self._handle_ai_message)
        
        # Initialize Farcaster virtual channels
        await self._initialize_farcaster_channels()
        
        # Wait for stop signal
        await self._stop_event.wait()
        logger.info("UnifiedChannelManager: Service stopped")
    
    async def stop(self) -> None:
        """Stop the service."""
        self._stop_event.set()
    
    async def _initialize_farcaster_channels(self) -> None:
        """Initialize Farcaster virtual channels."""
        # Ensure Farcaster home channel exists
        await database.ensure_channel_exists(
            self.db_path,
            self.FARCASTER_HOME_CHANNEL_ID,
            "farcaster_home",
            "Farcaster Home Feed"
        )
        
        # Ensure Farcaster notifications channel exists
        await database.ensure_channel_exists(
            self.db_path,
            self.FARCASTER_NOTIFICATIONS_CHANNEL_ID,
            "farcaster_notifications", 
            "Farcaster Notifications"
        )
        
        logger.info("UnifiedChannelManager: Initialized Farcaster virtual channels")
    
    async def _handle_matrix_message(self, event: MatrixMessageReceivedEvent) -> None:
        """Handle incoming Matrix message by adding it to the unified channel system."""
        try:
            # Ensure the Matrix room exists as a channel
            await database.ensure_channel_exists(
                self.db_path,
                event.room_id,
                "matrix",
                event.room_display_name or "Matrix Room"
            )
            
            # Add the message to the channel
            await database.add_channel_message(
                self.db_path,
                channel_id=event.room_id,
                message_id=event.event_id_matrix,
                message_type="matrix_message",
                sender_id=event.sender_id,
                sender_display_name=event.sender_display_name,
                content=event.body,
                timestamp=event.timestamp.timestamp(),
                metadata={
                    "room_display_name": event.room_display_name,
                    "event_type": "matrix_message"
                }
            )
            
            logger.debug(f"UnifiedChannelManager: Added Matrix message to channel {event.room_id}")
            
        except Exception as e:
            logger.error(f"UnifiedChannelManager: Error handling Matrix message: {e}")
    
    async def _handle_ai_reply(self, command: SendReplyCommand) -> None:
        """Handle AI reply to mark the replied-to message as replied."""
        try:
            if command.reply_to_event_id:
                await database.mark_message_as_replied(
                    self.db_path,
                    command.room_id,
                    command.reply_to_event_id
                )
                logger.debug(f"UnifiedChannelManager: Marked message {command.reply_to_event_id} as replied")
        except Exception as e:
            logger.error(f"UnifiedChannelManager: Error handling AI reply: {e}")
    
    async def _handle_ai_message(self, command: SendMatrixMessageCommand) -> None:
        """Handle AI message to update channel timestamp."""
        try:
            # Update the channel's AI check timestamp since the AI is actively engaging
            await database.update_channel_ai_check_timestamp(self.db_path, command.room_id)
            logger.debug(f"UnifiedChannelManager: Updated AI check timestamp for {command.room_id}")
        except Exception as e:
            logger.error(f"UnifiedChannelManager: Error handling AI message: {e}")
    
    async def update_farcaster_home_feed(self, casts: List[Dict[str, Any]]) -> bool:
        """Update the Farcaster home feed channel with new casts."""
        try:
            for cast in casts:
                cast_hash = cast.get("hash", "")
                author = cast.get("author", {})
                author_display_name = author.get("display_name") or author.get("username", "Unknown")
                author_fid = str(author.get("fid", ""))
                
                content = cast.get("text", "")
                timestamp = cast.get("timestamp", time.time())
                
                # Parse timestamp if it's a string
                if isinstance(timestamp, str):
                    try:
                        import datetime
                        dt = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        timestamp = dt.timestamp()
                    except ValueError:
                        timestamp = time.time()
                
                metadata = {
                    "cast_hash": cast_hash,
                    "author_fid": author_fid,
                    "author_username": author.get("username", ""),
                    "channel_id": cast.get("channel", {}).get("id"),
                    "replies_count": cast.get("replies", {}).get("count", 0),
                    "reactions_count": cast.get("reactions", {}).get("count", 0),
                    "recasts_count": cast.get("recasts", {}).get("count", 0)
                }
                
                await database.add_channel_message(
                    self.db_path,
                    channel_id=self.FARCASTER_HOME_CHANNEL_ID,
                    message_id=cast_hash,
                    message_type="farcaster_cast",
                    sender_id=author_fid,
                    sender_display_name=author_display_name,
                    content=content,
                    timestamp=timestamp,
                    metadata=metadata
                )
            
            logger.info(f"UnifiedChannelManager: Updated Farcaster home feed with {len(casts)} casts")
            return True
            
        except Exception as e:
            logger.error(f"UnifiedChannelManager: Error updating Farcaster home feed: {e}")
            return False
    
    async def update_farcaster_notifications(self, notifications: List[Dict[str, Any]]) -> bool:
        """Update the Farcaster notifications channel with new notifications."""
        try:
            for notification in notifications:
                notification_id = notification.get("id", "")
                notification_type = notification.get("type", "")
                
                # Get the actor (who performed the action)
                actor = notification.get("actor", {})
                actor_display_name = actor.get("display_name") or actor.get("username", "Unknown")
                actor_fid = str(actor.get("fid", ""))
                
                # Build content based on notification type
                content = self._format_notification_content(notification)
                
                timestamp = notification.get("timestamp", time.time())
                if isinstance(timestamp, str):
                    try:
                        import datetime
                        dt = datetime.datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        timestamp = dt.timestamp()
                    except ValueError:
                        timestamp = time.time()
                
                # Get the cast being interacted with
                cast = notification.get("cast", {})
                cast_hash = cast.get("hash", "")
                
                metadata = {
                    "notification_type": notification_type,
                    "actor_fid": actor_fid,
                    "actor_username": actor.get("username", ""),
                    "cast_hash": cast_hash,
                    "cast_text": cast.get("text", ""),
                    "original_notification": notification
                }
                
                await database.add_channel_message(
                    self.db_path,
                    channel_id=self.FARCASTER_NOTIFICATIONS_CHANNEL_ID,
                    message_id=notification_id,
                    message_type="farcaster_notification",
                    sender_id=actor_fid,
                    sender_display_name=actor_display_name,
                    content=content,
                    timestamp=timestamp,
                    metadata=metadata,
                    replied_to_message_id=cast_hash if notification_type in ["reply", "mention"] else None
                )
            
            logger.info(f"UnifiedChannelManager: Updated Farcaster notifications with {len(notifications)} notifications")
            return True
            
        except Exception as e:
            logger.error(f"UnifiedChannelManager: Error updating Farcaster notifications: {e}")
            return False
    
    def _format_notification_content(self, notification: Dict[str, Any]) -> str:
        """Format notification content for display."""
        notification_type = notification.get("type", "")
        actor = notification.get("actor", {})
        actor_name = actor.get("display_name") or actor.get("username", "Someone")
        cast = notification.get("cast", {})
        cast_text = cast.get("text", "")[:100]  # Truncate for display
        
        if notification_type == "mention":
            return f"{actor_name} mentioned you in: {cast_text}"
        elif notification_type == "reply":
            return f"{actor_name} replied to your cast: {cast_text}"
        elif notification_type == "like":
            return f"{actor_name} liked your cast: {cast_text}"
        elif notification_type == "recast":
            return f"{actor_name} recasted your cast: {cast_text}"
        elif notification_type == "follow":
            return f"{actor_name} followed you"
        else:
            return f"{actor_name} {notification_type}: {cast_text}"
    
    async def get_channel_context(self, channel_id: str, limit: int = 20) -> Dict[str, Any]:
        """Get channel context for AI processing."""
        try:
            messages = await database.get_channel_messages(self.db_path, channel_id, limit)
            
            # Update AI check timestamp since we're providing context
            await database.update_channel_ai_check_timestamp(self.db_path, channel_id)
            
            return {
                "channel_id": channel_id,
                "messages": messages,
                "message_count": len(messages)
            }
            
        except Exception as e:
            logger.error(f"UnifiedChannelManager: Error getting channel context for {channel_id}: {e}")
            return {"channel_id": channel_id, "messages": [], "message_count": 0}
    
    async def get_channels_needing_attention(self) -> List[Dict[str, Any]]:
        """Get channels that need AI attention."""
        return await database.get_channels_needing_ai_attention(self.db_path)
    
    async def mark_farcaster_message_replied(self, channel_id: str, message_id: str) -> bool:
        """Mark a Farcaster message as replied to prevent duplicate responses."""
        return await database.mark_message_as_replied(self.db_path, channel_id, message_id)