from __future__ import annotations

import json
import os
from collections.abc import Mapping
from http import HTTPStatus
from typing import Callable, Iterable

from .runtime_selection import AUTHORIZED_INTERNAL_BETA_RUNTIME


StartResponse = Callable[[str, list[tuple[str, str]]], object]
_REQUIRED_RUNTIME_ENV = (
    "OPENAI_API_KEY",
    "VINC_POSTGRES_APP_PASSWORD",
    "VINC_CLOUD_SQL_INSTANCE",
    "VINC_POSTGRES_DB",
    "VINC_POSTGRES_USER",
)


def _missing_runtime_config(environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    source = os.environ if environ is None else environ
    return tuple(sorted(name for name in _REQUIRED_RUNTIME_ENV if not source.get(name, "").strip()))


def _json_response(
    start_response: StartResponse,
    status: HTTPStatus,
    payload: dict[str, object],
) -> Iterable[bytes]:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    start_response(
        f"{status.value} {status.phrase}",
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
        ],
    )
    return [body]


def app(environ: Mapping[str, str], start_response: StartResponse) -> Iterable[bytes]:
    """Authenticated internal-beta Cloud Run WSGI shell.

    Only health/readiness endpoints exist here. The adapter does not retrieve corpus
    content, call the model provider, open the database, or expose a Copilot query
    endpoint. Those integrations remain behind later readiness gates.
    """

    method = environ.get("REQUEST_METHOD", "GET").upper()
    path = environ.get("PATH_INFO", "/")
    runtime = AUTHORIZED_INTERNAL_BETA_RUNTIME

    if method == "GET" and path == "/healthz":
        return _json_response(
            start_response,
            HTTPStatus.OK,
            {
                "status": "ok",
                "service": runtime.deployment_service,
                "region": runtime.deployment_region,
                "public_access": runtime.public_access,
                "selection_hash": runtime.selection_hash,
            },
        )

    if method == "GET" and path == "/readyz":
        missing = _missing_runtime_config()
        return _json_response(
            start_response,
            HTTPStatus.OK if not missing else HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "status": "ready" if not missing else "not_ready",
                "missing_config": list(missing),
                "public_access": runtime.public_access,
                "selection_hash": runtime.selection_hash,
            },
        )

    return _json_response(start_response, HTTPStatus.NOT_FOUND, {"status": "not_found"})
