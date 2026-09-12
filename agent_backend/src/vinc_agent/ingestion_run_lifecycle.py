from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID


class IngestionRunLifecycleError(RuntimeError):
    """Fail-closed error for incompatible ingestion-run state transitions."""


def _require_uuid(run_id: str) -> None:
    try:
        UUID(run_id)
    except (ValueError, AttributeError) as exc:
        raise ValueError("run_id must be a UUID") from exc


class IngestionRunLifecycle:
    """Persist only the pre-publication validation state owned by ingestion.

    This adapter closes the STARTED -> VALIDATED/PASS or STARTED -> FAILED/FAIL
    lifecycle needed before R20. It never writes PUBLISHED and therefore cannot
    make a source revision visible to retrieval.
    """

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect

    def mark_validated(self, run_id: str) -> None:
        _require_uuid(run_id)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(_MARK_VALIDATED, {"run_id": run_id})
                if cursor.fetchone() is None:
                    cursor.execute(_READ_RUN_STATE, {"run_id": run_id})
                    if cursor.fetchone() != ("VALIDATED", "PASS", None):
                        raise IngestionRunLifecycleError(
                            "ingestion run cannot transition idempotently to VALIDATED/PASS"
                        )
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    def mark_failed(self, run_id: str) -> None:
        _require_uuid(run_id)
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(_MARK_FAILED, {"run_id": run_id})
                if cursor.fetchone() is None:
                    cursor.execute(_READ_RUN_STATE, {"run_id": run_id})
                    existing = cursor.fetchone()
                    if (
                        existing is None
                        or existing[0] != "FAILED"
                        or existing[1] != "FAIL"
                        or existing[2] is None
                    ):
                        raise IngestionRunLifecycleError(
                            "ingestion run cannot transition idempotently to FAILED/FAIL"
                        )
            connection.commit()
        except Exception:
            connection.rollback()
            raise


_MARK_VALIDATED = """
UPDATE ingestion_runs
SET status = 'VALIDATED',
    validation_gate = 'PASS'
WHERE run_id = %(run_id)s
  AND status = 'STARTED'
  AND validation_gate IS NULL
  AND finished_at IS NULL
RETURNING run_id
""".strip()

_MARK_FAILED = """
UPDATE ingestion_runs
SET status = 'FAILED',
    validation_gate = 'FAIL',
    finished_at = COALESCE(finished_at, now())
WHERE run_id = %(run_id)s
  AND status = 'STARTED'
  AND validation_gate IS NULL
RETURNING run_id
""".strip()

_READ_RUN_STATE = """
SELECT status, validation_gate, finished_at
FROM ingestion_runs
WHERE run_id = %(run_id)s
""".strip()
