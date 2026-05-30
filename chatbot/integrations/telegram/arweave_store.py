"""
Arweave-backed state store for Mirquo.

Uploads conversation turns to Arweave as permanent, tagged transactions.
Retrieves history by querying Arweave GraphQL by session tag.
Falls back to local filesystem if Arweave is unreachable.
"""

import json
import logging
import time
import hashlib
from pathlib import Path
from typing import Optional

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend
import base64

logger = logging.getLogger(__name__)

ARWEAVE_GATEWAY = "https://arweave.net"
WALLET_PATH = Path("/Users/ratimics/develop/signal/arweave-wallet.json")
LOCAL_STORE = Path(__file__).resolve().parent.parent.parent.parent / "mailbox" / "sessions"


class ArweaveStore:
    """Permanent state store backed by Arweave with local fallback."""

    def __init__(self):
        self._wallet: Optional[dict] = None
        self._http = httpx.AsyncClient(timeout=30.0)
        LOCAL_STORE.mkdir(parents=True, exist_ok=True)
        self._ar_enabled = self._load_wallet()
        if self._ar_enabled:
            logger.info("ArweaveStore: wallet loaded, permanent storage enabled")
        else:
            logger.warning("ArweaveStore: no wallet found, using local storage only")

    def _load_wallet(self) -> bool:
        try:
            self._wallet = json.loads(WALLET_PATH.read_text())
            return True
        except (FileNotFoundError, json.JSONDecodeError):
            return False

    # ── public API ───────────────────────────────────────────────────────

    async def save_turn(self, chat_id: str, role: str, text: str, msg_id: str = None):
        """Save a conversation turn — Arweave primary, local fallback."""
        entry = {
            "role": role,
            "text": text,
            "timestamp": int(time.time()),
        }
        if msg_id:
            entry["message_id"] = str(msg_id)

        # Local storage (always)
        self._save_local(chat_id, entry)

        # Arweave (if available)
        if self._ar_enabled:
            try:
                data = json.dumps(entry, ensure_ascii=False).encode()
                txid = await self._upload(data, {
                    "App-Name": "mirquo",
                    "Session-ID": chat_id,
                    "Turn-Role": role,
                })
                if txid:
                    logger.debug(f"ArweaveStore: saved turn to {txid}")
            except Exception as e:
                logger.warning(f"ArweaveStore: upload failed, local only: {e}")

    async def load_history(self, chat_id: str) -> list:
        """Load conversation history — Arweave primary, local fallback."""
        if self._ar_enabled:
            try:
                history = await self._query(chat_id, limit=30)
                if history:
                    return history
            except Exception as e:
                logger.warning(f"ArweaveStore: query failed, falling back to local: {e}")

        return self._load_local(chat_id)

    # ── Arweave operations ───────────────────────────────────────────────

    async def _upload(self, data: bytes, tags: dict) -> Optional[str]:
        """Upload data to Arweave and return transaction ID."""
        if not self._wallet:
            return None

        # Build unsigned transaction
        tx = {
            "format": 2,
            "data": base64.b64encode(data).decode(),
            "tags": [{"name": k, "value": v} for k, v in tags.items()],
            "target": "",
            "quantity": "0",
            "last_tx": await self._get_last_tx(),
        }
        tx["data_size"] = str(len(data))
        tx["owner"] = self._wallet["n"]

        # Calculate reward
        price = await self._get_price(len(data))
        tx["reward"] = str(price)

        # Sign
        tx["id"] = await self._sign_tx(tx)

        # Submit
        resp = await self._http.post(f"{ARWEAVE_GATEWAY}/tx", json=tx)
        if resp.status_code in (200, 202):
            return tx["id"]
        logger.warning(f"ArweaveStore: upload failed: {resp.status_code}")
        return None

    async def _query(self, chat_id: str, limit: int = 30) -> list:
        """Query Arweave for conversation turns by session tag."""
        query = """
        query($tags: [TagFilter!]) {
          transactions(tags: $tags, first: %d, sort: HEIGHT_DESC) {
            edges {
              node {
                id
                tags { name value }
              }
            }
          }
        }
        """ % limit

        resp = await self._http.post(
            f"{ARWEAVE_GATEWAY}/graphql",
            json={
                "query": query,
                "variables": {
                    "tags": [
                        {"name": "App-Name", "values": ["mirquo"]},
                        {"name": "Session-ID", "values": [chat_id]},
                    ]
                },
            },
        )

        if resp.status_code != 200:
            return []

        result = resp.json()
        edges = result.get("data", {}).get("transactions", {}).get("edges", [])
        turns = []

        for edge in reversed(edges):  # oldest first
            txid = edge["node"]["id"]
            try:
                data_resp = await self._http.get(f"{ARWEAVE_GATEWAY}/{txid}")
                if data_resp.status_code == 200:
                    turn = data_resp.json()
                    turns.append(turn)
            except Exception:
                pass

        return turns

    async def _sign_tx(self, tx: dict) -> str:
        """Sign a transaction and return its ID."""
        # Build the signature data
        sig_data = self._deep_hash(tx)
        n = int.from_bytes(base64.urlsafe_b64decode(self._wallet["n"] + "=="), "big")
        d = int.from_bytes(base64.urlsafe_b64decode(self._wallet["d"] + "=="), "big")

        # Sign with raw RSA
        signature = pow(int.from_bytes(sig_data, "big"), d, n)
        sig_bytes = signature.to_bytes((signature.bit_length() + 7) // 8, "big")
        tx["signature"] = base64.b64encode(sig_bytes).decode()

        # Compute tx ID = base64url(sha256(signature))
        txid = base64.urlsafe_b64encode(
            hashlib.sha256(sig_bytes).digest()
        ).decode().rstrip("=")
        return txid

    def _deep_hash(self, tx: dict) -> bytes:
        """Compute the Arweave deep hash of a transaction."""
        # Simplified: concatenate and hash key fields
        fields = [
            base64.b64decode(tx.get("owner", "") + "=="),
            base64.b64decode(tx.get("target", "") + "==") if tx.get("target") else b"",
            tx.get("data", "").encode(),
            tx.get("quantity", "0").encode(),
            tx.get("reward", "0").encode(),
            tx.get("last_tx", "").encode(),
        ]
        # Arweave uses a specific deep hash algorithm. This is a simplified version.
        tag_str = json.dumps(tx.get("tags", []), sort_keys=True)
        fields.append(tag_str.encode())
        return hashlib.sha256(b"".join(fields)).digest()

    async def _get_last_tx(self) -> str:
        """Get the last transaction ID for the wallet (anchor)."""
        try:
            resp = await self._http.get(
                f"{ARWEAVE_GATEWAY}/wallet/{self._wallet['n'][:43]}/last_tx"
            )
            if resp.status_code == 200:
                return resp.text.strip()
        except Exception:
            pass
        return ""

    async def _get_price(self, data_size: int) -> int:
        """Get the current transaction price for a given data size."""
        try:
            resp = await self._http.get(f"{ARWEAVE_GATEWAY}/price/{data_size}")
            if resp.status_code == 200:
                return int(resp.text.strip())
        except Exception:
            pass
        return 0  # free on testnet

    # ── local fallback ───────────────────────────────────────────────────

    def _session_path(self, chat_id: str) -> Path:
        return LOCAL_STORE / f"{chat_id}.json"

    def _save_local(self, chat_id: str, entry: dict):
        path = self._session_path(chat_id)
        history = self._load_local(chat_id)
        history.append(entry)
        path.write_text(json.dumps(history[-50:], ensure_ascii=False, indent=2))

    def _load_local(self, chat_id: str) -> list:
        path = self._session_path(chat_id)
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return []
