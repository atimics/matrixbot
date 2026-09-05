"""Bounded Matrix management with durable receipts and a separate admin session."""

import asyncio
import hashlib
import json
import logging
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

SERVER_COMMANDS = {
    "uptime": "server uptime",
    "memory": "server memory-usage",
    "backup": "server backup-database",
    "list_backups": "server list-backups",
}
ROOM_OPERATIONS = {"name", "topic", "publish", "unpublish"}


class MatrixSteward:
    def __init__(self, config, db_path, transport=None):
        self.config = config
        self.db_path = db_path
        self.transport = transport
        self._lock = asyncio.Lock()

    def _client(self, token=None):
        return httpx.AsyncClient(
            base_url=self.config.MATRIX_HOMESERVER,
            headers={"Authorization": f"Bearer {token}"} if token else {},
            timeout=15,
            follow_redirects=False,
            transport=self.transport,
        )

    @contextmanager
    def _db(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.db_path, timeout=10)
        db.execute("""CREATE TABLE IF NOT EXISTS matrix_management_receipts (
            receipt_id TEXT PRIMARY KEY, source_event_id TEXT NOT NULL,
            operation TEXT NOT NULL, target TEXT NOT NULL,
            created_at REAL NOT NULL, result TEXT NOT NULL
        )""")
        try:
            with db:
                yield db
        finally:
            db.close()

    def _reserve(self, source_event_id, operation, target):
        receipt_id = hashlib.sha256(
            json.dumps([source_event_id, operation, target]).encode()
        ).hexdigest()
        with self._db() as db:
            row = db.execute(
                "SELECT result FROM matrix_management_receipts WHERE receipt_id=?",
                (receipt_id,),
            ).fetchone()
            if row:
                return receipt_id, json.loads(row[0])
            db.execute(
                "INSERT INTO matrix_management_receipts VALUES (?, ?, ?, ?, ?, ?)",
                (receipt_id, source_event_id, operation, target, time.time(),
                 json.dumps({"status": "pending", "message": "This action has a receipt; check its result before requesting it again."})),
            )
        return receipt_id, None

    def _finish(self, receipt_id, result):
        result = {**result, "receipt_id": receipt_id}
        with self._db() as db:
            db.execute(
                "UPDATE matrix_management_receipts SET result=? WHERE receipt_id=?",
                (json.dumps(result), receipt_id),
            )
        return result

    async def status(self, observer):
        async with self._client() as client:
            response = await client.get("/_matrix/client/versions")
            response.raise_for_status()
        return {
            "status": "success",
            "message": "Matrix API is healthy. Bot connection: " + ("ready." if observer and observer.client and observer.client.access_token else "waiting."),
            "matrix_api": "healthy",
            "matrix_versions": response.json().get("versions", []),
            "bot_connected": bool(observer and observer.client and observer.client.access_token),
            "management_ready": bool(self.config.MATRIX_ADMIN_ACCESS_TOKEN and self.config.MATRIX_ADMIN_ROOM_ID),
        }

    async def room_action(self, params, observer):
        room_id = params.get("room_id")
        operation = params.get("operation")
        allowed = {value.strip() for value in self.config.MATRIX_MANAGED_ROOM_IDS.split(",") if value.strip()}
        if room_id not in allowed or room_id in {self.config.MATRIX_ADMIN_ROOM_ID, self.config.MATRIX_CONTROL_ROOM_ID}:
            raise ValueError("Choose a configured public managed room")
        if operation not in ROOM_OPERATIONS:
            raise ValueError("Choose name, topic, publish, or unpublish")
        value = params.get("value")
        if operation in {"name", "topic"}:
            maximum = 100 if operation == "name" else 1000
            if not isinstance(value, str) or not value.strip() or len(value) > maximum:
                raise ValueError(f"Supply text between 1 and {maximum} characters")
        if not observer or not observer.client or not observer.client.access_token:
            raise ValueError("The bot must be connected to Matrix")
        source = params.get("source_event_id")
        if not isinstance(source, str) or not source.startswith("$"):
            raise ValueError("Supply a Matrix source event ID")
        async with self._lock:
            receipt_id, previous = self._reserve(source, operation, room_id)
            if previous:
                return {**previous, "replayed": True, "receipt_id": receipt_id}
            try:
                encoded_room = quote(room_id, safe="")
                token = (self.config.MATRIX_ADMIN_ACCESS_TOKEN if operation in {"publish", "unpublish"}
                         else observer.client.access_token)
                if not token:
                    raise ValueError("Configure the management session to publish a room")
                async with self._client(token) as client:
                    if operation in {"name", "topic"}:
                        response = await client.put(
                            f"/_matrix/client/v3/rooms/{encoded_room}/state/m.room.{operation}",
                            json={operation: value},
                        )
                    else:
                        response = await client.put(
                            f"/_matrix/client/v3/directory/list/room/{encoded_room}",
                            json={"visibility": "public" if operation == "publish" else "private"},
                        )
                    response.raise_for_status()
                return self._finish(receipt_id, {
                    "status": "success", "message": f"Room {operation} updated.",
                    "room_id": room_id, "event_id": response.json().get("event_id"),
                })
            except httpx.HTTPError:
                self._finish(receipt_id, {"status": "uncertain", "message": "Check the room state before requesting this change again."})
                raise

    async def server_action(self, operation, source_event_id):
        if operation not in SERVER_COMMANDS:
            raise ValueError("Choose uptime, memory, backup, or list_backups")
        if not self.config.MATRIX_ADMIN_ACCESS_TOKEN or not self.config.MATRIX_ADMIN_ROOM_ID:
            raise ValueError("The dedicated Matrix management session needs configuration")
        if not isinstance(source_event_id, str) or not source_event_id:
            raise ValueError("Supply a source event ID")
        async with self._lock:
            receipt_id, previous = self._reserve(source_event_id, operation, "server")
            if previous:
                return {**previous, "replayed": True, "receipt_id": receipt_id}
            room = quote(self.config.MATRIX_ADMIN_ROOM_ID, safe="")
            try:
                async with self._client(self.config.MATRIX_ADMIN_ACCESS_TOKEN) as client:
                    response = await client.put(
                        f"/_matrix/client/v3/rooms/{room}/send/m.room.message/{receipt_id}",
                        json={"msgtype": "m.text", "body": "!admin " + SERVER_COMMANDS[operation]},
                    )
                    response.raise_for_status()
                    event_id = response.json()["event_id"]
                    # Only accept the server user's reply to this exact command.
                    # Other admin-room history stays outside the AI context.
                    for attempt in range(10):
                        response = await client.get(
                            f"/_matrix/client/v3/rooms/{room}/context/{quote(event_id, safe='')}",
                            params={"limit": 20},
                        )
                        response.raise_for_status()
                        for event in response.json().get("events_after", []):
                            content = event.get("content", {})
                            reply_to = content.get("m.relates_to", {}).get("m.in_reply_to", {}).get("event_id")
                            if event.get("sender") == self.config.MATRIX_ADMIN_SERVER_USER_ID and reply_to == event_id:
                                body = content.get("body", "")
                                # Drop the Matrix quoted-reply fallback.
                                if body.startswith(">") and "\n\n" in body:
                                    body = body.split("\n\n", 1)[1]
                                return self._finish(receipt_id, {
                                    "status": "response_received",
                                    "message": body[:6000],
                                    "request_event_id": event_id,
                                    "response_event_id": event.get("event_id"),
                                })
                        if attempt < 9:
                            await asyncio.sleep(1)
                return self._finish(receipt_id, {
                    "status": "pending", "message": "The server accepted the command. Its result is still pending.",
                    "request_event_id": event_id,
                })
            except httpx.HTTPError:
                self._finish(receipt_id, {"status": "uncertain", "message": "Check the admin room for this request before trying again."})
                raise

    async def backup_loop(self):
        interval = self.config.MATRIX_BACKUP_INTERVAL_SECONDS
        if interval <= 0 or not self.config.MATRIX_ADMIN_ACCESS_TOKEN:
            return
        interval = max(3600, interval)
        while True:
            try:
                bucket = int(time.time() // interval)
                result = await self.server_action("backup", f"scheduled-backup:{bucket}")
                logger.info("Matrix scheduled backup receipt: %s", result.get("receipt_id"))
            except Exception:
                logger.exception("Matrix scheduled backup needs attention")
            await asyncio.sleep(interval)
