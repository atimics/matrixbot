"""Owner sessions, PKCE flows, and encrypted OpenRouter credentials."""

import base64
import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from cryptography.fernet import Fernet


class OpenRouterLink:
    def __init__(self, db_path, encryption_key, public_url):
        self.db_path = str(db_path)
        self.cipher = Fernet(encryption_key.encode()) if encryption_key else None
        self.public_url = public_url.rstrip("/")

    def require_ready(self):
        parsed = urlsplit(self.public_url)
        if not self.cipher or parsed.scheme != "https" or not parsed.netloc or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise ValueError("Set the encrypted credential store and HTTPS address first.")

    @contextmanager
    def _db(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.db_path, timeout=10)
        try:
            with db:
                db.execute("CREATE TABLE IF NOT EXISTS ai_connections (name TEXT PRIMARY KEY, value BLOB NOT NULL, expires REAL NOT NULL)")
                db.execute("DELETE FROM ai_connections WHERE expires > 0 AND expires < ?", (time.time(),))
                yield db
        finally:
            db.close()

    @staticmethod
    def digest(value):
        return hashlib.sha256(value.encode()).hexdigest()

    def _put(self, name, value, lifetime):
        if not self.cipher:
            raise ValueError("Set the encrypted credential store first.")
        encrypted = self.cipher.encrypt(json.dumps(value).encode())
        with self._db() as db:
            db.execute("INSERT OR REPLACE INTO ai_connections VALUES (?, ?, ?)",
                       (name, encrypted, time.time() + lifetime if lifetime else 0))

    def _get(self, name, consume=False):
        if not self.cipher:
            return None
        with self._db() as db:
            # A write transaction makes consuming a ticket atomic across threads.
            row = db.execute("SELECT value FROM ai_connections WHERE name=?", (name,)).fetchone()
            if row and consume:
                db.execute("DELETE FROM ai_connections WHERE name=?", (name,))
            return json.loads(self.cipher.decrypt(row[0])) if row else None

    def issue_link(self):
        self.require_ready()
        ticket = secrets.token_urlsafe(32)
        self._put("ticket:" + self.digest(ticket), True, 900)
        # Fragments stay in the browser and out of HTTP access logs.
        return self.public_url + "/connect/openrouter#" + ticket

    def open_session(self, ticket):
        self.require_ready()
        if not ticket or not self._get("ticket:" + self.digest(ticket), consume=True):
            raise ValueError("Open a fresh owner link to connect OpenRouter.")
        session = secrets.token_urlsafe(32)
        self._put("session:" + self.digest(session), {"csrf": secrets.token_urlsafe(32)}, 1800)
        return session

    def session(self, session):
        return self._get("session:" + self.digest(session)) if session else None

    def start(self, session, csrf):
        self.require_ready()
        owner = self.session(session)
        if not owner or not secrets.compare_digest(owner["csrf"], csrf):
            raise ValueError("Open a fresh owner link to connect OpenRouter.")
        verifier = secrets.token_urlsafe(64)
        flow = secrets.token_urlsafe(32)
        self._put("flow:" + flow, {"session": self.digest(session), "verifier": verifier}, 600)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        return "https://openrouter.ai/auth?" + urlencode({
            "callback_url": self.public_url + "/connect/openrouter/callback/" + flow,
            "code_challenge": challenge, "code_challenge_method": "S256",
        })

    def consume_flow(self, flow, session):
        # Validate the cookie before consuming, so another browser cannot burn a flow.
        item = self._get("flow:" + flow)
        if not self.session(session) or not item or not secrets.compare_digest(item["session"], self.digest(session)):
            raise ValueError("Return to Connect OpenRouter and try again.")
        item = self._get("flow:" + flow, consume=True)
        if not item:
            raise ValueError("Return to Connect OpenRouter and try again.")
        return item["verifier"]

    def save_key(self, key):
        if not isinstance(key, str) or not key.startswith("sk-or-") or len(key) > 1024:
            raise ValueError("OpenRouter returned an invalid key. Please connect again.")
        self._put("openrouter", {"key": key}, 0)

    def api_key(self):
        value = self._get("openrouter")
        return value["key"] if value else None
