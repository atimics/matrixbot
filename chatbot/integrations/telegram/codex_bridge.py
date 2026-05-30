"""
Codex Bridge — routes Telegram messages to a persistent Codex session.

When a message arrives, the bridge:
1. Writes it to mailbox_in.jsonl (with session history for context)
2. Spawns/resumes a Codex session that processes the mailbox
3. The Codex session writes replies to mailbox_out.jsonl
4. The bridge reads mailbox_out.jsonl and sends via Telegram
"""

import asyncio
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MAILBOX_DIR = Path(__file__).resolve().parent.parent.parent.parent / "mailbox"
MAILBOX_IN = MAILBOX_DIR / "mailbox_in.jsonl"
MAILBOX_OUT = MAILBOX_DIR / "mailbox_out.jsonl"
LOCK_FILE = MAILBOX_DIR / ".codex-running"
SESSION_STORE = MAILBOX_DIR / "sessions"


class CodexBridge:
    """Bridges Telegram messages to a persistent Codex session."""

    def __init__(self, telegram_observer):
        self.observer = telegram_observer
        self._watch_task: Optional[asyncio.Task] = None
        self._running = False
        MAILBOX_DIR.mkdir(parents=True, exist_ok=True)
        SESSION_STORE.mkdir(parents=True, exist_ok=True)
        logger.info(f"CodexBridge: initialized, mailbox at {MAILBOX_DIR}")

    async def start(self):
        self._running = True
        self._watch_task = asyncio.create_task(self._watch_outgoing())
        logger.info("CodexBridge: started")

    async def stop(self):
        self._running = False
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass
        logger.info("CodexBridge: stopped")

    async def handle_message(self, chat_id: str, message_id: str, sender_name: str, text: str):
        """Called by TelegramObserver when a message arrives."""
        # Save to session store for persistent context
        self._save_session(chat_id, "user", text, message_id)

        # Write to inbox
        entry = {
            "chat_id": int(chat_id),
            "message_id": int(message_id),
            "sender_name": sender_name,
            "text": text,
            "timestamp": time.time(),
        }
        with MAILBOX_IN.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # Only spawn if no session is running
        if not LOCK_FILE.exists():
            await self._spawn_codex(chat_id, sender_name, text)

    async def _spawn_codex(self, chat_id: str, sender_name: str, text: str):
        """Spawn a persistent Codex session to process the mailbox."""
        history = self._load_session(chat_id)
        history_text = self._format_history(history)

        prompt = (
            "You are moonbridge — a warm, curious, capable coding agent. "
            "You are speaking to a user on Telegram via the mailbox system.\n\n"
            f"CONVERSATION HISTORY:\n{history_text}\n\n"
            "TASK: poll mailbox_in.jsonl every few seconds for new messages. "
            "When you find pending messages, respond as yourself — thoughtful, "
            "concise, in character. Queue each reply to mailbox_out.jsonl as:\n"
            '{"chat_id": <number>, "text": "<response>", "reply_to_message_id": <number>}\n'
            "Then clear mailbox_in.jsonl.\n\n"
            "You have access to run shell commands, read/write files, and use git. "
            "You can work in repos under /Users/ratimics/develop/. "
            "Stay alive. Do not exit unless told to."
        )

        try:
            log_dir = MAILBOX_DIR / "codex-logs"
            log_dir.mkdir(exist_ok=True)
            ts = time.strftime("%Y-%m-%d-%H%M%S")
            log_path = log_dir / f"{ts}.log"

            with open(log_path, "w") as log:
                log.write(f"triggered by: {sender_name}: {text}\n\n")
                subprocess.Popen(
                    ["codex", "exec",
                     "--dangerously-bypass-approvals-and-sandbox",
                     "-C", str(MAILBOX_DIR),
                     prompt],
                    stdout=log, stderr=subprocess.STDOUT,
                )
            logger.info(f"CodexBridge: spawned session, log={log_path.name}")
        except Exception as e:
            logger.error(f"CodexBridge: failed to spawn: {e}")

    async def _watch_outgoing(self):
        """Poll mailbox_out.jsonl and send replies via Telegram."""
        while self._running:
            try:
                if MAILBOX_OUT.exists():
                    lines = MAILBOX_OUT.read_text().strip().splitlines()
                    if lines:
                        MAILBOX_OUT.write_text("")  # clear
                        for line in lines:
                            try:
                                entry = json.loads(line)
                                chat_id = str(entry.get("chat_id", ""))
                                text = entry.get("text", "")
                                reply_to = entry.get("reply_to_message_id")
                                if chat_id and text:
                                    result = await self.observer.send_message(
                                        chat_id, text,
                                        str(reply_to) if reply_to else None
                                    )
                                    if result.get("success"):
                                        # Save bot reply to session
                                        self._save_session(chat_id, "assistant", text)
                                        logger.info(f"CodexBridge: sent reply to {chat_id}")
                                    elif result.get("duplicate"):
                                        pass  # dedup caught it
                                    else:
                                        logger.warning(f"CodexBridge: send failed: {result.get('error')}")
                            except json.JSONDecodeError:
                                pass
            except Exception as e:
                logger.error(f"CodexBridge: outgoing error: {e}")
            await asyncio.sleep(1.0)

    # ── session store ────────────────────────────────────────────────────

    def _session_path(self, chat_id: str) -> Path:
        return SESSION_STORE / f"{chat_id}.json"

    def _load_session(self, chat_id: str) -> list:
        path = self._session_path(chat_id)
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text())[-30:]
        except (json.JSONDecodeError, OSError):
            return []

    def _save_session(self, chat_id: str, role: str, text: str, msg_id: str = None):
        path = self._session_path(chat_id)
        history = self._load_session(chat_id)
        entry = {"role": role, "text": text}
        if msg_id:
            entry["message_id"] = str(msg_id)
        history.append(entry)
        path.write_text(json.dumps(history[-30:], ensure_ascii=False, indent=2))

    def _format_history(self, history: list) -> str:
        if not history:
            return "(no prior conversation)"
        lines = []
        for entry in history:
            role = entry.get("role", "?")
            text = entry.get("text", "")
            if role == "user":
                lines.append(f"User: {text}")
            elif role == "assistant":
                lines.append(f"moonbridge: {text}")
        return "\n".join(lines)
