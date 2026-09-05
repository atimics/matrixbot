import base64
import hashlib
import json
import re
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient

from chatbot.api_server.main import ChatbotAPIServer
from chatbot.api_server.routers.openrouter import COOKIE, create_router
from chatbot.config import settings
from chatbot.core.openrouter_link import OpenRouterLink


@pytest.fixture
def connection(tmp_path):
    return OpenRouterLink(tmp_path / "bot.db", Fernet.generate_key().decode(), "https://bot.example")


def open_owner(connection):
    return connection.open_session(urlsplit(connection.issue_link()).fragment)


def test_link_is_single_use_and_key_survives_restart_encrypted(connection):
    ticket = urlsplit(connection.issue_link()).fragment
    assert connection.session(connection.open_session(ticket))
    with pytest.raises(ValueError):
        connection.open_session(ticket)
    key = "sk-or-test-private-key"
    connection.save_key(key)
    assert key.encode() not in open(connection.db_path, "rb").read()
    restarted = OpenRouterLink(connection.db_path, connection.cipher._signing_key and base64.urlsafe_b64encode(connection.cipher._signing_key + connection.cipher._encryption_key).decode(), connection.public_url)
    assert restarted.api_key() == key


def test_expired_ticket_and_session_are_rejected(connection):
    ticket = urlsplit(connection.issue_link()).fragment
    session = open_owner(connection)
    with patch("chatbot.core.openrouter_link.time.time", return_value=10**12):
        with pytest.raises(ValueError):
            connection.open_session(ticket)
        assert connection.session(session) is None


def test_pkce_bound_to_browser_single_use_and_correct_challenge(connection):
    session = open_owner(connection)
    url = connection.start(session, connection.session(session)["csrf"])
    query = parse_qs(urlsplit(url).query)
    flow = query["callback_url"][0].rsplit("/", 1)[1]
    with pytest.raises(ValueError):
        connection.consume_flow(flow, open_owner(connection))
    verifier = connection.consume_flow(flow, session)
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == [base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()]
    with pytest.raises(ValueError):
        connection.consume_flow(flow, session)
    with pytest.raises(ValueError):
        connection.start(session, "forged csrf")


def test_concurrent_ticket_consumption_has_one_winner(connection):
    ticket = urlsplit(connection.issue_link()).fragment
    def attempt(_):
        try:
            return bool(connection.open_session(ticket))
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(attempt, range(4))) == 1


def test_connection_routes_require_owner_link_and_use_secure_cookie(connection, monkeypatch):
    monkeypatch.setattr(settings, "ADMIN_API_TOKEN", "admin-" + "x" * 40)
    orchestrator = SimpleNamespace(openrouter_link=connection, ai_engine=SimpleNamespace(api_key=None))
    server = ChatbotAPIServer.__new__(ChatbotAPIServer)
    server.app = FastAPI()
    server._setup_middleware()
    server.app.include_router(create_router(orchestrator))
    client = TestClient(server.app, base_url=connection.public_url)
    assert client.post("/api/ai/openrouter/link").status_code == 401
    response = client.post("/api/ai/openrouter/link", headers={"Authorization": "Bearer " + settings.ADMIN_API_TOKEN})
    ticket = urlsplit(response.json()["url"]).fragment
    assert client.post("/connect/openrouter/session", json={"ticket": ticket}).status_code == 403
    response = client.post("/connect/openrouter/session", json={"ticket": ticket}, headers={"Origin": connection.public_url})
    assert response.status_code == 200
    assert all(value in response.headers["set-cookie"] for value in ["Secure", "HttpOnly", "SameSite=lax"])
    response = client.get("/connect/openrouter")
    csrf = re.search('name="csrf" value="([^"]+)"', response.text)[1]
    assert client.post("/connect/openrouter/start", data={"csrf": "wrong"}).status_code == 401
    response = client.post("/connect/openrouter/start", data={"csrf": csrf}, follow_redirects=False)
    assert response.status_code == 303
    query = parse_qs(urlsplit(response.headers["location"]).query)
    callback = query["callback_url"][0]
    post = AsyncMock(return_value=httpx.Response(200, json={"key": "sk-or-test-linked"}, request=httpx.Request("POST", "https://openrouter.ai/api/v1/auth/keys")))
    with patch("chatbot.api_server.routers.openrouter.httpx.AsyncClient") as mock:
        mock.return_value.__aenter__.return_value.post = post
        response = client.get(callback + "?code=single-use-test-code", follow_redirects=False)
    assert response.status_code == 303
    assert orchestrator.ai_engine.api_key == "sk-or-test-linked"
    assert post.call_args.kwargs["json"]["code_challenge_method"] == "S256"
    response = client.get("/connect/openrouter")
    assert "OpenRouter is connected" in response.text
    assert "sk-or-test-linked" not in response.text
    assert client.get(callback + "?code=replay").status_code == 400


def test_exchange_failure_preserves_existing_key(connection):
    connection.save_key("sk-or-existing")
    session = open_owner(connection)
    callback = parse_qs(urlsplit(connection.start(session, connection.session(session)["csrf"])).query)["callback_url"][0]
    app = FastAPI()
    app.include_router(create_router(SimpleNamespace(openrouter_link=connection, ai_engine=SimpleNamespace(api_key="sk-or-existing"))))
    client = TestClient(app, base_url=connection.public_url)
    client.cookies.set(COOKIE, session)
    with patch("chatbot.api_server.routers.openrouter.httpx.AsyncClient") as mock:
        mock.return_value.__aenter__.return_value.post = AsyncMock(side_effect=httpx.ConnectTimeout("private code details"))
        result = client.get(callback + "?code=private-code")
    assert result.status_code == 400
    assert "private" not in result.text
    assert connection.api_key() == "sk-or-existing"
