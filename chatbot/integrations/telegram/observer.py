#!/usr/bin/env python3
"""
Telegram Observer

Accepts authorized Telegram messages into a local operator-review queue.
Follows the same Integration pattern as the Matrix observer.
Uses raw httpx against the Telegram Bot API (no heavy framework dependency).
"""

import asyncio
import logging
import os
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Deque, Dict, Optional

import httpx

from ...config import settings
from ...core.world_state import WorldStateManager
from ..base import Integration, IntegrationConnectionError

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"


def parse_id_allowlist(raw_value: str) -> frozenset[str]:
    """Parse a comma-separated ID allowlist, ignoring empty entries."""
    return frozenset(value.strip() for value in raw_value.split(",") if value.strip())


class MessageRateLimiter:
    """Small in-memory sliding-window limiter keyed by authorized sender."""

    def __init__(self, limit_per_minute: int):
        if limit_per_minute < 1:
            raise ValueError("Telegram rate limit must be at least one message per minute")
        self.limit = limit_per_minute
        self._events: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str, now: Optional[float] = None) -> bool:
        current = time.monotonic() if now is None else now
        events = self._events[key]
        cutoff = current - 60.0
        while events and events[0] <= cutoff:
            events.popleft()
        if len(events) >= self.limit:
            return False
        events.append(current)
        return True


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
        self.operator_queue_bridge = None  # set by orchestrator after init
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.allowed_chat_ids = parse_id_allowlist(settings.TELEGRAM_ALLOWED_CHAT_IDS)
        self.allowed_sender_ids = parse_id_allowlist(
            settings.TELEGRAM_ALLOWED_SENDER_IDS
        )
        self.max_message_chars = settings.TELEGRAM_MAX_MESSAGE_CHARS
        if self.max_message_chars < 1 or self.max_message_chars > 4096:
            raise ValueError("TELEGRAM_MAX_MESSAGE_CHARS must be between 1 and 4096")
        self._rate_limiter = MessageRateLimiter(
            settings.TELEGRAM_MESSAGE_RATE_LIMIT_PER_MINUTE
        )
        self._http: Optional[httpx.AsyncClient] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._offset: int = 0
        self._connected = False
        self._bot_username: Optional[str] = None
        self._offset_file = Path(settings.TELEGRAM_OFFSET_PATH).expanduser()

        # Check configuration
        self._replied_ids: set[str] = set()  # dedup sent replies
        self._enabled = bool(
            self.token and self.allowed_chat_ids and self.allowed_sender_ids
        )
        if not self._enabled:
            logger.warning(
                "Telegram disabled: token plus non-empty chat and sender allowlists "
                "are required"
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
                "Telegram observer is disabled by incomplete authorization settings"
            )

        logger.info("TelegramObserver: Connecting…")
        self._http = httpx.AsyncClient(timeout=30.0)
        try:
            self._load_offset()
            me = await self._api("getMe")
            if not me.get("ok"):
                raise IntegrationConnectionError(
                    f"Telegram getMe failed: {me.get('description', 'unknown')}"
                )
        except Exception:
            await self._http.aclose()
            self._http = None
            raise
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
            return {
                "connected": False,
                "enabled": False,
                "error": "Missing Telegram token or authorization allowlist",
            }

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
            if self._offset < 0:
                raise ValueError("Telegram offset must not be negative")
        except (OSError, ValueError):
            self._offset = 0

    def _save_offset(self):
        self._offset_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary_path = self._offset_file.with_suffix(".tmp")
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        flags |= getattr(os, "O_CLOEXEC", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(temporary_path, flags, 0o600)
        try:
            os.fchmod(descriptor, 0o600)
            os.write(descriptor, str(self._offset).encode("ascii"))
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        os.replace(temporary_path, self._offset_file)

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
                    msg = upd.get("message")
                    if msg:
                        await self._handle_message(msg)
                    self._offset = upd["update_id"] + 1
                    self._save_offset()

                # Periodic dedup cleanup (keep last 5 min of IDs)
                if len(self._replied_ids) > 100:
                    self._replied_ids.clear()
                await asyncio.sleep(0.5)

            except asyncio.CancelledError:
                raise
            except Exception:
                # httpx exceptions can include the request URL, which contains
                # the Telegram bot token. Never render them into logs.
                logger.error("Telegram polling failed; retrying")
                await asyncio.sleep(5)

    # ── Message handling ─────────────────────────────────────────────────

    async def _handle_message(self, msg: dict):
        """Process an incoming Telegram message into world state."""
        chat = msg.get("chat", {})
        sender = msg.get("from", {})
        chat_id = str(chat.get("id", ""))
        sender_id = str(sender.get("id", ""))

        if (
            chat_id not in self.allowed_chat_ids
            or sender_id not in self.allowed_sender_ids
        ):
            logger.warning(
                "Telegram rejected unauthorized message chat_id=%s sender_id=%s",
                chat_id,
                sender_id,
            )
            return

        text = msg.get("text", "") or msg.get("caption", "")
        if not text:
            logger.info("Telegram ignored a non-text message from an authorized sender")
            return
        if len(text) > self.max_message_chars:
            await self.send_message(
                chat_id,
                f"Message exceeds the {self.max_message_chars}-character limit.",
                str(msg.get("message_id", "")) or None,
            )
            return
        if not self._rate_limiter.allow(f"{chat_id}:{sender_id}"):
            await self.send_message(
                chat_id,
                "Rate limit exceeded. Try again later.",
                str(msg.get("message_id", "")) or None,
            )
            return

        # Telegram is only an intake transport. A separately authenticated
        # operator decides whether queued requests become implementation work.
        if self.operator_queue_bridge:
            await self.operator_queue_bridge.handle_message(
                chat_id,
                str(msg.get("message_id", "")),
                sender_id,
                text,
            )
        else:
            raise RuntimeError("Telegram operator queue is unavailable")
        logger.info(
            "Telegram accepted message chat_id=%s sender_id=%s", chat_id, sender_id
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
        if chat_id not in self.allowed_chat_ids:
            logger.warning("Telegram blocked outbound message to unauthorized chat")
            return {"success": False, "error": "Unauthorized chat"}
        if not text or len(text) > 4096:
            return {"success": False, "error": "Invalid message length"}

        # Dedup: one reply per (chat, msg_id)
        dedup_key = f"{chat_id}:{reply_to_message_id}" if reply_to_message_id else None
        if dedup_key and dedup_key in self._replied_ids:
            logger.info(f"TelegramObserver: DEDUP skipped {dedup_key}")
            return {"success": True, "message_id": None, "duplicate": True}

        data: dict = {"chat_id": int(chat_id), "text": text}
        if reply_to_message_id:
            data["reply_to_message_id"] = int(reply_to_message_id)

        try:
            result = await self._api("sendMessage", data)
            if result.get("ok"):
                if dedup_key:
                    self._replied_ids.add(dedup_key)
                logger.info(f"TelegramObserver: Sent to {chat_id}")
                return {"success": True, "message_id": result["result"]["message_id"]}
            return {"success": False, "error": result.get("description", "unknown")}
        except Exception:
            logger.error("Telegram send failed")
            return {"success": False, "error": "Telegram request failed"}

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
