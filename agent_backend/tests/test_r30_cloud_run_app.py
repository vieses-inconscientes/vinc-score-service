from __future__ import annotations

from vinc_agent.cloud_run_app import create_app
from vinc_agent.runtime_selection import AUTHORIZED_INTERNAL_BETA_RUNTIME


_REQUIRED_ENV = {
    "OPENAI_API_KEY": "test-openai-key",
    "VINC_POSTGRES_APP_PASSWORD": "test-db-password",
    "VINC_CLOUD_SQL_INSTANCE": "project:region:instance",
    "VINC_POSTGRES_DB": "vinc_agent",
    "VINC_POSTGRES_USER": "vinc_agent_app",
}


def test_healthz_exposes_only_non_secret_runtime_identity() -> None:
    client = create_app().test_client()

    response = client.get("/healthz")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["service"] == "vinc-agent-internal-beta"
    assert payload["region"] == "southamerica-east1"
    assert payload["public_access"] is False
    assert payload["selection_hash"] == AUTHORIZED_INTERNAL_BETA_RUNTIME.selection_hash


def test_readyz_fails_closed_when_runtime_config_is_missing(monkeypatch) -> None:
    for name in _REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)
    client = create_app().test_client()

    response = client.get("/readyz")

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["status"] == "not_ready"
    assert set(payload["missing_config"]) == set(_REQUIRED_ENV)


def test_readyz_passes_when_runtime_config_is_present_without_leaking_values(monkeypatch) -> None:
    for name, value in _REQUIRED_ENV.items():
        monkeypatch.setenv(name, value)
    client = create_app().test_client()

    response = client.get("/readyz")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ready"
    assert payload["missing_config"] == []
    rendered = response.get_data(as_text=True)
    for value in _REQUIRED_ENV.values():
        assert value not in rendered


def test_no_public_query_endpoint_is_exposed() -> None:
    client = create_app().test_client()

    assert client.get("/").status_code == 404
    assert client.post("/query", json={"query": "test"}).status_code == 404
