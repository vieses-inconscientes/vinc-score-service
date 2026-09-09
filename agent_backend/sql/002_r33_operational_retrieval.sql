-- R33 operational retrieval schema, design-only until R33 staging/promotion implementation is validated.
-- Authority: SCHEMA_POSTGRES_V0_1 + CONTRATO_CHUNK_V0_1 + R19/R20/R21 + R33 contract closure.
-- This migration is intentionally DDL-only: it does not ingest, promote, mutate, or expose corpus content.
-- Do not apply to Cloud SQL until the versioned staging/promotion implementation is complete and CI/review are green.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS canonical_objects (
    canonical_id text PRIMARY KEY,
    drive_file_id text UNIQUE,
    canonical_status text NOT NULL CHECK (canonical_status = 'CANONICO_VIGENTE'),
    agent_index_authorized boolean NOT NULL,
    domain text NOT NULL,
    access_scope text NOT NULL
);

CREATE INDEX IF NOT EXISTS canonical_objects_status_idx
    ON canonical_objects (canonical_status, agent_index_authorized);
CREATE INDEX IF NOT EXISTS canonical_objects_domain_idx
    ON canonical_objects (domain);
CREATE INDEX IF NOT EXISTS canonical_objects_access_scope_idx
    ON canonical_objects (access_scope);

CREATE TABLE IF NOT EXISTS corpus_memberships (
    membership_id text PRIMARY KEY,
    canonical_id text NOT NULL REFERENCES canonical_objects(canonical_id),
    target_corpus text NOT NULL,
    access_scope text NOT NULL,
    enabled boolean NOT NULL DEFAULT FALSE,
    CHECK (
        (target_corpus = 'CORPUS_PUBLICO' AND access_scope = 'PUBLICO')
        OR (target_corpus = 'CORPUS_INTERNO' AND access_scope = 'INTERNO')
    ),
    UNIQUE (canonical_id, target_corpus, access_scope)
);

CREATE INDEX IF NOT EXISTS corpus_memberships_filter_idx
    ON corpus_memberships (target_corpus, access_scope, enabled);

CREATE TABLE IF NOT EXISTS source_assets (
    asset_key text PRIMARY KEY,
    canonical_id text NOT NULL REFERENCES canonical_objects(canonical_id),
    provider text NOT NULL CHECK (provider = 'gdrive'),
    provider_file_id text NOT NULL,
    source_type text NOT NULL,
    UNIQUE (provider, provider_file_id)
);

CREATE INDEX IF NOT EXISTS source_assets_canonical_idx
    ON source_assets (canonical_id);
CREATE INDEX IF NOT EXISTS source_assets_type_idx
    ON source_assets (source_type);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id uuid PRIMARY KEY,
    status text NOT NULL CHECK (status IN ('STARTED', 'FAILED', 'VALIDATED', 'PUBLISHED')),
    validation_gate text,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    CHECK (status <> 'PUBLISHED' OR validation_gate = 'PASS')
);

CREATE INDEX IF NOT EXISTS ingestion_runs_status_idx
    ON ingestion_runs (status, started_at);

CREATE TABLE IF NOT EXISTS source_revisions (
    source_revision_id text PRIMARY KEY,
    asset_key text NOT NULL REFERENCES source_assets(asset_key),
    run_id uuid NOT NULL REFERENCES ingestion_runs(run_id),
    material_fingerprint text NOT NULL,
    provider_revision_hint text,
    operational_current boolean NOT NULL DEFAULT FALSE,
    UNIQUE (asset_key, material_fingerprint)
);

CREATE UNIQUE INDEX IF NOT EXISTS source_revisions_one_current_per_asset_idx
    ON source_revisions (asset_key)
    WHERE operational_current = TRUE;

CREATE INDEX IF NOT EXISTS source_revisions_asset_idx
    ON source_revisions (asset_key, material_fingerprint);

CREATE TABLE IF NOT EXISTS canonical_urls (
    url_key text PRIMARY KEY,
    url_order smallint NOT NULL CHECK (url_order BETWEEN 1 AND 116),
    slug text NOT NULL,
    canonical_url text NOT NULL UNIQUE,
    name text NOT NULL,
    UNIQUE (url_order)
);

CREATE INDEX IF NOT EXISTS canonical_urls_slug_idx
    ON canonical_urls (slug);
CREATE INDEX IF NOT EXISTS canonical_urls_name_idx
    ON canonical_urls (lower(name));

CREATE TABLE IF NOT EXISTS sections (
    section_id text PRIMARY KEY,
    source_revision_id text NOT NULL REFERENCES source_revisions(source_revision_id),
    asset_key text NOT NULL REFERENCES source_assets(asset_key),
    normalized_section_locator text NOT NULL,
    section_ordinal integer NOT NULL CHECK (section_ordinal >= 1),
    source_section_locator text,
    heading_path text[] NOT NULL DEFAULT '{}',
    UNIQUE (source_revision_id, normalized_section_locator, section_ordinal)
);

CREATE INDEX IF NOT EXISTS sections_asset_idx
    ON sections (asset_key);
CREATE INDEX IF NOT EXISTS sections_source_locator_idx
    ON sections (source_section_locator);
CREATE INDEX IF NOT EXISTS sections_heading_path_idx
    ON sections USING gin (heading_path);

