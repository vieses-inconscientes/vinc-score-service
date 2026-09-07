from __future__ import annotations

import os
from collections.abc import Mapping

from flask import Flask, jsonify

from .runtime_selection import AUTHORIZED_INTERNAL_BETA_RUNTIME


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


def create_app() -> Flask:
    """Create the authenticated internal-beta Cloud Run HTTP shell.

    This adapter intentionally exposes only health/readiness endpoints. It does not
    retrieve corpus content, call the model provider, open the database, or expose a
    public Copilot query endpoint. Those integrations remain behind later readiness
    gates.
    """

    app = Flask(__name__)

    @app.get("/healthz")
    def healthz():
        runtime = AUTHORIZED_INTERNAL_BETA_RUNTIME
        return jsonify(
            {
                "status": "ok",
                "service": runtime.deployment_service,
                "region": runtime.deployment_region,
                "public_access": runtime.public_access,
                "selection_hash": runtime.selection_hash,
            }
        )

    @app.get("/readyz")
    def readyz():
        missing = _missing_runtime_config()
        runtime = AUTHORIZED_INTERNAL_BETA_RUNTIME
        status_code = 200 if not missing else 503
        return (
            jsonify(
                {
                    "status": "ready" if not missing else "not_ready",
                    "missing_config": list(missing),
                    "public_access": runtime.public_access,
                    "selection_hash": runtime.selection_hash,
                }
            ),
            status_code,
        )

    return app


app = create_app()
