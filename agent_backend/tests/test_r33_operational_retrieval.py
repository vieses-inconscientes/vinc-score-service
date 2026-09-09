from __future__ import annotations

from pathlib import Path

import pytest

from vinc_agent.postgres_read_model import PostgresReadModel
from vinc_agent.retrieval import CandidateFilter, RetrievalPolicyError


class FakeCursor:
    def __init__(self, *, rows=(), row=None) -> None:
        self.rows = tuple(rows)
        self.row = row
        self.executions: list[tuple[str, dict[str, object]]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement, params):
        self.executions.append((statement, params))

    def fetchall(self):
        return self.rows

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


class ConnectFactory:
    def __init__(self, cursor: FakeCursor) -> None:
        self.cursor = cursor
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return FakeConnection(self.cursor)


def filt(ids=frozenset({"VINC-CAN-001", "VINC-CAN-004"}), enabled=True) -> CandidateFilter:
    return CandidateFilter(
        allowed_canonical_ids=ids,
        target_corpus="CORPUS_PUBLICO",
        requester_scope="PUBLICO",
        policy_hash="policy-r33",
        retrieval_enabled=enabled,
    )


def test_lexical_search_filters_exact_allowlist_before_ranking():
    cursor = FakeCursor(
        rows=(
            (
                "CHK_001",
                "VINC-CAN-001",
                "AST_001",
                "SRV_001",
                0.75,
                "texto canônico",
                "secao-1",
            ),
        )
    )
    connect = ConnectFactory(cursor)
    model = PostgresReadModel(connect)

    hits = model.search_authorized(
        query_text="carta fundacional",
        candidate_filter=filt(),
        top_k=5,
        modes=("lexical",),
    )

    assert len(hits) == 1
    assert hits[0].canonical_id == "VINC-CAN-001"
    sql, params = cursor.executions[0]
    assert "c.canonical_id = ANY(%(allowed_ids)s)" in sql
    assert "sr.operational_current = TRUE" in sql
    assert "c.retrieval_enabled = TRUE" in sql
    assert sql.index("c.canonical_id = ANY") < sql.index("ORDER BY score DESC")
    assert params["allowed_ids"] == ["VINC-CAN-001", "VINC-CAN-004"]
    assert params["top_k"] == 5


def test_empty_allowlist_does_not_touch_postgres():
    cursor = FakeCursor()
    connect = ConnectFactory(cursor)
    model = PostgresReadModel(connect)

    assert (
        model.search_authorized(
            query_text="qualquer",
            candidate_filter=filt(frozenset()),
            top_k=5,
            modes=("lexical",),
        )
        == ()
    )
    assert connect.calls == 0


def test_non_lexical_mode_fails_closed_without_postgres_access():
    cursor = FakeCursor()
    connect = ConnectFactory(cursor)
    model = PostgresReadModel(connect)

    with pytest.raises(RetrievalPolicyError, match="only authorizes lexical"):
        model.search_authorized(
            query_text="qualquer",
            candidate_filter=filt(),
            top_k=5,
            modes=("vector",),
        )
    assert connect.calls == 0


def test_current_provenance_requires_operational_current_join():
    cursor = FakeCursor(
        row=(
            "VINC-CAN-004",
            "AST_004_019",
            "SRV_CURRENT",
            "vies-implicito-inc-01",
            "https://viesesinconscientes.org/termo-verbete/vies-implicito/",
            "a" * 64,
        )
    )
    model = PostgresReadModel(ConnectFactory(cursor))

    provenance = model.resolve_current_provenance("CHK_019")

    assert provenance is not None
    assert provenance.source_revision_id == "SRV_CURRENT"
    sql, params = cursor.executions[0]
    assert "sr.operational_current = TRUE" in sql
    assert "co.canonical_status = 'CANONICO_VIGENTE'" in sql
    assert params == {"chunk_id": "CHK_019"}


def test_missing_current_provenance_returns_none():
    cursor = FakeCursor(row=None)
    model = PostgresReadModel(ConnectFactory(cursor))
    assert model.resolve_current_provenance("CHK_OLD") is None


def test_r33_operational_migration_is_ddl_only_and_membership_safe():
    migration = Path(__file__).parents[1] / "sql" / "002_r33_operational_retrieval.sql"
    text = migration.read_text(encoding="utf-8")
    required_tables = (
        "canonical_objects",
        "corpus_memberships",
        "source_assets",
        "ingestion_runs",
        "source_revisions",
        "canonical_urls",
        "sections",
        "chunks",
        "chunk_embeddings",
    )
    for table in required_tables:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in text

    source_assets = text.split("CREATE TABLE IF NOT EXISTS source_assets", 1)[1].split(");", 1)[0]
    assert "membership_id" not in source_assets
    assert "target_corpus = 'CORPUS_PUBLICO' AND access_scope = 'PUBLICO'" in text
    assert "target_corpus = 'CORPUS_INTERNO' AND access_scope = 'INTERNO'" in text
    assert "chunk_ordinal integer NOT NULL CHECK (chunk_ordinal >= 1)" in text

    assert "CREATE FUNCTION promote_staging_chunks" not in text
    assert "CREATE FUNCTION promote_staging_embeddings" not in text
    assert "INSERT INTO " not in text
    assert "UPDATE " not in text
    assert "DELETE FROM " not in text


def test_staging_to_operational_contract_is_versioned_before_promotion_code():
    contract = Path(__file__).parents[1] / "docs" / "R33_STAGING_TO_OPERATIONAL_CONTRACT.md"
    text = contract.read_text(encoding="utf-8")
    assert "chunk_ordinal is one-based end-to-end" in text
    assert "PUBLICO ↔ CORPUS_PUBLICO" in text
    assert "INTERNO ↔ CORPUS_INTERNO" in text
    assert "publisher MUST NOT synthesize missing governance or provenance" in text
    assert "created_at" in text and "search_tsv" in text
