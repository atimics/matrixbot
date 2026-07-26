"""Local operator-review queue for authorized Telegram messages.

This module intentionally does not execute an agent, a shell, or any worker.
Telegram is an untrusted transport; converting a chat message directly into an
agent prompt would turn the bot token into remote-code-execution authority.
"""

import asyncio
import json
import logging
import os
import stat
import time
from pathlib import Path

from ...config import settings

logger = logging.getLogger(__name__)


class OperatorQueueBridge:
    """Persist bounded requests for a separately authenticated operator."""

    def __init__(self, telegram_observer):
        self.observer = telegram_observer
        self.queue_path = Path(settings.TELEGRAM_OPERATOR_QUEUE_PATH).expanduser()
        self.max_queue_bytes = max(1, settings.TELEGRAM_OPERATOR_QUEUE_MAX_BYTES)
        self._write_lock = asyncio.Lock()
        self._queued_ids: set[str] = set()
        self._running = False

    async def start(self) -> None:
        self.queue_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.queue_path.parent, 0o700)
        if self.queue_path.is_symlink():
            raise RuntimeError("Telegram operator queue must not be a symlink")
        if self.queue_path.exists() and not self.queue_path.is_file():
            raise RuntimeError("Telegram operator queue must be a regular file")
        if self.queue_path.exists():
            os.chmod(self.queue_path, 0o600)
        self._load_queued_ids()
        self._running = True
        logger.info("Telegram operator-review queue started")

    async def stop(self) -> None:
        self._running = False
        logger.info("Telegram operator-review queue stopped")

    async def handle_message(
        self,
        chat_id: str,
        message_id: str,
        sender_id: str,
        text: str,
    ) -> None:
        """Queue one already-authorized message and acknowledge receipt."""
        if not self._running:
            raise RuntimeError("Telegram operator queue is not running")

        entry = {
            "chat_id": chat_id,
            "message_id": message_id,
            "sender_id": sender_id,
            "text": text,
            "received_at": int(time.time()),
        }
        encoded = (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8")
        message_key = f"{chat_id}:{message_id}"

        queued = await self._append_bounded(message_key, encoded)
        response = (
            "Request queued for authenticated operator review."
            if queued
            else "Operator queue is full. Try again later."
        )
        await self.observer.send_message(chat_id, response, message_id)

    def _load_queued_ids(self) -> None:
        self._queued_ids.clear()
        if not self.queue_path.exists():
            return
        if self.queue_path.stat().st_size > self.max_queue_bytes:
            raise RuntimeError("Telegram operator queue exceeds its configured limit")
        for line in self.queue_path.read_text(encoding="utf-8").splitlines():
            try:
                entry = json.loads(line)
                self._queued_ids.add(
                    f"{entry['chat_id']}:{entry['message_id']}"
                )
            except (KeyError, TypeError, json.JSONDecodeError):
                raise RuntimeError("Telegram operator queue contains invalid data")

    async def _append_bounded(self, message_key: str, encoded: bytes) -> bool:
        async with self._write_lock:
            if message_key in self._queued_ids:
                return True
            current_size = (
                self.queue_path.stat().st_size if self.queue_path.exists() else 0
            )
            if current_size + len(encoded) > self.max_queue_bytes:
                logger.warning(
                    "Telegram operator queue rejected a message because it is full"
                )
                return False

            flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
            flags |= getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(self.queue_path, flags, 0o600)
            try:
                os.fchmod(fd, 0o600)
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise RuntimeError("Telegram operator queue is not a regular file")
                remaining = memoryview(encoded)
                while remaining:
                    written = os.write(fd, remaining)
                    if written < 1:
                        raise OSError("Could not append to Telegram operator queue")
                    remaining = remaining[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
            self._queued_ids.add(message_key)
            return True