CREATE TABLE IF NOT EXISTS chunks (
    chunk_id text PRIMARY KEY,
    section_id text NOT NULL REFERENCES sections(section_id),
    source_revision_id text NOT NULL REFERENCES source_revisions(source_revision_id),
    asset_key text NOT NULL REFERENCES source_assets(asset_key),
    canonical_id text NOT NULL REFERENCES canonical_objects(canonical_id),
    url_key text REFERENCES canonical_urls(url_key),
    canonical_url_order smallint CHECK (
        canonical_url_order IS NULL OR canonical_url_order BETWEEN 1 AND 116
    ),
    canonical_url text,
    source_type text NOT NULL CHECK (
        source_type IN ('GOOGLE_DOC', 'HTML', 'SHEET_STRUCTURED')
    ),
    source_title text NOT NULL CHECK (length(btrim(source_title)) > 0),
    h1 text,
    heading_path text[] NOT NULL DEFAULT '{}',
    source_section_locator text,
    chunk_ordinal integer NOT NULL CHECK (chunk_ordinal >= 1),
    chunk_text text NOT NULL CHECK (length(btrim(chunk_text)) > 0),
    chunk_text_sha256 char(64) NOT NULL CHECK (chunk_text_sha256 ~ '^[0-9a-f]{64}$'),
    token_count integer NOT NULL CHECK (token_count > 0),
    language text NOT NULL,
    content_type text NOT NULL CHECK (
        content_type IN ('institutional', 'editorial', 'technical', 'reference')
    ),
    access_scope text NOT NULL,
    sensitivity text NOT NULL,
    instruction_authority text NOT NULL CHECK (
        instruction_authority IN ('NONE', 'RAG_REFERENCE_ONLY')
    ),
    domain_authority text NOT NULL,
    "references" jsonb,
    source_locator jsonb NOT NULL,
    metadata jsonb,
    ingestion_run_id uuid NOT NULL REFERENCES ingestion_runs(run_id),
    created_at timestamptz NOT NULL DEFAULT now(),
    retrieval_enabled boolean NOT NULL DEFAULT TRUE,
    search_tsv tsvector NOT NULL,
    UNIQUE (section_id, chunk_ordinal)
);

-- PostgreSQL 18 rejects the previous GENERATED expression because the composed
-- heading-path expression is not immutable. The canonical contract requires
-- search_tsv to be database-derived, not specifically a generated column.
-- A BEFORE trigger preserves that boundary: publishers never supply search_tsv.
CREATE OR REPLACE FUNCTION vinc_set_chunks_search_tsv()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.search_tsv := to_tsvector(
        'portuguese'::regconfig,
        coalesce(NEW.source_title, '') || ' ' ||
        coalesce(NEW.h1, '') || ' ' ||
        coalesce(array_to_string(NEW.heading_path, ' '), '') || ' ' ||
        NEW.chunk_text
    );
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS chunks_search_tsv_before_write ON chunks;
CREATE TRIGGER chunks_search_tsv_before_write
BEFORE INSERT OR UPDATE
OF source_title, h1, heading_path, chunk_text
ON chunks
FOR EACH ROW
EXECUTE FUNCTION vinc_set_chunks_search_tsv();

CREATE INDEX IF NOT EXISTS chunks_canonical_idx
    ON chunks (canonical_id);
CREATE INDEX IF NOT EXISTS chunks_url_key_idx
    ON chunks (url_key);
CREATE INDEX IF NOT EXISTS chunks_access_scope_idx
    ON chunks (access_scope);
CREATE INDEX IF NOT EXISTS chunks_sensitivity_idx
    ON chunks (sensitivity);
CREATE INDEX IF NOT EXISTS chunks_text_hash_idx
    ON chunks (chunk_text_sha256);
CREATE INDEX IF NOT EXISTS chunks_search_tsv_idx
    ON chunks USING gin (search_tsv);
CREATE INDEX IF NOT EXISTS chunks_retrieval_enabled_idx
    ON chunks (canonical_id, asset_key)
    WHERE retrieval_enabled = TRUE;

CREATE TABLE IF NOT EXISTS chunk_embeddings (
    embedding_id text PRIMARY KEY,
    chunk_id text NOT NULL REFERENCES chunks(chunk_id) ON DELETE CASCADE,
    embedding_model text NOT NULL,
    dimensions integer NOT NULL CHECK (dimensions > 0),
    embedding_vector vector NOT NULL,
    UNIQUE (chunk_id, embedding_model, dimensions)
);

CREATE INDEX IF NOT EXISTS chunk_embeddings_chunk_idx
    ON chunk_embeddings (chunk_id);

-- Contract closure (R33):
-- * valid membership pairs are PUBLICO/CORPUS_PUBLICO and INTERNO/CORPUS_INTERNO only;
-- * source_assets is not bound to one membership row; memberships join through canonical_id;
-- * chunk_ordinal is one-based end-to-end;
-- * P07 staging must carry every source field needed by the operational chunk contract;
--   created_at/search_tsv remain database-derived.
--
-- Promotion functions remain intentionally absent from this DDL-only migration.
-- They are authorized for a subsequent versioned implementation only after the enriched staging
-- representation and assert_staging_complete are implemented and tested.
