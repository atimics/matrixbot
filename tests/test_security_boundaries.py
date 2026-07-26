"""Regression tests for externally reachable security boundaries."""

import json
import base64
import asyncio
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from chatbot.api_server.auth import is_admin_authorized
from chatbot.config import settings
from chatbot.core.integration_manager import IntegrationManager
from chatbot.integrations.telegram.operator_queue import OperatorQueueBridge
from chatbot.integrations.telegram.observer import (
    MessageRateLimiter,
    TelegramObserver,
    parse_id_allowlist,
)


class TelegramBoundaryTests(unittest.TestCase):
    def test_allowlist_is_exact_and_fails_closed(self):
        self.assertEqual(parse_id_allowlist("123, -456,123"), {"123", "-456"})
        self.assertNotIn("12", parse_id_allowlist("123"))

        previous = (
            settings.TELEGRAM_BOT_TOKEN,
            settings.TELEGRAM_ALLOWED_CHAT_IDS,
            settings.TELEGRAM_ALLOWED_SENDER_IDS,
        )
        try:
            settings.TELEGRAM_BOT_TOKEN = "token"
            settings.TELEGRAM_ALLOWED_CHAT_IDS = "123"
            settings.TELEGRAM_ALLOWED_SENDER_IDS = ""
            self.assertFalse(TelegramObserver().enabled)
        finally:
            (
                settings.TELEGRAM_BOT_TOKEN,
                settings.TELEGRAM_ALLOWED_CHAT_IDS,
                settings.TELEGRAM_ALLOWED_SENDER_IDS,
            ) = previous

    def test_rate_limit_uses_a_sliding_window(self):
        limiter = MessageRateLimiter(2)
        self.assertTrue(limiter.allow("sender", now=10))
        self.assertTrue(limiter.allow("sender", now=20))
        self.assertFalse(limiter.allow("sender", now=30))
        self.assertTrue(limiter.allow("sender", now=71))

    def test_only_exactly_authorized_messages_reach_the_operator_queue(self):
        previous = (
            settings.TELEGRAM_BOT_TOKEN,
            settings.TELEGRAM_ALLOWED_CHAT_IDS,
            settings.TELEGRAM_ALLOWED_SENDER_IDS,
        )
        try:
            settings.TELEGRAM_BOT_TOKEN = "token"
            settings.TELEGRAM_ALLOWED_CHAT_IDS = "123"
            settings.TELEGRAM_ALLOWED_SENDER_IDS = "42"
            observer = TelegramObserver()
            observer.operator_queue_bridge = AsyncMock()

            asyncio.run(
                observer._handle_message(
                    {
                        "message_id": 7,
                        "chat": {"id": 123},
                        "from": {"id": 42},
                        "text": "review this",
                    }
                )
            )
            observer.operator_queue_bridge.handle_message.assert_awaited_once_with(
                "123", "7", "42", "review this"
            )

            observer.operator_queue_bridge.reset_mock()
            asyncio.run(
                observer._handle_message(
                    {
                        "message_id": 8,
                        "chat": {"id": 1234},
                        "from": {"id": 42},
                        "text": "do not queue this",
                    }
                )
            )
            observer.operator_queue_bridge.handle_message.assert_not_awaited()
        finally:
            (
                settings.TELEGRAM_BOT_TOKEN,
                settings.TELEGRAM_ALLOWED_CHAT_IDS,
                settings.TELEGRAM_ALLOWED_SENDER_IDS,
            ) = previous


class OperatorQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_queue_is_local_bounded_and_owner_only(self):
        old_path = settings.TELEGRAM_OPERATOR_QUEUE_PATH
        old_limit = settings.TELEGRAM_OPERATOR_QUEUE_MAX_BYTES
        try:
            with tempfile.TemporaryDirectory() as directory:
                queue_path = Path(directory) / "operator.jsonl"
                settings.TELEGRAM_OPERATOR_QUEUE_PATH = str(queue_path)
                settings.TELEGRAM_OPERATOR_QUEUE_MAX_BYTES = 1024
                observer = AsyncMock()
                observer.send_message.return_value = {"success": True}
                bridge = OperatorQueueBridge(observer)

                await bridge.start()
                await bridge.handle_message("123", "7", "42", "review this")
                await bridge.handle_message("123", "7", "42", "review this")
                bridge.max_queue_bytes = queue_path.stat().st_size
                await bridge.handle_message("123", "8", "42", "another")
                await bridge.stop()

                entries = queue_path.read_text().splitlines()
                self.assertEqual(len(entries), 1)
                entry = json.loads(entries[0])
                self.assertEqual(entry["sender_id"], "42")
                self.assertEqual(entry["text"], "review this")
                self.assertEqual(stat.S_IMODE(queue_path.stat().st_mode), 0o600)
                observer.send_message.assert_awaited_with(
                    "123",
                    "Operator queue is full. Try again later.",
                    "8",
                )
        finally:
            settings.TELEGRAM_OPERATOR_QUEUE_PATH = old_path
            settings.TELEGRAM_OPERATOR_QUEUE_MAX_BYTES = old_limit


class AdminAuthenticationTests(unittest.TestCase):
    def test_admin_token_is_required_compared_exactly_and_minimum_length(self):
        old_token = settings.ADMIN_API_TOKEN
        try:
            settings.ADMIN_API_TOKEN = None
            self.assertFalse(is_admin_authorized({}))
            settings.ADMIN_API_TOKEN = "short"
            self.assertFalse(is_admin_authorized({"x-admin-token": "short"}))

            token = "a" * 32
            settings.ADMIN_API_TOKEN = token
            self.assertFalse(is_admin_authorized({"authorization": f"Bearer {token}x"}))
            self.assertTrue(is_admin_authorized({"authorization": f"Bearer {token}"}))
            self.assertTrue(is_admin_authorized({"x-admin-token": token}))
            encoded = base64.urlsafe_b64encode(token.encode()).decode().rstrip("=")
            self.assertTrue(
                is_admin_authorized(
                    {
                        "sec-websocket-protocol": (
                            f"ratichat-admin, auth.{encoded}"
                        )
                    }
                )
            )
        finally:
            settings.ADMIN_API_TOKEN = old_token


class IntegrationDeletionTests(unittest.IsolatedAsyncioTestCase):
    def test_production_requires_a_stable_credential_key(self):
        old_environment = settings.CHATBOT_ENV
        try:
            settings.CHATBOT_ENV = "production"
            with self.assertRaisesRegex(
                ValueError, "INTEGRATION_CREDENTIAL_KEY"
            ):
                IntegrationManager(":memory:")
        finally:
            settings.CHATBOT_ENV = old_environment

    async def test_remove_integration_deletes_credentials_and_configuration(self):
        manager = IntegrationManager(":memory:")
        await manager.initialize()
        try:
            now = 1.0
            await manager._persistent_db.execute(
                """
                INSERT INTO integrations
                    (id, user_id, integration_type, display_name, is_active,
                     config, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("integration-1", None, "dummy", "Dummy", True, "{}", now, now),
            )
            await manager._persistent_db.execute(
                """
                INSERT INTO credentials
                    (id, integration_id, credential_key,
                     credential_value_encrypted, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    "credential-1",
                    "integration-1",
                    "token",
                    manager.cipher.encrypt(b"not-a-real-secret"),
                    now,
                ),
            )
            await manager._persistent_db.commit()

            self.assertTrue(await manager.remove_integration("integration-1"))
            self.assertFalse(await manager.remove_integration("integration-1"))
            cursor = await manager._persistent_db.execute(
                "SELECT COUNT(*) FROM credentials WHERE integration_id = ?",
                ("integration-1",),
            )
            self.assertEqual((await cursor.fetchone())[0], 0)
        finally:
            await manager.cleanup()


if __name__ == "__main__":
    unittest.main()
