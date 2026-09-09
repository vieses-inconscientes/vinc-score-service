from __future__ import annotations

from pathlib import Path

import pytest

from vinc_agent.publisher import AtomicPublisher, PublishRequest


ROOT = Path(__file__).resolve().parents[1]
SQL = (ROOT / "sql" / "005_r33_atomic_promotion_functions.sql").read_text(encoding="utf-8")


class FakeSession:
    def __init__(self, fail_at: str | None = None) -> None:
        self.events: list[tuple[str, dict[str, object] | None]] = []
        self.fail_at = fail_at

    def begin(self) -> None:
        self.events.append(("BEGIN", None))

    def execute(self, statement: str, params: dict[str, object]) -> None:
        self.events.append((statement, params))
        if self.fail_at and self.fail_at in statement:
            raise RuntimeError("simulated promotion failure")

    def commit(self) -> None:
        self.events.append(("COMMIT", None))

    def rollback(self) -> None:
        self.events.append(("ROLLBACK", None))


class FakeCache:
    def __init__(self) -> None:
        self.invalidated: list[str] = []

    def invalidate_corpus(self, canonical_id: str) -> None:
        self.invalidated.append(canonical_id)


def request() -> PublishRequest:
    return PublishRequest(
        run_id="00000000-0000-0000-0000-000000000033",
        canonical_id="VINC-CAN-003",
        asset_key="asset-003",
        source_revision_id="rev-003",
        validation_gate="PASS",
    )


def _statement_index(events: list[tuple[str, dict[str, object] | None]], needle: str) -> int:
    return next(index for index, (statement, _) in enumerate(events) if needle in statement)


def test_promotion_functions_are_read_only_scoped_row_projections() -> None:
    assert "CREATE OR REPLACE FUNCTION promote_staging_sections" in SQL
    assert "CREATE OR REPLACE FUNCTION promote_staging_chunks" in SQL
    assert "CREATE OR REPLACE FUNCTION promote_staging_embeddings" in SQL
    assert "p_asset_key text" in SQL
    assert "p_source_revision_id text" in SQL
    assert "p_canonical_id text" in SQL
    assert "\nINSERT INTO " not in SQL.upper()
    assert "\nUPDATE " not in SQL.upper()
    assert "\nDELETE FROM " not in SQL.upper()


def test_publisher_orders_gate_replacement_and_promotions_atomically() -> None:
    session = FakeSession()
    cache = FakeCache()
    AtomicPublisher(session, cache).publish(request())

    assert session.events[0][0] == "BEGIN"
    assert _statement_index(session.events, "assert_staging_complete") < _statement_index(
        session.events, "DELETE FROM chunk_embeddings"
    )
    assert _statement_index(session.events, "DELETE FROM chunk_embeddings") < _statement_index(
        session.events, "DELETE FROM chunks"
    )
    assert _statement_index(session.events, "DELETE FROM chunks") < _statement_index(
        session.events, "DELETE FROM sections"
    )
    assert _statement_index(session.events, "DELETE FROM sections") < _statement_index(
        session.events, "promote_staging_sections"
    )
    assert _statement_index(session.events, "promote_staging_sections") < _statement_index(
        session.events, "promote_staging_chunks"
    )
    assert _statement_index(session.events, "promote_staging_chunks") < _statement_index(
        session.events, "promote_staging_embeddings"
    )
    assert _statement_index(session.events, "promote_staging_embeddings") < _statement_index(
        session.events, "UPDATE source_revisions"
    )
    assert _statement_index(session.events, "UPDATE source_revisions") < _statement_index(
        session.events, "UPDATE ingestion_runs"
    )
    assert session.events[-1][0] == "COMMIT"
    assert cache.invalidated == ["VINC-CAN-003"]


def test_promotion_is_scoped_to_exact_run_asset_revision_and_canonical_id() -> None:
    session = FakeSession()
    AtomicPublisher(session, FakeCache()).publish(request())

    promotion_events = [
        (statement, params)
        for statement, params in session.events
        if statement.startswith("INSERT INTO") or "promote_staging_" in statement
    ]
    assert promotion_events
    for _, params in promotion_events:
        assert params is not None
        assert params["run_id"] == request().run_id
        assert params["asset_key"] == request().asset_key
        assert params["source_revision_id"] == request().source_revision_id
        assert params["canonical_id"] == request().canonical_id


def test_chunk_insert_leaves_database_derived_columns_to_postgres() -> None:
    session = FakeSession()
    AtomicPublisher(session, FakeCache()).publish(request())
    statement = next(
        statement
        for statement, _ in session.events
        if statement.startswith("INSERT INTO chunks")
    )
    assert "created_at" not in statement
    assert "search_tsv" not in statement
    assert "promote_staging_chunks" in statement


@pytest.mark.parametrize(
    "fail_at",
    ["promote_staging_sections", "promote_staging_chunks", "promote_staging_embeddings"],
)
def test_any_promotion_failure_rolls_back_and_never_invalidates_cache(fail_at: str) -> None:
    session = FakeSession(fail_at=fail_at)
    cache = FakeCache()
    with pytest.raises(RuntimeError, match="simulated promotion failure"):
        AtomicPublisher(session, cache).publish(request())
    assert session.events[-1][0] == "ROLLBACK"
    assert not any(statement == "COMMIT" for statement, _ in session.events)
    assert cache.invalidated == []
