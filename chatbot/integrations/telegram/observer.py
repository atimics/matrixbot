#!/usr/bin/env python3
"""
Telegram Observer

Observes Telegram chats and updates the world state with new messages.
Follows the same Integration pattern as the Matrix observer.
Uses raw httpx against the Telegram Bot API (no heavy framework dependency).
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from dotenv import load_dotenv

from ...config import settings
from ...core.world_state import Channel, Message, WorldStateManager
from ..base import Integration, IntegrationConnectionError

logger = logging.getLogger(__name__)
load_dotenv()

TELEGRAM_API = "https://api.telegram.org"


class TelegramObserver(Integration):
    """Observes Telegram chats and reports to world state."""

    def __init__(
        self,
        integration_id: str = "telegram",
        display_name: str = "Telegram Integration",
        config: Dict[str, Any] = None,
        world_state_manager: WorldStateManager = None,
    ):
        # Support legacy positional usage
        if not isinstance(integration_id, str) and world_state_manager is None:
            world_state_manager = integration_id
            integration_id = "telegram"
            display_name = "Telegram Integration"
            config = config or {}

        super().__init__(integration_id, display_name, config or {})
        self.world_state = world_state_manager
        self.token = settings.TELEGRAM_BOT_TOKEN
        self._http: Optional[httpx.AsyncClient] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._offset: int = 0
        self._connected = False
        self._bot_username: Optional[str] = None
        self._offset_file = Path("telegram_offset.txt")

        # Check configuration
        self._enabled = bool(self.token)
        if not self._enabled:
            logger.warning(
                "Telegram configuration incomplete. Set TELEGRAM_BOT_TOKEN."
            )
            return

        logger.info("TelegramObserver: Initialized")

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def integration_type(self) -> str:
        return "telegram"

    # ── Integration interface ────────────────────────────────────────────

    async def connect(self) -> None:
        if not self.enabled:
            raise IntegrationConnectionError(
                "Telegram observer is disabled — set TELEGRAM_BOT_TOKEN"
            )

        logger.info("TelegramObserver: Connecting…")
        self._http = httpx.AsyncClient(timeout=30.0)

        # Load saved offset
        self._load_offset()

        # Verify token
        me = await self._api("getMe")
        if not me.get("ok"):
            raise IntegrationConnectionError(
                f"Telegram getMe failed: {me.get('description', 'unknown')}"
            )
        self._bot_username = me["result"]["username"]
        logger.info(f"TelegramObserver: Connected as @{self._bot_username}")

        # Update world state
        if self.world_state:
            self.world_state.update_system_status({"telegram_connected": True})

        self._connected = True

        # Start polling
        self._poll_task = asyncio.create_task(self._poll_forever())
        logger.info("TelegramObserver: Polling started")

    async def disconnect(self) -> None:
        if not self.enabled:
            return

        logger.info("TelegramObserver: Disconnecting…")
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        if self._http:
            await self._http.aclose()
            self._http = None

        if self.world_state:
            self.world_state.update_system_status({"telegram_connected": False})

        self._connected = False
        logger.info("TelegramObserver: Disconnected")

    async def get_status(self) -> Dict[str, Any]:
        if not self.enabled:
            return {"connected": False, "enabled": False, "error": "Missing TELEGRAM_BOT_TOKEN"}

        return {
            "connected": self._connected,
            "enabled": self.enabled,
            "bot_username": self._bot_username,
            "poll_offset": self._offset,
        }

    async def test_connection(self) -> bool:
        if not self.enabled:
            return False
        try:
            resp = await self._api("getMe")
            return resp.get("ok", False)
        except Exception:
            return False

    # Legacy compat
    async def start(self):
        await self.connect()

    async def stop(self):
        await self.disconnect()

    # ── API helpers ──────────────────────────────────────────────────────

    async def _api(self, method: str, data: dict = None) -> dict:
        url = f"{TELEGRAM_API}/bot{self.token}/{method}"
        resp = await self._http.post(url, json=data or {})
        resp.raise_for_status()
        return resp.json()

    def _load_offset(self):
        try:
            self._offset = int(self._offset_file.read_text().strip())
        except (FileNotFoundError, ValueError):
            self._offset = 0

    def _save_offset(self):
        self._offset_file.write_text(str(self._offset))

    # ── Polling loop ─────────────────────────────────────────────────────

    async def _poll_forever(self):
        """Long-poll Telegram for new messages."""
        while True:
            try:
                result = await self._api("getUpdates", {
                    "offset": self._offset,
                    "timeout": 25,
                    "allowed_updates": ["message"],
                })

                if not result.get("ok"):
                    logger.warning(f"Telegram poll error: {result.get('description')}")
                    await asyncio.sleep(5)
                    continue

                for upd in result.get("result", []):
                    self._offset = upd["update_id"] + 1
                    self._save_offset()
                    msg = upd.get("message")
                    if msg:
                        await self._handle_message(msg)

                await asyncio.sleep(0.5)

            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"Telegram poll error: {e}")
                await asyncio.sleep(5)

    # ── Message handling ─────────────────────────────────────────────────

    async def _handle_message(self, msg: dict):
        """Process an incoming Telegram message into world state."""
        chat = msg.get("chat", {})
        sender = msg.get("from", {})
        chat_id = str(chat.get("id", ""))
        text = msg.get("text", "") or msg.get("caption", "") or "(non-text)"

        # Auto-register channel
        if self.world_state and chat_id not in self.world_state.state.channels:
            chat_name = chat.get("title") or chat.get("username") or sender.get("first_name", "Unknown")
            self.world_state.add_channel(chat_id, "telegram", chat_name)
            logger.info(f"TelegramObserver: Auto-registered chat {chat_name} ({chat_id})")

        # Build message
        message = Message(
            id=str(msg.get("message_id", "")),
            channel_id=chat_id,
            channel_type="telegram",
            sender=sender.get("username") or sender.get("first_name", "unknown"),
            content=text,
            timestamp=msg.get("date", time.time()),
            reply_to=str(msg.get("reply_to_message", {}).get("message_id", "")) or None,
            metadata={
                "chat_type": chat.get("type"),
                "sender_id": sender.get("id"),
                "sender_name": sender.get("first_name", ""),
            },
        )

        if self.world_state:
            self.world_state.add_message(chat_id, message)

        log_text = text[:100] + "…" if len(text) > 100 else text
        logger.info(
            f"TelegramObserver: {sender.get('first_name', '?')}: {log_text}"
        )

    # ── Sending ──────────────────────────────────────────────────────────

    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_to_message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a text message to a Telegram chat."""
        if not self._http:
            return {"success": False, "error": "Not connected"}

        data: dict = {"chat_id": int(chat_id), "text": text}
        if reply_to_message_id:
            data["reply_to_message_id"] = int(reply_to_message_id)

        try:
            result = await self._api("sendMessage", data)
            if result.get("ok"):
                logger.info(f"TelegramObserver: Sent to {chat_id}")
                return {"success": True, "message_id": result["result"]["message_id"]}
            return {"success": False, "error": result.get("description", "unknown")}
        except Exception as e:
            logger.error(f"TelegramObserver: Send failed: {e}")
            return {"success": False, "error": str(e)}

    async def send_typing(self, chat_id: str):
        """Send typing indicator."""
        if self._http:
            try:
                await self._api("sendChatAction", {
                    "chat_id": int(chat_id),
                    "action": "typing",
                })
            except Exception:
                pass
