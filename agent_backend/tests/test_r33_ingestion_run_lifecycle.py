from __future__ import annotations

from collections import deque

import pytest

from vinc_agent.ingestion_run_lifecycle import (
    IngestionRunLifecycle,
    IngestionRunLifecycleError,
)


class FakeCursor:
    def __init__(self, scripted_rows=None):
        self.events = []
        self._scripted_rows = deque(scripted_rows or [])
        self._current = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement, params):
        self.events.append((statement, params))
        self._current = self._scripted_rows.popleft() if self._scripted_rows else ("ok",)

    def fetchone(self):
        return self._current


class FakeConnection:
    def __init__(self, scripted_rows=None):
        self.cursor_instance = FakeCursor(scripted_rows)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


RUN_ID = "00000000-0000-0000-0000-000000000033"


def test_mark_validated_is_prepublication_only():
    connection = FakeConnection(scripted_rows=[("run",)])

    IngestionRunLifecycle(lambda: connection).mark_validated(RUN_ID)

    statement = connection.cursor_instance.events[0][0]
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert "status = 'VALIDATED'" in statement
    assert "validation_gate = 'PASS'" in statement
    assert "PUBLISHED" not in statement


def test_mark_validated_is_idempotent_only_for_exact_validated_pass_state():
    connection = FakeConnection(scripted_rows=[None, ("VALIDATED", "PASS", None)])

    IngestionRunLifecycle(lambda: connection).mark_validated(RUN_ID)

    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert len(connection.cursor_instance.events) == 2


def test_mark_validated_rejects_published_or_drifted_state():
    connection = FakeConnection(scripted_rows=[None, ("PUBLISHED", "PASS", "done")])

    with pytest.raises(IngestionRunLifecycleError, match="VALIDATED/PASS"):
        IngestionRunLifecycle(lambda: connection).mark_validated(RUN_ID)

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_mark_failed_sets_terminal_fail_without_publication():
    connection = FakeConnection(scripted_rows=[("run",)])

    IngestionRunLifecycle(lambda: connection).mark_failed(RUN_ID)

    statement = connection.cursor_instance.events[0][0]
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert "status = 'FAILED'" in statement
    assert "validation_gate = 'FAIL'" in statement
    assert "finished_at" in statement
    assert "PUBLISHED" not in statement


def test_mark_failed_is_idempotent_only_for_existing_failed_fail_state():
    connection = FakeConnection(scripted_rows=[None, ("FAILED", "FAIL", "timestamp")])

    IngestionRunLifecycle(lambda: connection).mark_failed(RUN_ID)

    assert connection.commits == 1
    assert connection.rollbacks == 0


def test_lifecycle_rejects_invalid_uuid_before_database_access():
    connection = FakeConnection()

    with pytest.raises(ValueError, match="UUID"):
        IngestionRunLifecycle(lambda: connection).mark_validated("not-a-uuid")

    assert connection.cursor_instance.events == []
    assert connection.commits == 0
    assert connection.rollbacks == 0
