from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest

from vinc_agent.persistence import (
    EmbeddingRecord,
    EnrichedStagingBundle,
    PostgresStagingIndexer,
    StagingChunkRecord,
    StagingSectionRecord,
)


class FakeSession:
    def __init__(self, *, fail_on: str | None = None) -> None:
        self.events: list[tuple[str, dict[str, object] | None]] = []
        self.fail_on = fail_on

    def begin(self):
        self.events.append(("begin", None))

    def commit(self):
        self.events.append(("commit", None))

    def rollback(self):
        self.events.append(("rollback", None))

    def execute(self, statement, params):
        self.events.append((statement, params))
        if self.fail_on and self.fail_on in statement:
            raise RuntimeError("simulated write failure")


def section(section_id: str = "SEC_001", ordinal: int = 1) -> StagingSectionRecord:
    return StagingSectionRecord(
        section_id=section_id,
        source_revision_id="SRV_001",
        asset_key="AST_004_019",
        normalized_section_locator=f"main/section[{ordinal}]",
        section_ordinal=ordinal,
        source_section_locator=f"#section-{ordinal}",
        heading_path=("H1", f"H2 {ordinal}"),
    )


def chunk(
    chunk_id: str = "CHK_001",
    section_id: str = "SEC_001",
    ordinal: int = 1,
    text: str = "Texto canônico autorizado.",
) -> StagingChunkRecord:
    return StagingChunkRecord(
        chunk_id=chunk_id,
        section_id=section_id,
        source_revision_id="SRV_001",
        asset_key="AST_004_019",
        canonical_id="VINC-CAN-004",
        url_key="URL_019",
        canonical_url_order=19,
        canonical_url="https://viesesinconscientes.org/termo-verbete/vies-implicito/",
        source_type="HTML",
        source_title="Viés Implícito",
        h1="Viés Implícito",
        heading_path=("Viés Implícito", "Conceito"),
        source_section_locator="#conceito",
        chunk_ordinal=ordinal,
        chunk_text=text,
        chunk_text_sha256=sha256(text.encode("utf-8")).hexdigest(),
        token_count=8,
        language="pt-BR",
        content_type="editorial",
        access_scope="PUBLICO|INTERNO",
        sensitivity="PUBLICO",
        instruction_authority="RAG_REFERENCE_ONLY",
        domain_authority="editorial_conceitual",
        references=[{"title": "Referência"}],
        source_locator={"drive_file_id": "DRIVE-019", "section_id": "conceito"},
        metadata={"manifest_id": "MCV01-004"},
        retrieval_enabled=True,
    )


def test_migration_003_is_ddl_only_and_adds_complete_staging_shape():
    migration = Path(__file__).parents[1] / "sql" / "003_r33_enriched_staging.sql"
    text = migration.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS staging_sections" in text
    for column in (
        "section_id",
        "asset_key",
        "canonical_id",
        "url_key",
        "canonical_url_order",
        "source_type",
        "source_title",
        "chunk_text_sha256",
        "token_count",
        "language",
        "content_type",
        "access_scope",
        "sensitivity",
        "instruction_authority",
        "domain_authority",
        "source_locator",
        "retrieval_enabled",
    ):
        assert f"ADD COLUMN IF NOT EXISTS {column}" in text or f"{column} text" in text

    assert "CHECK (chunk_ordinal >= 1)" in text
    assert "CREATE FUNCTION" not in text
    assert "INSERT INTO " not in text
    assert "UPDATE " not in text
    assert "DELETE FROM " not in text


def test_enriched_chunk_rejects_hash_mismatch_and_partial_url_provenance():
    good = chunk()
    assert good.chunk_ordinal == 1

    with pytest.raises(ValueError, match="does not match"):
        replace(good, chunk_text_sha256="a" * 64)

    with pytest.raises(ValueError, match="URL provenance"):
        replace(good, canonical_url=None)


def test_enriched_bundle_requires_section_binding_and_one_based_ordinals_per_section():
    with pytest.raises(ValueError, match="reference a staged section"):
        EnrichedStagingBundle(sections=(section(),), chunks=(chunk(section_id="SEC_MISSING"),))

    with pytest.raises(ValueError, match="contiguous and one-based per section"):
        EnrichedStagingBundle(
            sections=(section(),),
            chunks=(chunk("CHK_002", ordinal=2),),
        )


def test_enriched_writer_is_transactional_and_writes_sections_before_chunks():
    first = chunk()
    embedding = EmbeddingRecord(
        embedding_id="emb-1",
        chunk_id=first.chunk_id,
        model_id="fake-embedding-v0",
        dimensions=3,
        vector=(1.0, 0.0, 1.0),
    )
    bundle = EnrichedStagingBundle(
        sections=(section(),),
        chunks=(first,),
        embeddings=(embedding,),
    )
    session = FakeSession()

    PostgresStagingIndexer(session).build_enriched_staging(
        bundle,
        run_id="00000000-0000-0000-0000-000000000033",
    )

    statements = [event[0] for event in session.events if event[0] not in {"begin", "commit", "rollback"}]
    section_insert = next(i for i, statement in enumerate(statements) if "INSERT INTO staging_sections" in statement)
    chunk_insert = next(i for i, statement in enumerate(statements) if "INSERT INTO staging_chunks" in statement)
    embedding_insert = next(i for i, statement in enumerate(statements) if "INSERT INTO staging_chunk_embeddings" in statement)

    assert session.events[0][0] == "begin"
    assert session.events[-1][0] == "commit"
    assert section_insert < chunk_insert < embedding_insert
    assert not any("promote" in statement.lower() or "operational_current" in statement.lower() for statement in statements)


def test_enriched_writer_supports_structured_sources_without_embeddings():
    first = chunk()
    bundle = EnrichedStagingBundle(sections=(section(),), chunks=(first,), embeddings=())
    session = FakeSession()

    PostgresStagingIndexer(session).build_enriched_staging(
        bundle,
        run_id="00000000-0000-0000-0000-000000000034",
    )

    inserts = [event[0] for event in session.events if event[0].startswith("INSERT INTO")]
    assert any("staging_sections" in statement for statement in inserts)
    assert any("staging_chunks" in statement for statement in inserts)
    assert not any("staging_chunk_embeddings" in statement for statement in inserts)


def test_enriched_writer_rolls_back_on_partial_chunk_write():
    bundle = EnrichedStagingBundle(sections=(section(),), chunks=(chunk(),))
    session = FakeSession(fail_on="INSERT INTO staging_chunks")

    with pytest.raises(RuntimeError):
        PostgresStagingIndexer(session).build_enriched_staging(
            bundle,
            run_id="00000000-0000-0000-0000-000000000035",
        )
    assert session.events[-1][0] == "rollback"
