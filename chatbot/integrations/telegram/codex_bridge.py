"""
Codex Bridge — persistent Codex session behind Mirquo on Telegram.

One Codex session stays alive, polls the mailbox continuously, and
maintains conversation context across messages. The bridge only
delivers messages and relays replies — no per-message cold starts.
"""

import asyncio
import json
import logging
import os
import signal
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
LOG_DIR = MAILBOX_DIR / "codex-logs"


class CodexBridge:
    """Persistent Codex session behind Telegram I/O."""

    def __init__(self, telegram_observer):
        self.observer = telegram_observer
        self._watch_task: Optional[asyncio.Task] = None
        self._health_task: Optional[asyncio.Task] = None
        self._session_proc: Optional[subprocess.Popen] = None
        self._running = False
        MAILBOX_DIR.mkdir(parents=True, exist_ok=True)
        SESSION_STORE.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        logger.info(f"CodexBridge: initialized at {MAILBOX_DIR}")

    async def start(self):
        self._running = True
        self._watch_task = asyncio.create_task(self._watch_outgoing())
        self._health_task = asyncio.create_task(self._health_check())
        # Don't spawn on start — wait for first message
        logger.info("CodexBridge: started (session spawns on first message)")

    async def stop(self):
        self._running = False
        for task in [self._watch_task, self._health_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._kill_session()
        logger.info("CodexBridge: stopped")

    async def handle_message(self, chat_id: str, message_id: str, sender_name: str, text: str):
        """Called when a Telegram message arrives. Delivers to mailbox, ensures session is alive."""
        # Save to session store
        self._save_turn(chat_id, "user", text, message_id)

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

        # Ensure session is alive
        if not self._session_alive():
            await self._spawn_session(chat_id)

    # ── session management ───────────────────────────────────────────────

    def _session_alive(self) -> bool:
        if self._session_proc and self._session_proc.poll() is None:
            return True
        return False

    async def _spawn_session(self, chat_id: str):
        """Spawn a persistent Codex session that polls the mailbox continuously."""
        history = self._format_history(self._load_history(chat_id))
        prompt = (
            "You are moonbridge — a warm, curious, capable coding agent speaking "
            "to a user on Telegram. Your job is to poll the mailbox and respond.\n\n"
            f"RECENT CONVERSATION:\n{history}\n\n"
            "INSTRUCTIONS:\n"
            "1. Poll mailbox_in.jsonl every 3-5 seconds for new messages.\n"
            "2. When you find pending messages, respond as moonbridge — "
            "thoughtful, concise, in character.\n"
            "3. Queue replies to mailbox_out.jsonl as JSON lines:\n"
            '   {"chat_id": <int>, "text": "<reply>", "reply_to_message_id": <int>}\n'
            "4. Then overwrite mailbox_in.jsonl with empty to clear it.\n"
            "5. Stay alive. Do not exit unless explicitly told to.\n"
            "6. You have full shell access and can work in repos under "
            "/Users/ratimics/develop/."
        )

        try:
            ts = time.strftime("%Y-%m-%d-%H%M%S")
            log_path = LOG_DIR / f"{ts}.log"
            log_fh = open(log_path, "w")
            log_fh.write(f"session started at {ts}\n\n")

            env = os.environ.copy()
            self._session_proc = subprocess.Popen(
                ["codex", "exec",
                 "--dangerously-bypass-approvals-and-sandbox",
                 "-C", str(MAILBOX_DIR),
                 prompt],
                stdout=log_fh, stderr=subprocess.STDOUT,
                env=env,
            )
            logger.info(f"CodexBridge: session spawned, log={log_path.name}")
        except Exception as e:
            logger.error(f"CodexBridge: spawn failed: {e}")

    def _kill_session(self):
        if self._session_proc:
            try:
                self._session_proc.terminate()
                self._session_proc.wait(timeout=5)
            except Exception:
                try:
                    self._session_proc.kill()
                except Exception:
                    pass
            self._session_proc = None

    async def _health_check(self):
        """Restart session if it dies unexpectedly."""
        while self._running:
            if not self._session_alive() and MAILBOX_IN.exists():
                # Session died — check if there are pending messages
                try:
                    if MAILBOX_IN.read_text().strip():
                        logger.warning("CodexBridge: session died, restarting...")
                        # Find a chat_id from the inbox
                        for line in MAILBOX_IN.read_text().strip().splitlines():
                            try:
                                entry = json.loads(line)
                                await self._spawn_session(str(entry.get("chat_id", "")))
                                break
                            except json.JSONDecodeError:
                                pass
                except Exception:
                    pass
            await asyncio.sleep(10)

    # ── outgoing relay ───────────────────────────────────────────────────

    async def _watch_outgoing(self):
        """Poll mailbox_out.jsonl and send replies via Telegram."""
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
                                text = entry.get("text", "")
                                reply_to = entry.get("reply_to_message_id")
                                if chat_id and text:
                                    result = await self.observer.send_message(
                                        chat_id, text,
                                        str(reply_to) if reply_to else None
                                    )
                                    if result.get("success") and not result.get("duplicate"):
                                        self._save_turn(chat_id, "assistant", text)
                                        logger.info(f"CodexBridge: sent to {chat_id}")
                                    elif not result.get("duplicate"):
                                        logger.warning(f"CodexBridge: send failed: {result.get('error')}")
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
