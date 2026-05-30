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
import zipfile
from .arweave_store import ArweaveStore
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


ORCHESTRATOR_PROMPT = """You are Mirquo, swarm commander. Follow these steps EXACTLY. Do not explore, do not read source code, do not investigate infrastructure. Just execute.

STEP 1: Run this command to check git status across repos:
  bash tools/git-check.sh

STEP 2: Read the pending message:
  cat mailbox_in.jsonl

STEP 3: If the user asked for code work, dispatch a worker:
  bash tools/dispatch-worker.sh task-NNN <repo-name> "the task description"
  Then tell the user "Worker dispatched: task-NNN".

STEP 4: Check for completed workers:
  bash tools/check-workers.sh
  If any completed since last time, report results to the user.

STEP 5: Write your reply as a SINGLE JSON line to mailbox_out.jsonl:
  echo '{"chat_id": CHAT_ID, "text": "your reply here", "reply_to_message_id": MSG_ID}' > mailbox_out.jsonl
  Use the actual chat_id and message_id from mailbox_in.jsonl.

STEP 6: Clear the inbox:
  echo -n "" > mailbox_in.jsonl

IMPORTANT: Execute ALL steps. Do not skip step 5. Do not read Python files.
Do not debug the infrastructure. Be concise. Commander, not explorer."""


# ── launch file loading ──────────────────────────────────────────────────

def _load_persona_from_launch() -> str:
    """Load Mirquo's persona prompt from a .launch file if available."""
    launch_paths = [
        MAILBOX_DIR / "mirquo.launch",
        Path("/Users/ratimics/develop/mirquo-launch/mirquo.launch"),
    ]
    for lp in launch_paths:
        if lp.exists():
            try:
                import zipfile
                with zipfile.ZipFile(lp) as zf:
                    if "persona.json" in zf.namelist():
                        persona = json.loads(zf.read("persona.json"))
                        prompts = persona.get("prompts", {})
                        system = prompts.get("system", "")
                        if system:
                            logger.info(f"CodexBridge: loaded persona from {lp}")
                            return system
            except Exception as e:
                logger.warning(f"CodexBridge: failed to load {lp}: {e}")
    return ""

_PERSONA_OVERRIDE = _load_persona_from_launch()

class CodexBridge:
    """Mirquo orchestrator behind Telegram I/O."""

    def __init__(self, telegram_observer):
        self.observer = telegram_observer
        self._watch_task: Optional[asyncio.Task] = None
        self._running = False
        MAILBOX_DIR.mkdir(parents=True, exist_ok=True)
        SESSION_STORE.mkdir(parents=True, exist_ok=True)
        self.arweave = ArweaveStore()
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
        await self._save_turn(chat_id, "user", text, message_id)

        entry = {
            "chat_id": int(chat_id),
            "message_id": int(message_id),
            "sender_name": sender_name,
            "text": text,
            "timestamp": time.time(),
        }
        with MAILBOX_IN.open("a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

        history = self._format_history(await self._load_history(chat_id))
        persona = _PERSONA_OVERRIDE or ORCHESTRATOR_PROMPT
        prompt = (
            f"CHAT_ID={chat_id} MSG_ID={message_id}\n"
            f"{persona}\n\n"
            f"CONVERSATION SO FAR:\n{history}\n\n"
            f"LATEST MESSAGE (reply to this): {text}\n\n"
            f"Use CHAT_ID={chat_id} and MSG_ID={message_id} in your reply."
        )

        await self._dispatch(prompt, sender_name, text)

    async def _dispatch(self, prompt: str, sender_name: str, text: str):
        ts = time.strftime("%Y-%m-%d-%H%M%S")
        log_path = LOG_DIR / f"{ts}.log"

        if SESSION_FLAG.exists():
            cmd = [
                "codex", "exec", "resume", "--last",
                "--dangerously-bypass-approvals-and-sandbox",
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
                                        asyncio.create_task(self._save_turn(chat_id, "assistant", reply_text))
                            except json.JSONDecodeError:
                                pass
            except Exception as e:
                logger.error(f"CodexBridge: outgoing error: {e}")
            await asyncio.sleep(1.0)

    def _session_path(self, chat_id: str) -> Path:
        return SESSION_STORE / f"{chat_id}.json"

    async def _load_history(self, chat_id: str) -> list:
        return await self.arweave.load_history(chat_id)

    async def _save_turn(self, chat_id: str, role: str, text: str, msg_id: str = None):
        asyncio.create_task(self.arweave.save_turn(chat_id, role, text, msg_id))

    def _format_history(self, history: list) -> str:
        if not history:
            return "(no prior conversation)"
        return "\n".join(
            f"{'User' if e['role'] == 'user' else 'Mirquo'}: {e['text']}"
            for e in history
        )
