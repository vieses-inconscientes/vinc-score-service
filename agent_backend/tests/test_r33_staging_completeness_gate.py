from __future__ import annotations

from pathlib import Path


def _migration_text() -> str:
    path = Path(__file__).parents[1] / "sql" / "004_r33_staging_completeness_gate.sql"
    return path.read_text(encoding="utf-8")


def test_completeness_gate_is_versioned_and_read_only():
    text = _migration_text()
    assert "CREATE OR REPLACE FUNCTION assert_staging_complete" in text
    assert "RETURNS void" in text
    assert "LANGUAGE plpgsql" in text
    assert "STABLE" in text
    assert "INSERT INTO " not in text
    assert "UPDATE " not in text
    assert "DELETE FROM " not in text
    assert "promote_staging_sections" not in text
    assert "promote_staging_chunks" not in text
    assert "promote_staging_embeddings" not in text


def test_completeness_gate_binds_run_revision_asset_and_canonical_identity():
    text = _migration_text()
    assert "FROM source_revisions sr" in text
    assert "JOIN source_assets sa ON sa.asset_key = sr.asset_key" in text
    assert "sr.source_revision_id = p_source_revision_id" in text
    assert "sr.run_id = p_run_id" in text
    assert "c.asset_key <> v_asset_key" in text
    assert "c.canonical_id <> v_canonical_id" in text
    assert "chunk section binding is broken" in text


def test_completeness_gate_requires_complete_chunk_contract_and_canonical_url_provenance():
    text = _migration_text()
    required_tokens = (
        "c.section_id IS NULL",
        "c.source_type IS NULL",
        "c.source_title IS NULL",
        "c.chunk_text_sha256 IS NULL",
        "c.content_hash IS NULL OR c.content_hash <> c.chunk_text_sha256",
        "c.token_count IS NULL",
        "c.language IS NULL",
        "c.content_type IS NULL",
        "c.access_scope IS NULL",
        "c.sensitivity IS NULL",
        "c.instruction_authority IS NULL",
        "c.domain_authority IS NULL",
        "c.source_locator IS NULL",
        "c.retrieval_enabled IS NULL",
    )
    for token in required_tokens:
        assert token in text

    assert "FROM canonical_urls u" in text
    assert "u.url_key = c.url_key" in text
    assert "u.url_order = c.canonical_url_order" in text
    assert "u.canonical_url = c.canonical_url" in text
    assert "canonical URL provenance mismatch" in text


def test_completeness_gate_enforces_one_based_contiguous_ordinals_per_section():
    text = _migration_text()
    assert "GROUP BY c.section_id" in text
    assert "min(c.chunk_ordinal) AS min_ordinal" in text
    assert "max(c.chunk_ordinal) AS max_ordinal" in text
    assert "count(DISTINCT c.chunk_ordinal) AS distinct_count" in text
    assert "ordinal_check.min_ordinal <> 1" in text
    assert "ordinal_check.max_ordinal <> ordinal_check.row_count" in text
    assert "chunk ordinals are not contiguous and one-based" in text


def test_embeddings_are_optional_but_exact_when_present():
    text = _migration_text()
    assert "IF v_embedding_count > 0 THEN" in text
    assert "embedding references a chunk outside the candidate" in text
    assert "count(DISTINCT (e.embedding_model, e.dimensions))" in text
    assert "multiple embedding model/dimension sets" in text
    assert "count(DISTINCT e.chunk_id)" in text
    assert "embedding coverage is incomplete" in text


def test_atomic_publisher_invokes_completeness_gate_before_visibility_change():
    publisher = (
        Path(__file__).parents[1] / "src" / "vinc_agent" / "publisher.py"
    ).read_text(encoding="utf-8")
    gate = publisher.index("SELECT assert_staging_complete")
    first_visibility_change = publisher.index("DELETE FROM chunk_embeddings")
    assert gate < first_visibility_change
