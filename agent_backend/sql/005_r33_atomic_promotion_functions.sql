-- R33 scoped promotion row functions.
-- Authority: R20 atomic publisher contract + R33 staging-to-operational contract
-- + 002_r33_operational_retrieval.sql + 003_r33_enriched_staging.sql
-- + 004_r33_staging_completeness_gate.sql.
--
-- These functions are read-only row projections from validated staging.
-- They do not change operational visibility by themselves. AtomicPublisher remains
-- the sole visibility-changing adapter and must call assert_staging_complete first.
-- DO NOT APPLY TO CLOUD SQL until a separate database-application decision is recorded.

CREATE OR REPLACE FUNCTION promote_staging_sections(
    p_run_id uuid,
    p_asset_key text,
    p_source_revision_id text
)
RETURNS TABLE (
    section_id text,
    source_revision_id text,
    asset_key text,
    normalized_section_locator text,
    section_ordinal integer,
    source_section_locator text,
    heading_path text[]
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        s.section_id,
        s.source_revision_id,
        s.asset_key,
        s.normalized_section_locator,
        s.section_ordinal,
        s.source_section_locator,
        s.heading_path
    FROM staging_sections s
    WHERE s.ingestion_run_id = p_run_id
      AND s.asset_key = p_asset_key
      AND s.source_revision_id = p_source_revision_id
    ORDER BY s.section_ordinal, s.section_id;
$$;

CREATE OR REPLACE FUNCTION promote_staging_chunks(
    p_run_id uuid,
    p_asset_key text,
    p_canonical_id text,
    p_source_revision_id text
)
RETURNS TABLE (
    chunk_id text,
    section_id text,
    source_revision_id text,
    asset_key text,
    canonical_id text,
    url_key text,
    canonical_url_order smallint,
    canonical_url text,
    source_type text,
    source_title text,
    h1 text,
    heading_path text[],
    source_section_locator text,
    chunk_ordinal integer,
    chunk_text text,
    chunk_text_sha256 char(64),
    token_count integer,
    language text,
    content_type text,
    access_scope text,
    sensitivity text,
    instruction_authority text,
    domain_authority text,
    "references" jsonb,
    source_locator jsonb,
    metadata jsonb,
    ingestion_run_id uuid,
    retrieval_enabled boolean
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        c.chunk_id,
        c.section_id,
        c.source_revision_id,
        c.asset_key,
        c.canonical_id,
        c.url_key,
        c.canonical_url_order,
        c.canonical_url,
        c.source_type,
        c.source_title,
        c.h1,
        c.heading_path,
        c.source_section_locator,
        c.chunk_ordinal,
        c.chunk_text,
        c.chunk_text_sha256,
        c.token_count,
        c.language,
        c.content_type,
        c.access_scope,
        c.sensitivity,
        c.instruction_authority,
        c.domain_authority,
        c."references",
        c.source_locator,
        c.metadata,
        c.ingestion_run_id,
        c.retrieval_enabled
    FROM staging_chunks c
    WHERE c.ingestion_run_id = p_run_id
      AND c.asset_key = p_asset_key
      AND c.canonical_id = p_canonical_id
      AND c.source_revision_id = p_source_revision_id
    ORDER BY c.section_id, c.chunk_ordinal, c.chunk_id;
$$;

CREATE OR REPLACE FUNCTION promote_staging_embeddings(
    p_run_id uuid,
    p_asset_key text,
    p_source_revision_id text
)
RETURNS TABLE (
    embedding_id text,
    chunk_id text,
    embedding_model text,
    dimensions integer,
    embedding_vector vector
)
LANGUAGE sql
STABLE
AS $$
    SELECT
        e.embedding_id,
        e.chunk_id,
        e.embedding_model,
        e.dimensions,
        e.embedding_vector
    FROM staging_chunk_embeddings e
    JOIN staging_chunks c
      ON c.ingestion_run_id = e.ingestion_run_id
     AND c.chunk_id = e.chunk_id
    WHERE e.ingestion_run_id = p_run_id
      AND c.asset_key = p_asset_key
      AND c.source_revision_id = p_source_revision_id
    ORDER BY e.chunk_id, e.embedding_id;
$$;

-- No INSERT/UPDATE/DELETE statements exist in this migration.
-- The publisher owns the transaction, deletion of the prior asset projection,
-- insertion order (sections -> chunks -> embeddings), revision flip, run status,
-- commit/rollback, and post-commit cache invalidation.
