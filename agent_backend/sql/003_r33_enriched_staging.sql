-- R33 enriched staging representation.
-- Authority: R33_STAGING_TO_OPERATIONAL_CONTRACT.md + CONTRATO_CHUNK_V0_1 + PIPELINE_INGESTAO_V0_1 P07/P08.
-- This migration is DDL-only. It does not ingest, promote, mutate operational corpus content, or expose runtime endpoints.
-- DO NOT APPLY TO CLOUD SQL until this migration + writer/tests are green and a separate database-application decision is recorded.

CREATE TABLE IF NOT EXISTS staging_sections (
    section_id text NOT NULL,
    source_revision_id text NOT NULL,
    asset_key text NOT NULL,
    normalized_section_locator text NOT NULL,
    section_ordinal integer NOT NULL CHECK (section_ordinal >= 1),
    source_section_locator text,
    heading_path text[] NOT NULL DEFAULT '{}',
    ingestion_run_id uuid NOT NULL,
    PRIMARY KEY (ingestion_run_id, section_id),
    UNIQUE (ingestion_run_id, source_revision_id, normalized_section_locator, section_ordinal)
);

CREATE INDEX IF NOT EXISTS staging_sections_run_idx
    ON staging_sections (ingestion_run_id, source_revision_id, asset_key, section_ordinal);

-- Extend the R19 skeletal staging table without deleting legacy columns.
-- New R33 writer rows populate the complete promotion-compatible contract.
ALTER TABLE staging_chunks
    ADD COLUMN IF NOT EXISTS section_id text,
    ADD COLUMN IF NOT EXISTS asset_key text,
    ADD COLUMN IF NOT EXISTS canonical_id text,
    ADD COLUMN IF NOT EXISTS url_key text,
    ADD COLUMN IF NOT EXISTS canonical_url_order smallint,
    ADD COLUMN IF NOT EXISTS canonical_url text,
    ADD COLUMN IF NOT EXISTS source_type text,
    ADD COLUMN IF NOT EXISTS source_title text,
    ADD COLUMN IF NOT EXISTS h1 text,
    ADD COLUMN IF NOT EXISTS heading_path text[] DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS source_section_locator text,
    ADD COLUMN IF NOT EXISTS chunk_text_sha256 char(64),
    ADD COLUMN IF NOT EXISTS token_count integer,
    ADD COLUMN IF NOT EXISTS language text,
    ADD COLUMN IF NOT EXISTS content_type text,
    ADD COLUMN IF NOT EXISTS access_scope text,
    ADD COLUMN IF NOT EXISTS sensitivity text,
    ADD COLUMN IF NOT EXISTS instruction_authority text,
    ADD COLUMN IF NOT EXISTS domain_authority text,
    ADD COLUMN IF NOT EXISTS "references" jsonb,
    ADD COLUMN IF NOT EXISTS source_locator jsonb,
    ADD COLUMN IF NOT EXISTS metadata jsonb,
    ADD COLUMN IF NOT EXISTS retrieval_enabled boolean DEFAULT TRUE;

-- R33 closes ordinal semantics as one-based. NOT VALID avoids treating legacy
-- pre-R33 rows as silently repaired; it is enforced for newly written rows.
ALTER TABLE staging_chunks
    DROP CONSTRAINT IF EXISTS staging_chunks_chunk_ordinal_check;

ALTER TABLE staging_chunks
    ADD CONSTRAINT staging_chunks_chunk_ordinal_one_based_check
    CHECK (chunk_ordinal >= 1) NOT VALID;

-- Structural checks are null-tolerant for pre-R33 rows. Completeness of an R33
-- candidate is intentionally reserved for assert_staging_complete in the next
-- versioned step; no missing field is inferred here.
ALTER TABLE staging_chunks
    ADD CONSTRAINT staging_chunks_url_order_check
        CHECK (canonical_url_order IS NULL OR canonical_url_order BETWEEN 1 AND 116) NOT VALID,
    ADD CONSTRAINT staging_chunks_source_type_check
        CHECK (source_type IS NULL OR source_type IN ('GOOGLE_DOC', 'HTML', 'SHEET_STRUCTURED')) NOT VALID,
    ADD CONSTRAINT staging_chunks_sha256_check
        CHECK (chunk_text_sha256 IS NULL OR chunk_text_sha256 ~ '^[0-9a-f]{64}$') NOT VALID,
    ADD CONSTRAINT staging_chunks_token_count_check
        CHECK (token_count IS NULL OR token_count > 0) NOT VALID,
    ADD CONSTRAINT staging_chunks_content_type_check
        CHECK (content_type IS NULL OR content_type IN ('institutional', 'editorial', 'technical', 'reference')) NOT VALID,
    ADD CONSTRAINT staging_chunks_instruction_authority_check
        CHECK (instruction_authority IS NULL OR instruction_authority IN ('NONE', 'RAG_REFERENCE_ONLY')) NOT VALID,
    ADD CONSTRAINT staging_chunks_url_provenance_group_check
        CHECK (
            (url_key IS NULL AND canonical_url_order IS NULL AND canonical_url IS NULL)
            OR (url_key IS NOT NULL AND canonical_url_order IS NOT NULL AND canonical_url IS NOT NULL)
        ) NOT VALID;

CREATE INDEX IF NOT EXISTS staging_chunks_section_idx
    ON staging_chunks (ingestion_run_id, section_id, chunk_ordinal);

CREATE INDEX IF NOT EXISTS staging_chunks_binding_idx
    ON staging_chunks (ingestion_run_id, source_revision_id, asset_key, canonical_id);

-- Promotion remains deliberately absent in Migration 003.
-- No assert_staging_complete/promote_* function is created here.
