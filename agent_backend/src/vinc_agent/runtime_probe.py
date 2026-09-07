from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .runtime_selection import AUTHORIZED_INTERNAL_BETA_RUNTIME


_OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
_REQUIRED_RUNTIME_ENV = (
    "OPENAI_API_KEY",
    "VINC_POSTGRES_APP_PASSWORD",
    "VINC_CLOUD_SQL_INSTANCE",
    "VINC_POSTGRES_DB",
    "VINC_POSTGRES_USER",
)


class RuntimeProbeError(RuntimeError):
    """Fail-closed R30 probe error that never includes secret values."""


@dataclass(frozen=True, slots=True)
class DatabaseProbeResult:
    database: str
    user: str


@dataclass(frozen=True, slots=True)
class ModelProbeResult:
    provider: str
    model: str
    status: str


@dataclass(frozen=True, slots=True)
class RuntimeProbeReport:
    database: DatabaseProbeResult
    model_provider: ModelProbeResult
    selection_hash: str
    ready: bool = True


def _require_runtime_env(environ: Mapping[str, str]) -> None:
    missing = tuple(sorted(name for name in _REQUIRED_RUNTIME_ENV if not environ.get(name, "").strip()))
    if missing:
        raise RuntimeProbeError("missing runtime config: " + ",".join(missing))


def _default_db_connect(**kwargs: object) -> Any:
    import psycopg

    return psycopg.connect(**kwargs)


def probe_database(
    environ: Mapping[str, str] | None = None,
    *,
    connect: Callable[..., Any] | None = None,
) -> DatabaseProbeResult:
    source = os.environ if environ is None else environ
    _require_runtime_env(source)
    connector = _default_db_connect if connect is None else connect
    expected_database = source["VINC_POSTGRES_DB"].strip()
    expected_user = source["VINC_POSTGRES_USER"].strip()

    try:
        connection = connector(
            host=f"/cloudsql/{source['VINC_CLOUD_SQL_INSTANCE'].strip()}",
            dbname=expected_database,
            user=expected_user,
            password=source["VINC_POSTGRES_APP_PASSWORD"],
            connect_timeout=10,
            options="-c default_transaction_read_only=on -c statement_timeout=5000",
        )
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database(), current_user, 1")
                row = cursor.fetchone()
    except RuntimeProbeError:
        raise
    except Exception as exc:
        raise RuntimeProbeError(f"database probe failed ({type(exc).__name__})") from None

    if not row or len(row) < 3 or row[2] != 1:
        raise RuntimeProbeError("database probe returned an invalid identity row")
    database, user = str(row[0]), str(row[1])
    if database != expected_database or user != expected_user:
        raise RuntimeProbeError("database probe identity mismatch")
    return DatabaseProbeResult(database=database, user=user)


def probe_model_provider(
    environ: Mapping[str, str] | None = None,
    *,
    open_url: Callable[..., Any] | None = None,
) -> ModelProbeResult:
    source = os.environ if environ is None else environ
    _require_runtime_env(source)
    runtime = AUTHORIZED_INTERNAL_BETA_RUNTIME
    if runtime.model_provider != "openai" or runtime.model_api != "responses":
        raise RuntimeProbeError("unauthorized model provider selection")
    if runtime.model_external_tools_allowed:
        raise RuntimeProbeError("model external tools must remain disabled")

    payload = {
        "model": runtime.model_id,
        "input": "Reply with exactly: VINC_RUNTIME_PROBE_OK",
        "max_output_tokens": 64,
        "store": False,
        "tools": [],
    }
    request = Request(
        _OPENAI_RESPONSES_URL,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {source['OPENAI_API_KEY']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    opener = urlopen if open_url is None else open_url

    try:
        with opener(request, timeout=30) as response:
            status_code = int(getattr(response, "status", 200))
            raw_body = response.read()
    except HTTPError as exc:
        raise RuntimeProbeError(f"model provider probe failed (HTTP {exc.code})") from None
    except (URLError, TimeoutError) as exc:
        raise RuntimeProbeError(f"model provider probe failed ({type(exc).__name__})") from None
    except Exception as exc:
        raise RuntimeProbeError(f"model provider probe failed ({type(exc).__name__})") from None

    if status_code < 200 or status_code >= 300:
        raise RuntimeProbeError(f"model provider probe failed (HTTP {status_code})")
    try:
        response_payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeProbeError("model provider returned an invalid response") from None

    response_id = str(response_payload.get("id", ""))
    returned_model = str(response_payload.get("model", ""))
    response_status = str(response_payload.get("status", ""))
    expected_model = runtime.model_id
    model_matches = returned_model == expected_model or returned_model.startswith(expected_model + "-")
    if not response_id or not model_matches or response_status != "completed":
        raise RuntimeProbeError("model provider response failed identity/status validation")

    return ModelProbeResult(provider=runtime.model_provider, model=returned_model, status=response_status)


def run_runtime_probe(
    environ: Mapping[str, str] | None = None,
    *,
    connect: Callable[..., Any] | None = None,
    open_url: Callable[..., Any] | None = None,
) -> RuntimeProbeReport:
    source = os.environ if environ is None else environ
    _require_runtime_env(source)
    database = probe_database(source, connect=connect)
    model_provider = probe_model_provider(source, open_url=open_url)
    return RuntimeProbeReport(
        database=database,
        model_provider=model_provider,
        selection_hash=AUTHORIZED_INTERNAL_BETA_RUNTIME.selection_hash,
    )


def _safe_report_payload(report: RuntimeProbeReport) -> dict[str, object]:
    return {
        "ready": report.ready,
        "selection_hash": report.selection_hash,
        "database": {
            "status": "ok",
            "database": report.database.database,
            "user": report.database.user,
        },
        "model_provider": {
            "status": report.model_provider.status,
            "provider": report.model_provider.provider,
            "model": report.model_provider.model,
        },
    }


def main() -> int:
    try:
        report = run_runtime_probe()
    except RuntimeProbeError as exc:
        print(
            json.dumps(
                {
                    "ready": False,
                    "error": str(exc),
                    "selection_hash": AUTHORIZED_INTERNAL_BETA_RUNTIME.selection_hash,
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            file=sys.stderr,
        )
        return 1
    print(json.dumps(_safe_report_payload(report), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
