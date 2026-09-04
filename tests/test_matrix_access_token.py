import json
from unittest.mock import AsyncMock, Mock

import pytest
from nio import LoginResponse, WhoamiResponse

from chatbot.api_server.services.setup_manager import SetupManager
from chatbot.config import AppConfig, matrix_auth_is_configured, settings
from chatbot.integrations.matrix.observer import MatrixObserver


def _set_matrix_settings(
    monkeypatch,
    *,
    access_token="service-token",
    password=None,
    device_id="BOTDEVICE",
):
    monkeypatch.setattr(settings, "MATRIX_HOMESERVER", "https://matrix.rati.chat")
    monkeypatch.setattr(settings, "MATRIX_USER_ID", "@ratichat-bot:rati.chat")
    monkeypatch.setattr(settings, "MATRIX_ACCESS_TOKEN", access_token)
    monkeypatch.setattr(settings, "MATRIX_PASSWORD", password)
    monkeypatch.setattr(settings, "MATRIX_DEVICE_ID", device_id)


def test_matrix_auth_accepts_service_token_with_device_id():
    config = AppConfig(
        _env_file=None,
        MATRIX_HOMESERVER="https://matrix.rati.chat",
        MATRIX_USER_ID="@ratichat-bot:rati.chat",
        MATRIX_PASSWORD=None,
        MATRIX_ACCESS_TOKEN="service-token",
        MATRIX_DEVICE_ID="BOTDEVICE",
    )

    assert matrix_auth_is_configured(config) is True


def test_matrix_auth_requires_device_id_for_service_token():
    config = AppConfig(
        _env_file=None,
        MATRIX_HOMESERVER="https://matrix.rati.chat",
        MATRIX_USER_ID="@ratichat-bot:rati.chat",
        MATRIX_PASSWORD="password-fallback",
        MATRIX_ACCESS_TOKEN="service-token",
        MATRIX_DEVICE_ID=None,
    )

    assert matrix_auth_is_configured(config) is False


def test_observer_is_disabled_when_service_token_has_no_device(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    _set_matrix_settings(
        monkeypatch,
        password="password-fallback",
        device_id=None,
    )

    observer = MatrixObserver(world_state_manager=Mock())

    assert observer.enabled is False


@pytest.mark.asyncio
async def test_observer_accepts_service_token_credentials(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_matrix_settings(
        monkeypatch,
        access_token=None,
        password=None,
        device_id=None,
    )
    observer = MatrixObserver(world_state_manager=Mock())

    await observer.set_credentials(
        {
            "homeserver": "https://matrix.rati.chat",
            "user_id": "@ratichat-bot:rati.chat",
            "access_token": "service-token",
            "device_id": "BOTDEVICE",
        }
    )

    assert observer.enabled is True
    assert observer.access_token == "service-token"
    assert observer.device_id == "BOTDEVICE"


@pytest.mark.asyncio
async def test_observer_verifies_configured_token_before_password(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    _set_matrix_settings(monkeypatch, password="password-fallback")
    observer = MatrixObserver(world_state_manager=Mock())
    assert observer.enabled is True
    observer.client = Mock()
    observer.client.restore_login = Mock()
    observer.client.whoami = AsyncMock(
        return_value=WhoamiResponse("@ratichat-bot:rati.chat", "BOTDEVICE", False)
    )
    observer.client.login = AsyncMock()
    monkeypatch.setattr(observer, "_load_token", AsyncMock(return_value=False))
    save_token = AsyncMock()
    monkeypatch.setattr(observer, "_save_token", save_token)

    await observer._authenticate("RatiChat Bot")

    observer.client.restore_login.assert_called_once_with(
        "@ratichat-bot:rati.chat", "BOTDEVICE", "service-token"
    )
    observer.client.login.assert_not_awaited()
    save_token.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_observer_uses_password_after_configured_token_is_rejected(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    _set_matrix_settings(monkeypatch, password="password-fallback")
    observer = MatrixObserver(world_state_manager=Mock())
    observer.client = Mock()
    observer.client.restore_login = Mock()
    observer.client.whoami = AsyncMock(
        return_value=WhoamiResponse("@another-user:rati.chat", "OTHER", False)
    )
    observer.client.login = AsyncMock(
        return_value=LoginResponse(
            "@ratichat-bot:rati.chat", "BOTDEVICE", "password-login-token"
        )
    )
    monkeypatch.setattr(observer, "_load_token", AsyncMock(return_value=False))
    save_token = AsyncMock()
    monkeypatch.setattr(observer, "_save_token", save_token)

    await observer._authenticate("RatiChat Bot")

    observer.client.login.assert_awaited_once_with(
        password="password-fallback", device_name="RatiChat Bot"
    )
    save_token.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_observer_restores_and_verifies_saved_token(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    _set_matrix_settings(monkeypatch, access_token="saved-token")
    token_data = {
        "access_token": "saved-token",
        "user_id": "@ratichat-bot:rati.chat",
        "device_id": "SAVEDDEVICE",
        "homeserver": "https://matrix.rati.chat",
    }
    (tmp_path / "matrix_token.json").write_text(json.dumps(token_data))

    observer = MatrixObserver(world_state_manager=Mock())
    observer.client = Mock()
    observer.client.restore_login = Mock()
    observer.client.whoami = AsyncMock(
        return_value=WhoamiResponse(
            "@ratichat-bot:rati.chat", "SAVEDDEVICE", False
        )
    )

    assert await observer._load_token() is True
    observer.client.restore_login.assert_called_once_with(
        "@ratichat-bot:rati.chat", "SAVEDDEVICE", "saved-token"
    )


@pytest.mark.asyncio
async def test_configured_token_replaces_a_different_saved_token(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    _set_matrix_settings(monkeypatch, access_token="rotated-token")
    token_data = {
        "access_token": "old-token",
        "user_id": "@ratichat-bot:rati.chat",
        "device_id": "OLDDEVICE",
        "homeserver": "https://matrix.rati.chat",
    }
    (tmp_path / "matrix_token.json").write_text(json.dumps(token_data))

    observer = MatrixObserver(world_state_manager=Mock())
    observer.client = Mock()
    observer.client.restore_login = Mock()

    assert await observer._load_token() is False
    observer.client.restore_login.assert_not_called()


def test_setup_manager_accepts_service_token_environment(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    for key in (
        "OPENROUTER_API_KEY",
        "MATRIX_HOMESERVER",
        "MATRIX_USER_ID",
        "MATRIX_PASSWORD",
        "MATRIX_ACCESS_TOKEN",
        "MATRIX_DEVICE_ID",
    ):
        monkeypatch.delenv(key, raising=False)

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-production")
    monkeypatch.setenv("MATRIX_HOMESERVER", "https://matrix.rati.chat")
    monkeypatch.setenv("MATRIX_USER_ID", "@ratichat-bot:rati.chat")
    monkeypatch.setenv("MATRIX_ACCESS_TOKEN", "service-token")
    monkeypatch.setenv("MATRIX_DEVICE_ID", "BOTDEVICE")

    assert SetupManager().is_setup_required() is False
