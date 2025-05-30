#!/usr/bin/env python3
"""
Action Executor

This module executes the actions selected by the AI decision engine.
It handles all the actual interactions with Matrix, Farcaster, etc.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from ..core.ai_engine import ActionPlan

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

    async def execute_action(
        self, action_type: str, parameters: Dict[str, Any]
    ) -> Dict[str, Any]:
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
                error_msg = f"Unknown action type: {action_type}"
                logger.error(error_msg)
                return {"status": "failure", "error": error_msg}

        except Exception as e:
            error_msg = f"Failed to execute {action_type}: {str(e)}"
            logger.error(error_msg)
            return {"status": "failure", "error": error_msg}

    async def _wait_action(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Wait and observe - no action taken"""
        duration = params.get("duration", 1)
        await asyncio.sleep(duration)
        message = f"Waited {duration} seconds and observed"
        return {"status": "success", "message": message}

    async def _send_matrix_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send a message to a Matrix channel"""
        if not self.matrix_observer:
            return {"status": "failure", "error": "Matrix observer not configured"}

        room_id = params.get("room_id")
        content = params.get("content")

        if not room_id or not content:
            return {
                "status": "failure",
                "error": "Missing room_id or content for Matrix message",
            }

        try:
            # Use the matrix observer to send message
            result = await self.matrix_observer.send_message(room_id, content)
            if result.get("success"):
                event_id = result.get("event_id", "unknown")
                msg = f"Sent Matrix message to {room_id} (event: {event_id})"
                logger.info(msg)
                return {
                    "status": "success",
                    "message": msg,
                    "event_id": event_id,
                    "room_id": room_id,
                    "sent_content": content,
                }
            else:
                err_msg = f"Failed to send Matrix message: {result.get('error', 'unknown error')}"
                logger.error(err_msg)
                return {"status": "failure", "error": err_msg}

        except Exception as e:
            err_msg = f"Error sending Matrix message: {str(e)}"
            logger.exception(err_msg)
            return {"status": "failure", "error": err_msg}

    async def _send_matrix_reply(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send a reply to a Matrix message"""
        logger.info(f"_send_matrix_reply called with params: {params}")

        if not self.matrix_observer:
            logger.error("Matrix observer not configured")
            return {"status": "failure", "error": "Matrix observer not configured"}

        # Handle both parameter naming conventions
        room_id = params.get("room_id") or params.get("channel_id")
        content = params.get("content")
        reply_to_event_id = params.get("reply_to_event_id") or params.get("reply_to_id")

        logger.info(
            f"Extracted params - room_id: {room_id}, content: {content[:100] if content else None}..., reply_to_event_id: {reply_to_event_id}"
        )

        if not all([room_id, content, reply_to_event_id]):
            missing = []
            if not room_id:
                missing.append("room_id/channel_id")
            if not content:
                missing.append("content")
            if not reply_to_event_id:
                missing.append("reply_to_event_id/reply_to_id")
            logger.error(f"Missing required parameters: {missing}")
            return {
                "status": "failure",
                "error": f"Missing required parameters for Matrix reply: {missing}",
            }

        try:
            logger.info(
                f"Calling matrix_observer.send_reply with room_id={room_id}, content_length={len(content)}, reply_to={reply_to_event_id}"
            )
            result = await self.matrix_observer.send_reply(
                room_id, content, reply_to_event_id
            )
            logger.info(f"Matrix observer send_reply returned: {result}")

            if result.get("success"):
                event_id = result.get("event_id", "unknown")
                success_msg = f"Sent Matrix reply to {room_id} (event: {event_id})"
                logger.info(success_msg)
                return {
                    "status": "success",
                    "message": success_msg,
                    "event_id": event_id,
                    "room_id": room_id,
                    "reply_to_event_id": reply_to_event_id,
                    "sent_content": content,
                }
            else:
                error_msg = f"Failed to send Matrix reply: {result.get('error', 'unknown error')}"
                logger.error(error_msg)
                return {"status": "failure", "error": error_msg}

        except Exception as e:
            error_msg = f"Error sending Matrix reply: {str(e)}"
            logger.error(error_msg)
            import traceback

            logger.error(f"Full traceback: {traceback.format_exc()}")
            return {"status": "failure", "error": error_msg}

    async def _send_farcaster_post(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send a post to Farcaster"""
        if not self.farcaster_observer:
            return {"status": "failure", "error": "Farcaster observer not configured"}

        content = params.get("content")
        channel = params.get("channel")

        if not content:
            return {"status": "failure", "error": "Missing content for Farcaster post"}

        try:
            result = await self.farcaster_observer.post_cast(content, channel)
            if result.get("success"):
                cast_hash = result.get("cast_hash", "unknown")
                msg = f"Posted to Farcaster (hash: {cast_hash})"
                logger.info(msg)
                return {
                    "status": "success",
                    "message": msg,
                    "cast_hash": cast_hash,
                    "channel": channel,
                    "sent_content": content,
                }
            else:
                err_msg = f"Failed to post to Farcaster: {result.get('error', 'unknown error')}"
                logger.error(err_msg)
                return {"status": "failure", "error": err_msg}

        except Exception as e:
            err_msg = f"Error posting to Farcaster: {str(e)}"
            logger.exception(err_msg)
            return {"status": "failure", "error": err_msg}

    async def _send_farcaster_reply(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send a reply to a Farcaster cast"""
        if not self.farcaster_observer:
            return {"status": "failure", "error": "Farcaster observer not configured"}

        content = params.get("content")
        reply_to = params.get("reply_to")
        channel = params.get("channel")

        if not content or not reply_to:
            return {
                "status": "failure",
                "error": "Missing content or reply_to for Farcaster reply",
            }

        try:
            result = await self.farcaster_observer.post_cast(content, channel, reply_to)
            if result.get("success"):
                cast_hash = result.get("cast_hash", "unknown")
                msg = f"Replied on Farcaster (hash: {cast_hash})"
                logger.info(msg)
                return {
                    "status": "success",
                    "message": msg,
                    "cast_hash": cast_hash,
                    "channel": channel,
                    "reply_to": reply_to,
                    "sent_content": content,
                }
            else:
                err_msg = f"Failed to reply on Farcaster: {result.get('error', 'unknown error')}"
                logger.error(err_msg)
                return {"status": "failure", "error": err_msg}

        except Exception as e:
            err_msg = f"Error replying on Farcaster: {str(e)}"
            logger.exception(err_msg)
            return {"status": "failure", "error": err_msg}
