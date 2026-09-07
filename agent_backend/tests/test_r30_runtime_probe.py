from __future__ import annotations

import json
from urllib.error import URLError

import pytest

from vinc_agent.runtime_probe import RuntimeProbeError, probe_database, probe_model_provider, run_runtime_probe


ENV = {
    "OPENAI_API_KEY": "secret-openai-key",
    "VINC_POSTGRES_APP_PASSWORD": "secret-db-password",
    "VINC_CLOUD_SQL_INSTANCE": "vinc-agent-internal-beta:southamerica-east1:vinc-agent-postgres-beta",
    "VINC_POSTGRES_DB": "vinc_agent",
    "VINC_POSTGRES_USER": "vinc_agent_app",
}


class FakeCursor:
    def __init__(self, row=("vinc_agent", "vinc_agent_app", 1)) -> None:
        self.row = row
        self.statement = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement: str) -> None:
        self.statement = statement

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, cursor: FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self._cursor


class FakeResponse:
    status = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def test_missing_runtime_config_fails_before_any_external_call() -> None:
    with pytest.raises(RuntimeProbeError, match="OPENAI_API_KEY"):
        run_runtime_probe({}, connect=lambda **_: pytest.fail("db called"), open_url=lambda *_a, **_k: pytest.fail("http called"))


def test_database_probe_uses_cloud_sql_socket_and_read_only_session() -> None:
    captured = {}
    cursor = FakeCursor()

    def connect(**kwargs):
        captured.update(kwargs)
        return FakeConnection(cursor)

    result = probe_database(ENV, connect=connect)

    assert result.database == "vinc_agent"
    assert result.user == "vinc_agent_app"
    assert captured["host"] == "/cloudsql/vinc-agent-internal-beta:southamerica-east1:vinc-agent-postgres-beta"
    assert captured["options"] == "-c default_transaction_read_only=on -c statement_timeout=5000"
    assert cursor.statement == "SELECT current_database(), current_user, 1"


def test_database_failure_does_not_leak_exception_text() -> None:
    def connect(**_kwargs):
        raise RuntimeError("password=secret-db-password")

    with pytest.raises(RuntimeProbeError) as captured:
        probe_database(ENV, connect=connect)

    assert "secret-db-password" not in str(captured.value)
    assert "RuntimeError" in str(captured.value)


def test_model_probe_calls_only_authorized_responses_api_without_tools() -> None:
    captured = {}

    def open_url(request, timeout):
        captured["url"] = request.full_url
        captured["authorization"] = request.get_header("Authorization")
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse({"id": "resp_probe", "model": "gpt-5.6-terra", "status": "completed"})

    result = probe_model_provider(ENV, open_url=open_url)

    assert result.provider == "openai"
    assert result.model == "gpt-5.6-terra"
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["payload"]["model"] == "gpt-5.6-terra"
    assert captured["payload"]["tools"] == []
    assert captured["payload"]["store"] is False
    assert captured["timeout"] == 30


def test_model_transport_failure_does_not_leak_exception_text() -> None:
    def open_url(*_args, **_kwargs):
        raise URLError("Bearer secret-openai-key")

    with pytest.raises(RuntimeProbeError) as captured:
        probe_model_provider(ENV, open_url=open_url)

    assert "secret-openai-key" not in str(captured.value)
    assert "URLError" in str(captured.value)


def test_runtime_probe_stops_before_model_when_database_fails() -> None:
    called = {"model": False}

    def connect(**_kwargs):
        raise OSError("db unavailable")

    def open_url(*_args, **_kwargs):
        called["model"] = True
        return FakeResponse({"id": "resp_probe", "model": "gpt-5.6-terra", "status": "completed"})

    with pytest.raises(RuntimeProbeError, match="database probe failed"):
        run_runtime_probe(ENV, connect=connect, open_url=open_url)

    assert called["model"] is False


def test_runtime_probe_reports_both_real_runtime_boundaries_when_green() -> None:
    def connect(**_kwargs):
        return FakeConnection(FakeCursor())

    def open_url(*_args, **_kwargs):
        return FakeResponse({"id": "resp_probe", "model": "gpt-5.6-terra-2026-09-01", "status": "completed"})

    report = run_runtime_probe(ENV, connect=connect, open_url=open_url)

    assert report.ready is True
    assert report.database.database == "vinc_agent"
    assert report.model_provider.model.startswith("gpt-5.6-terra")
    assert len(report.selection_hash) == 64
