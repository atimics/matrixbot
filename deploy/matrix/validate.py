#!/usr/bin/env python3
"""Validate the low-cost Matrix pilot files without network access."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = ROOT.parents[1]

EXPECTED_SERVICES: dict[str, dict[str, Any]] = {
    "continuwuity": {
        "app": "ratichat-matrix",
        "port": 8008,
        "memory": "1gb",
        "mount": ("matrix_data", "/data"),
        "image": (
            "ghcr.io/continuwuity/continuwuity:v26.8.1@"
            "sha256:fdf3cd0ffec66dbbce3c7e58999739355dd0c630b068bb02929a19719448d585"
        ),
    },
    "pocket-id": {
        "app": "ratichat-id",
        "port": 1411,
        "memory": "512mb",
        "mount": ("pocket_data", "/app/data"),
        "image": (
            "ghcr.io/pocket-id/pocket-id:v2.14.0@"
            "sha256:01540977dcf4c7b41b1159f34d68e4632f2658d62790e460ca65a42722b13c4a"
        ),
    },
    "element-web": {
        "app": "ratichat-chat",
        "port": 8080,
        "memory": "256mb",
        "mount": None,
        "image": (
            "ghcr.io/element-hq/element-web:v1.12.26@"
            "sha256:a9be04cef41ed94cba0dcaeca5a81f89826d4f8be3d57ba5a6fa988f34eda703"
        ),
    },
}

SECRET_NAMES = {
    "ENCRYPTION_KEY",
    "CONTINUWUITY_OAUTH__OIDC__CLIENT_ID",
    "CONTINUWUITY_OAUTH__OIDC__CLIENT_SECRET",
}


def load_toml(path: Path) -> dict[str, Any]:
    with path.open("rb") as source:
        return tomllib.load(source)


def check(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def validate_service(name: str, expected: dict[str, Any], errors: list[str]) -> None:
    directory = ROOT / name
    fly = load_toml(directory / "fly.toml")
    dockerfile = (directory / "Dockerfile").read_text(encoding="utf-8")

    check(fly.get("app") == expected["app"], f"{name}: unexpected app name", errors)
    check(fly.get("primary_region") == "sjc", f"{name}: region must be sjc", errors)

    deploy = fly.get("deploy", {})
    check(deploy.get("strategy") == "rolling", f"{name}: deploys must be rolling", errors)
    check(deploy.get("max_unavailable") == 1, f"{name}: unexpected rollout size", errors)

    service = fly.get("http_service", {})
    check(
        service.get("internal_port") == expected["port"],
        f"{name}: unexpected internal port",
        errors,
    )
    check(service.get("force_https") is True, f"{name}: HTTPS must be forced", errors)
    check(
        service.get("auto_stop_machines") == "off",
        f"{name}: pilot service must stay active",
        errors,
    )
    check(
        service.get("min_machines_running") == 1,
        f"{name}: pilot must keep one machine running",
        errors,
    )
    check(bool(service.get("checks")), f"{name}: health check is missing", errors)

    vm = fly.get("vm", [])
    check(len(vm) == 1, f"{name}: expected one VM definition", errors)
    if vm:
        check(vm[0].get("size") == "shared-cpu-1x", f"{name}: unexpected CPU size", errors)
        check(vm[0].get("memory") == expected["memory"], f"{name}: unexpected memory", errors)

    restart = fly.get("restart", [])
    check(
        len(restart) == 1 and restart[0].get("policy") == "always",
        f"{name}: restart policy must be always",
        errors,
    )

    mounts = fly.get("mounts", [])
    if expected["mount"] is None:
        check(not mounts, f"{name}: stateless service has a mount", errors)
    else:
        source, destination = expected["mount"]
        check(len(mounts) == 1, f"{name}: expected one volume mount", errors)
        if mounts:
            check(mounts[0].get("source") == source, f"{name}: unexpected volume name", errors)
            check(
                mounts[0].get("destination") == destination,
                f"{name}: unexpected volume path",
                errors,
            )

    from_lines = [line.strip() for line in dockerfile.splitlines() if line.startswith("FROM ")]
    check(from_lines == [f"FROM {expected['image']}"], f"{name}: image pin changed", errors)
    check(
        bool(re.search(r":v[^@\s]+@sha256:[0-9a-f]{64}$", from_lines[0])) if from_lines else False,
        f"{name}: image needs a version tag and digest",
        errors,
    )

    env = fly.get("env", {})
    for secret_name in SECRET_NAMES:
        check(secret_name not in env, f"{name}: {secret_name} belongs in Fly secrets", errors)


def validate_public_config(errors: list[str]) -> None:
    element = json.loads((ROOT / "element-web/config.json").read_text(encoding="utf-8"))
    check(element.get("brand") == "RatiChat", "Element brand must be RatiChat", errors)
    check(element.get("default_server_name") == "rati.chat", "Element server name changed", errors)
    check(element.get("disable_custom_urls") is True, "Element server picker must stay locked", errors)
    homeserver = element.get("default_server_config", {}).get("m.homeserver", {})
    check(
        homeserver.get("base_url") == "https://matrix.rati.chat",
        "Element homeserver URL changed",
        errors,
    )

    element_root = ROOT / "element-web"
    client = json.loads(
        (element_root / "well-known/matrix/client").read_text(encoding="utf-8")
    )
    server = json.loads(
        (element_root / "well-known/matrix/server").read_text(encoding="utf-8")
    )
    check(
        client.get("m.homeserver", {}).get("base_url") == "https://matrix.rati.chat",
        "client discovery URL changed",
        errors,
    )
    check(server.get("m.server") == "matrix.rati.chat:443", "server discovery URL changed", errors)

    dockerfile = (element_root / "Dockerfile").read_text(encoding="utf-8")
    check(
        "COPY well-known /app/.well-known" in dockerfile,
        "Element image must include Matrix discovery files",
        errors,
    )
    check(
        "COPY default.conf.template /etc/nginx/templates/default.conf.template" in dockerfile,
        "Element image must install the discovery server configuration",
        errors,
    )

    nginx = (element_root / "default.conf.template").read_text(encoding="utf-8")
    check(
        "server_name rati.chat chat.rati.chat;" in nginx,
        "Element must serve the identity and chat hostnames",
        errors,
    )
    client_location = nginx.split("location = /.well-known/matrix/client {", 1)
    check(len(client_location) == 2, "client discovery route is missing", errors)
    if len(client_location) == 2:
        client_block = client_location[1].split("}", 1)[0]
        check(
            "default_type application/json;" in client_block,
            "client discovery must use application/json",
            errors,
        )
        check(
            'add_header Access-Control-Allow-Origin "*" always;' in client_block,
            "client discovery must allow browser CORS",
            errors,
        )

    server_location = nginx.split("location = /.well-known/matrix/server {", 1)
    check(len(server_location) == 2, "server discovery route is missing", errors)
    if len(server_location) == 2:
        server_block = server_location[1].split("}", 1)[0]
        check(
            "default_type application/json;" in server_block,
            "server discovery must use application/json",
            errors,
        )


def validate_identity_settings(errors: list[str]) -> None:
    matrix = load_toml(ROOT / "continuwuity/fly.toml").get("env", {})
    check(matrix.get("CONTINUWUITY_SERVER_NAME") == "rati.chat", "Matrix identity changed", errors)
    check(
        matrix.get("CONTINUWUITY_OAUTH__OIDC__DISCOVERY_URL") == "https://id.rati.chat",
        "Pocket ID discovery URL changed",
        errors,
    )
    check(
        matrix.get("CONTINUWUITY_DATABASE_PATH") == "/data/database",
        "Continuwuity database path changed",
        errors,
    )
    check(
        matrix.get("CONTINUWUITY_DATABASE_BACKUP_PATH") == "/data/backups",
        "Continuwuity backup path changed",
        errors,
    )
    check(
        matrix.get("CONTINUWUITY_ALLOW_REGISTRATION") == "true",
        "invited OIDC users need first-login account creation",
        errors,
    )

    pocket = load_toml(ROOT / "pocket-id/fly.toml").get("env", {})
    check(pocket.get("APP_URL") == "https://id.rati.chat", "Pocket ID public URL changed", errors)
    check(
        pocket.get("ALLOW_INSECURE_CALLBACK_URLS") == "false",
        "Pocket ID must require HTTPS callbacks",
        errors,
    )
    check(
        pocket.get("WEBAUTHN_USER_VERIFICATION") == "required",
        "Pocket ID must require passkey user verification",
        errors,
    )


def validate_workflow_safety(errors: list[str]) -> None:
    legacy = (REPOSITORY_ROOT / ".github/workflows/deploy.yml").read_text(encoding="utf-8")
    check("workflow_dispatch:" in legacy, "legacy Mac mini deploy must be manual", errors)
    check("\n  push:" not in legacy, "legacy Mac mini deploy still runs on push", errors)

    checks = (REPOSITORY_ROOT / ".github/workflows/matrix-pilot-infra.yml").read_text(
        encoding="utf-8"
    )
    check("fly deploy" not in checks, "Matrix validation workflow must not deploy", errors)
    check("FLY_API_TOKEN" not in checks, "Matrix validation workflow must not use Fly secrets", errors)


def main() -> int:
    errors: list[str] = []
    for name, expected in EXPECTED_SERVICES.items():
        validate_service(name, expected, errors)
    validate_public_config(errors)
    validate_identity_settings(errors)
    validate_workflow_safety(errors)

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("Matrix pilot configuration is valid.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
