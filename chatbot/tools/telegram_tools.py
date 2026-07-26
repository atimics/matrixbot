"""
Telegram platform-specific tools for ratichat.
"""
import logging
import time
from typing import Any, Dict

from .base import ActionContext, ToolInterface

logger = logging.getLogger(__name__)


class SendTelegramMessageTool(ToolInterface):
    """Send a message to a Telegram chat."""

    @property
    def name(self) -> str:
        return "send_telegram_message"

    @property
    def description(self) -> str:
        return (
            "Send a text message to a Telegram chat. Use this to respond to users "
            "who messaged you on Telegram. The chat_id comes from the message's channel_id."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "chat_id": "string (Telegram chat ID) — the chat to send to",
            "content": "string — the message text to send",
            "reply_to_id": "string (optional) — message ID to reply to",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        logger.info("Executing Telegram message tool")

        observer = getattr(context, "telegram_observer", None)
        if not observer:
            return {"status": "failure", "error": "Telegram observer not connected", "timestamp": time.time()}

        chat_id = params.get("chat_id")
        content = params.get("content")
        reply_to = params.get("reply_to_id")

        if not chat_id:
            return {"status": "failure", "error": "Missing chat_id", "timestamp": time.time()}
        if not content:
            return {"status": "failure", "error": "Missing content", "timestamp": time.time()}

        result = await observer.send_message(str(chat_id), str(content), str(reply_to) if reply_to else None)
        if result.get("success"):
            return {"status": "success", "message_id": result.get("message_id"), "timestamp": time.time()}
        return {"status": "failure", "error": result.get("error", "unknown"), "timestamp": time.time()}


class SendTelegramReplyTool(ToolInterface):
    """Reply to a specific message in a Telegram chat."""

    @property
    def name(self) -> str:
        return "send_telegram_reply"

    @property
    def description(self) -> str:
        return (
            "Reply to a specific Telegram message. Use this when responding directly "
            "to a user's message. The reply_to_id is the message_id from the incoming message."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "chat_id": "string (Telegram chat ID)",
            "content": "string — the reply text",
            "reply_to_id": "string — the message ID to reply to",
        }

    async def execute(
        self, params: Dict[str, Any], context: ActionContext
    ) -> Dict[str, Any]:
        logger.info("Executing Telegram reply tool")

        observer = getattr(context, "telegram_observer", None)
        if not observer:
            return {"status": "failure", "error": "Telegram observer not connected", "timestamp": time.time()}

        chat_id = params.get("chat_id")
        content = params.get("content")
        reply_to = params.get("reply_to_id")

        if not chat_id or not content or not reply_to:
            return {"status": "failure", "error": "Missing chat_id, content, or reply_to_id", "timestamp": time.time()}

        result = await observer.send_message(str(chat_id), str(content), str(reply_to))
        if result.get("success"):
            return {"status": "success", "message_id": result.get("message_id"), "timestamp": time.time()}
        return {"status": "failure", "error": result.get("error", "unknown"), "timestamp": time.time()}
