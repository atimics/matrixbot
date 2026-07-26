"""Authentication helpers for the local management API."""

import base64
import hmac
from typing import Mapping, Optional

from chatbot.config import settings

MIN_ADMIN_TOKEN_LENGTH = 32


def configured_admin_token() -> Optional[str]:
    token = settings.ADMIN_API_TOKEN
    if token and len(token.encode("utf-8")) >= MIN_ADMIN_TOKEN_LENGTH:
        return token
    return None


def supplied_admin_token(headers: Mapping[str, str]) -> Optional[str]:
    authorization = headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        candidate = authorization[7:]
        return candidate or None
    direct_token = headers.get("x-admin-token")
    if direct_token:
        return direct_token

    for protocol in headers.get("sec-websocket-protocol", "").split(","):
        protocol = protocol.strip()
        if not protocol.startswith("auth."):
            continue
        encoded = protocol[5:]
        try:
            padding = "=" * (-len(encoded) % 4)
            return base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return None
    return None


def is_admin_authorized(headers: Mapping[str, str]) -> bool:
    expected = configured_admin_token()
    supplied = supplied_admin_token(headers)
    if expected is None or supplied is None:
        return False
    return hmac.compare_digest(
        supplied.encode("utf-8"),
        expected.encode("utf-8"),
    )


def allowed_origins() -> list[str]:
    return [
        origin.strip()
        for origin in settings.ADMIN_API_ALLOWED_ORIGINS.split(",")
        if origin.strip()
    ]
