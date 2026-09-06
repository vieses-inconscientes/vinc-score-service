CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS staging_chunks (
    chunk_id text NOT NULL,
    source_revision_id text NOT NULL,
    source_asset_id text NOT NULL,
    chunk_ordinal integer NOT NULL CHECK (chunk_ordinal >= 0),
    chunk_text text NOT NULL CHECK (length(btrim(chunk_text)) > 0),
    content_hash text NOT NULL,
    ingestion_run_id uuid NOT NULL,
    PRIMARY KEY (ingestion_run_id, chunk_id),
    UNIQUE (ingestion_run_id, source_revision_id, chunk_ordinal)
);

CREATE TABLE IF NOT EXISTS staging_chunk_embeddings (
    embedding_id text NOT NULL,
    chunk_id text NOT NULL,
    embedding_model text NOT NULL,
    dimensions integer NOT NULL CHECK (dimensions > 0),
    embedding_vector vector NOT NULL,
    ingestion_run_id uuid NOT NULL,
    PRIMARY KEY (ingestion_run_id, embedding_id),
    UNIQUE (ingestion_run_id, chunk_id, embedding_model, dimensions)
);

CREATE INDEX IF NOT EXISTS staging_chunks_run_idx
    ON staging_chunks (ingestion_run_id, source_revision_id, chunk_ordinal);

CREATE INDEX IF NOT EXISTS staging_embeddings_run_idx
    ON staging_chunk_embeddings (ingestion_run_id, chunk_id);

-- Intentionally no promotion trigger, active-corpus view, or vector ANN index here.
-- R19 is staging-only. Visibility changes belong exclusively to the publisher contract.
