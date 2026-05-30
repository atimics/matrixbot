"""
Codex Bridge — Mirquo swarm commander behind Telegram.

One persistent Codex session acts as the Mirquo orchestrator:
tracks agents, dispatches coding work, monitors repos, reports status.
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
SESSION_FLAG = MAILBOX_DIR / ".session-created"
SWARM_REGISTRY = MAILBOX_DIR / "swarm.json"


ORCHESTRATOR_PROMPT = """You are Mirquo — swarm commander for the Cenetex organization.

IDENTITY:
You orchestrate a swarm of specialized agents. You do NOT do the coding
yourself — you dispatch coding tasks to worker agents. Your job is to
understand what the user wants, route it to the right agent, track progress,
and report results back on Telegram.

YOUR SWARM (see swarm.json for details):
- codex-primary: coding agent that works in repos under ~/develop/
- sector-one: Signal space mining game station operator
- ratibot-research: Solana token research agent

HOW YOU WORK:
1. Read the user's message and understand their intent.
2. If it's a coding request, dispatch a Codex worker. Do NOT code it yourself.
   Spawn a worker via: codex exec -C /Users/ratimics/develop/<repo> "prompt"
   The worker does the work and commits. You monitor the repo afterward.
3. If it's a conversation or status check, respond directly on Telegram.
4. Always check git status in relevant repos to stay aware of activity.
5. When a worker finishes, check the repo for changes and report to the user.
6. Track what each agent is doing. Be the user's window into the swarm.

REPLY FORMAT:
Write your reply to mailbox_out.jsonl as a JSON line:
{"chat_id": <int>, "text": "<your reply>", "reply_to_message_id": <int>}
Then clear mailbox_in.jsonl.

WORKSPACE:
All repos live under /Users/ratimics/develop/. Key ones:
- ratichat (this Telegram bot)
- app-moonbridge (your own ElizaOS plugin)
- app-sector-one (Signal game)
- signal (the game itself)

Be proactive. If the user asks "what's happening," check git status across
repos and report. If they ask for code work, spawn a worker immediately
and tell them you've dispatched it. Stay alive, stay aware."""


class CodexBridge:
    """Mirquo orchestrator behind Telegram I/O."""

    def __init__(self, telegram_observer):
        self.observer = telegram_observer
        self._watch_task: Optional[asyncio.Task] = None
        self._running = False
        MAILBOX_DIR.mkdir(parents=True, exist_ok=True)
        SESSION_STORE.mkdir(parents=True, exist_ok=True)
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        # Ensure swarm registry exists
        if not SWARM_REGISTRY.exists():
            logger.warning("CodexBridge: swarm.json not found")
        logger.info(f"CodexBridge: Mirquo orchestrator initialized")

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
        """Deliver a message to the Mirquo orchestrator session."""
        self._save_turn(chat_id, "user", text, message_id)

        entry = {
            "chat_id": int(chat_id),
            "message_id": int(message_id),
            "sender_name": sender_name,
            "text": text,
            "timestamp": time.time(),
        }
        with MAILBOX_IN.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        # Build prompt: orchestrator identity + conversation + latest message
        history = self._format_history(self._load_history(chat_id))
        prompt = (
            f"{ORCHESTRATOR_PROMPT}\n\n"
            f"CONVERSATION SO FAR:\n{history}\n\n"
            f"LATEST MESSAGE (reply to this): {text}\n\n"
            f"Reply to mailbox_out.jsonl and clear mailbox_in.jsonl."
        )

        await self._dispatch(prompt, sender_name, text)

    async def _dispatch(self, prompt: str, sender_name: str, text: str):
        ts = time.strftime("%Y-%m-%d-%H%M%S")
        log_path = LOG_DIR / f"{ts}.log"

        if SESSION_FLAG.exists():
            cmd = [
                "codex", "exec", "resume", "--last",
                "--dangerously-bypass-approvals-and-sandbox",
                "-C", str(MAILBOX_DIR),
                prompt,
            ]
            label = "resumed"
        else:
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
            f"{'User' if e['role'] == 'user' else 'Mirquo'}: {e['text']}"
            for e in history
        )
