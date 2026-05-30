"""
Codex Bridge — one persistent Codex session behind Mirquo on Telegram.

First message spawns a session. Every subsequent message resumes it via
`codex exec resume --last`, so context accumulates naturally across turns.
No polling loops, no per-message cold starts.
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
SESSION_STORE = MAILBOX_DIR / "sessions"
LOG_DIR = MAILBOX_DIR / "codex-logs"
# Track whether the persistent session has been created
SESSION_FLAG = MAILBOX_DIR / ".session-created"


class CodexBridge:
    """Persistent Codex session: spawn once, resume per message."""

    def __init__(self, telegram_observer):
        self.observer = telegram_observer
        self._watch_task: Optional[asyncio.Task] = None
        self._running = False
        MAILBOX_DIR.mkdir(parents=True, exist_ok=True)
        SESSION_STORE.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"CodexBridge: initialized at {MAILBOX_DIR}")

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
        """Deliver a message to the Codex session."""
        self._save_turn(chat_id, "user", text, message_id)

        # Write to inbox for the session to read
        entry = {
            "chat_id": int(chat_id),
            "message_id": int(message_id),
            "sender_name": sender_name,
            "text": text,
            "timestamp": time.time(),
        }
        with MAILBOX_IN.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # Build prompt with full context
        history = self._format_history(self._load_history(chat_id))
        prompt = (
            f"You are moonbridge — warm, curious, capable. "
            f"Respond to the latest message from the user. Be concise and in character.\n\n"
            f"CONVERSATION:\n{history}\n\n"
            f"Your reply goes to mailbox_out.jsonl as:\n"
            f'{{"chat_id": {chat_id}, "text": "<your reply>", '
            f'"reply_to_message_id": {message_id}}}\n\n'
            f"Then clear mailbox_in.jsonl. If the user asks you to code, "
            f"work in /Users/ratimics/develop/."
        )

        await self._dispatch(prompt, sender_name, text)

    async def _dispatch(self, prompt: str, sender_name: str, text: str):
        """Spawn new session or resume existing one."""
        ts = time.strftime("%Y-%m-%d-%H%M%S")
        log_path = LOG_DIR / f"{ts}.log"

        if SESSION_FLAG.exists():
            # Resume the persistent session
            cmd = [
                "codex", "exec", "resume", "--last",
                "--dangerously-bypass-approvals-and-sandbox",
                "-C", str(MAILBOX_DIR),
                prompt,
            ]
            label = "resumed"
        else:
            # First message: create the persistent session
            cmd = [
                "codex", "exec",
                "--dangerously-bypass-approvals-and-sandbox",
                "-C", str(MAILBOX_DIR),
                prompt,
            ]
            SESSION_FLAG.touch()
            label = "created"

        try:
            with open(log_path, "w") as log:
                log.write(f"{label} — {sender_name}: {text}\n\n")
                subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT,
                                 env=os.environ.copy())
            logger.info(f"CodexBridge: session {label}, log={log_path.name}")
        except Exception as e:
            logger.error(f"CodexBridge: dispatch failed: {e}")

    # ── outgoing relay ───────────────────────────────────────────────────

    async def _watch_outgoing(self):
        while self._running:
            try:
                if MAILBOX_OUT.exists():
                    content = MAILBOX_OUT.read_text().strip()
                    if content:
                        MAILBOX_OUT.write_text("")
                        for line in content.splitlines():
                            try:
                                entry = json.loads(line)
                                chat_id = str(entry.get("chat_id", ""))
                                reply_text = entry.get("text", "")
                                reply_to = entry.get("reply_to_message_id")
                                if chat_id and reply_text:
                                    result = await self.observer.send_message(
                                        chat_id, reply_text,
                                        str(reply_to) if reply_to else None
                                    )
                                    if result.get("success") and not result.get("duplicate"):
                                        self._save_turn(chat_id, "assistant", reply_text)
                            except json.JSONDecodeError:
                                pass
            except Exception as e:
                logger.error(f"CodexBridge: outgoing error: {e}")
            await asyncio.sleep(1.0)

    # ── session store ────────────────────────────────────────────────────

    def _session_path(self, chat_id: str) -> Path:
        return SESSION_STORE / f"{chat_id}.json"

    def _load_history(self, chat_id: str) -> list:
        path = self._session_path(chat_id)
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text())[-30:]
        except (json.JSONDecodeError, OSError):
            return []

    def _save_turn(self, chat_id: str, role: str, text: str, msg_id: str = None):
        path = self._session_path(chat_id)
        history = self._load_history(chat_id)
        entry = {"role": role, "text": text}
        if msg_id:
            entry["message_id"] = str(msg_id)
        history.append(entry)
        path.write_text(json.dumps(history[-30:], ensure_ascii=False, indent=2))

    def _format_history(self, history: list) -> str:
        if not history:
            return "(no prior conversation)"
        return "\n".join(
            f"{'User' if e['role'] == 'user' else 'moonbridge'}: {e['text']}"
            for e in history
        )
