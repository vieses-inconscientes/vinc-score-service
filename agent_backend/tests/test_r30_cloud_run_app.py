from __future__ import annotations

import json
from collections.abc import Iterable

from vinc_agent.cloud_run_app import app
from vinc_agent.runtime_selection import AUTHORIZED_INTERNAL_BETA_RUNTIME


_REQUIRED_ENV = {
    "OPENAI_API_KEY": "test-openai-key",
    "VINC_POSTGRES_APP_PASSWORD": "test-db-password",
    "VINC_CLOUD_SQL_INSTANCE": "project:region:instance",
    "VINC_POSTGRES_DB": "vinc_agent",
    "VINC_POSTGRES_USER": "vinc_agent_app",
}


def _call(path: str, method: str = "GET") -> tuple[int, dict[str, object], str]:
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]]) -> object:
        captured["status"] = status
        captured["headers"] = headers
        return object()

    chunks: Iterable[bytes] = app(
        {"REQUEST_METHOD": method, "PATH_INFO": path},
        start_response,
    )
    rendered = b"".join(chunks).decode("utf-8")
    status_code = int(str(captured["status"]).split()[0])
    return status_code, json.loads(rendered), rendered


def test_healthz_exposes_only_non_secret_runtime_identity() -> None:
    status_code, payload, _ = _call("/healthz")

    assert status_code == 200
    assert payload["status"] == "ok"
    assert payload["service"] == "vinc-agent-internal-beta"
    assert payload["region"] == "southamerica-east1"
    assert payload["public_access"] is False
    assert payload["selection_hash"] == AUTHORIZED_INTERNAL_BETA_RUNTIME.selection_hash


def test_readyz_fails_closed_when_runtime_config_is_missing(monkeypatch) -> None:
    for name in _REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)

    status_code, payload, _ = _call("/readyz")

    assert status_code == 503
    assert payload["status"] == "not_ready"
    assert set(payload["missing_config"]) == set(_REQUIRED_ENV)


def test_readyz_passes_when_runtime_config_is_present_without_leaking_values(monkeypatch) -> None:
    for name, value in _REQUIRED_ENV.items():
        monkeypatch.setenv(name, value)

    status_code, payload, rendered = _call("/readyz")

    assert status_code == 200
    assert payload["status"] == "ready"
    assert payload["missing_config"] == []
    for value in _REQUIRED_ENV.values():
        assert value not in rendered


def test_no_public_query_endpoint_is_exposed() -> None:
    assert _call("/")[0] == 404
    assert _call("/query", method="POST")[0] == 404
