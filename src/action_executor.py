#!/usr/bin/env python3
"""
Action Executor

This module executes the actions selected by the AI decision engine.
It handles all the actual interactions with Matrix, Farcaster, etc.
"""

import asyncio
import logging
import time
from typing import Dict, List, Any, Optional

from ai_engine import ActionPlan

logger = logging.getLogger(__name__)

class ActionExecutor:
    """Executes actions selected by the AI"""
    
    def __init__(self):
        self.matrix_observer = None
        self.farcaster_observer = None
        
        logger.info("Action executor initialized")
    
    def set_matrix_observer(self, observer):
        """Set the Matrix observer for sending messages"""
        self.matrix_observer = observer
        logger.info("Matrix observer set in action executor")
    
    def set_farcaster_observer(self, observer):
        """Set the Farcaster observer for posting"""
        self.farcaster_observer = observer
        logger.info("Farcaster observer set in action executor")
    
    async def execute_action(self, action_type: str, parameters: Dict[str, Any]) -> str:
        """Execute a single action and return the result"""
        logger.info(f"Executing action: {action_type}")
        
        try:
            if action_type == "wait":
                return await self._wait_action(parameters)
            
            elif action_type == "send_matrix_message":
                return await self._send_matrix_message(parameters)
            
            elif action_type == "send_matrix_reply":
                return await self._send_matrix_reply(parameters)
            
            elif action_type == "send_farcaster_post":
                return await self._send_farcaster_post(parameters)
            
            elif action_type == "send_farcaster_reply":
                return await self._send_farcaster_reply(parameters)
            
            else:
                raise ValueError(f"Unknown action type: {action_type}")
                
        except Exception as e:
            error_msg = f"Failed to execute {action_type}: {str(e)}"
            logger.error(error_msg)
            return error_msg
    
    async def _wait_action(self, params: Dict[str, Any]) -> str:
        """Wait and observe - no action taken"""
        duration = params.get("duration", 1)
        await asyncio.sleep(duration)
        return f"Waited {duration} seconds and observed"
    
    async def _send_matrix_message(self, params: Dict[str, Any]) -> str:
        """Send a message to a Matrix channel"""
        if not self.matrix_observer:
            return "Error: Matrix observer not configured"
        
        room_id = params.get("room_id")
        content = params.get("content")
        
        if not room_id or not content:
            return "Error: Missing room_id or content for Matrix message"
        
        try:
            # Use the matrix observer to send message
            result = await self.matrix_observer.send_message(room_id, content)
            if result.get("success"):
                event_id = result.get("event_id", "unknown")
                return f"Sent Matrix message to {room_id} (event: {event_id})"
            else:
                return f"Failed to send Matrix message: {result.get('error', 'unknown error')}"
                
        except Exception as e:
            return f"Error sending Matrix message: {str(e)}"
    
    async def _send_matrix_reply(self, params: Dict[str, Any]) -> str:
        """Send a reply to a Matrix message"""
        if not self.matrix_observer:
            return "Error: Matrix observer not configured"
        
        room_id = params.get("room_id")
        content = params.get("content")
        reply_to_event_id = params.get("reply_to_event_id")
        
        if not all([room_id, content, reply_to_event_id]):
            return "Error: Missing required parameters for Matrix reply"
        
        try:
            result = await self.matrix_observer.send_reply(room_id, content, reply_to_event_id)
            if result.get("success"):
                event_id = result.get("event_id", "unknown")
                return f"Sent Matrix reply to {room_id} (event: {event_id})"
            else:
                return f"Failed to send Matrix reply: {result.get('error', 'unknown error')}"
                
        except Exception as e:
            return f"Error sending Matrix reply: {str(e)}"
    
    async def _send_farcaster_post(self, params: Dict[str, Any]) -> str:
        """Send a post to Farcaster"""
        if not self.farcaster_observer:
            return "Error: Farcaster observer not configured"
        
        content = params.get("content")
        channel = params.get("channel")
        
        if not content:
            return "Error: Missing content for Farcaster post"
        
        try:
            result = await self.farcaster_observer.post_cast(content, channel)
            if result.get("success"):
                cast_hash = result.get("cast_hash", "unknown")
                return f"Posted to Farcaster (hash: {cast_hash})"
            else:
                return f"Failed to post to Farcaster: {result.get('error', 'unknown error')}"
                
        except Exception as e:
            return f"Error posting to Farcaster: {str(e)}"
    
    async def _send_farcaster_reply(self, params: Dict[str, Any]) -> str:
        """Send a reply to a Farcaster cast"""
        if not self.farcaster_observer:
            return "Error: Farcaster observer not configured"
        
        content = params.get("content")
        reply_to = params.get("reply_to")
        channel = params.get("channel")
        
        if not content or not reply_to:
            return "Error: Missing content or reply_to for Farcaster reply"
        
        try:
            result = await self.farcaster_observer.post_cast(content, channel, reply_to)
            if result.get("success"):
                cast_hash = result.get("cast_hash", "unknown")
                return f"Replied on Farcaster (hash: {cast_hash})"
            else:
                return f"Failed to reply on Farcaster: {result.get('error', 'unknown error')}"
                
        except Exception as e:
            return f"Error replying on Farcaster: {str(e)}"
        if not self.matrix_client:
            raise RuntimeError("Matrix client not configured")
        
        channel_id = params["channel_id"]
        content = params["content"]
        
        logger.info(f"ActionExecutor: Sending Matrix message to {channel_id}")
        logger.info(f"ActionExecutor: Message content: {content[:200]}...")
        
        # This would be the actual Matrix API call
        # For now, we'll simulate it
        await asyncio.sleep(0.5)  # Simulate network delay
        
        # TODO: Implement actual Matrix message sending
        # response = await self.matrix_client.room_send(
        #     room_id=channel_id,
        #     message_type="m.room.message",
        #     content={"msgtype": "m.text", "body": content}
        # )
        
        return f"Sent Matrix message to {channel_id}"
    
    async def _send_matrix_reply(self, params: Dict[str, Any]) -> str:
        """Reply to a specific Matrix message"""
        if not self.matrix_client:
            raise RuntimeError("Matrix client not configured")
        
        channel_id = params["channel_id"]
        reply_to_id = params["reply_to_id"]
        content = params["content"]
        
        logger.info(f"ActionExecutor: Sending Matrix reply to {reply_to_id} in {channel_id}")
        logger.info(f"ActionExecutor: Reply content: {content[:200]}...")
        
        # This would be the actual Matrix API call
        # For now, we'll simulate it
        await asyncio.sleep(0.5)  # Simulate network delay
        
        # TODO: Implement actual Matrix reply sending
        # response = await self.matrix_client.room_send(
        #     room_id=channel_id,
        #     message_type="m.room.message",
        #     content={
        #         "msgtype": "m.text",
        #         "body": content,
        #         "m.relates_to": {"m.in_reply_to": {"event_id": reply_to_id}}
        #     }
        # )
        
        return f"Sent Matrix reply to {reply_to_id} in {channel_id}"
    
    async def _send_farcaster_post(self, params: Dict[str, Any]) -> str:
        """Post to Farcaster"""
        if not self.farcaster_client:
            raise RuntimeError("Farcaster client not configured")
        
        content = params["content"]
        
        logger.info(f"ActionExecutor: Posting to Farcaster")
        logger.info(f"ActionExecutor: Post content: {content[:200]}...")
        
        # This would be the actual Farcaster API call
        # For now, we'll simulate it
        await asyncio.sleep(0.5)  # Simulate network delay
        
        # TODO: Implement actual Farcaster posting
        # response = await self.farcaster_client.post(content)
        
        return f"Posted to Farcaster: {content[:50]}..."
