#!/usr/bin/env bash
set -euo pipefail

export PGHOST="${PGHOST:-127.0.0.1}"
export PGPORT="${PGPORT:-5432}"
export PGUSER="${PGUSER:-postgres}"
export PGDATABASE="${PGDATABASE:-postgres}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PSQL=(psql -X --no-psqlrc -v ON_ERROR_STOP=1)
RUN_ID="00000000-0000-0000-0000-000000000033"

printf '\n== R33 SQL deployment preflight ==\n'
"${PSQL[@]}" -Atqc "SELECT 'postgres=' || current_setting('server_version');"
"${PSQL[@]}" -Atqc "SELECT 'vector_available=' || coalesce(default_version, 'NO') FROM pg_available_extensions WHERE name='vector';"

printf '\n== 1. Recreate the known live baseline (R19 staging only) ==\n'
"${PSQL[@]}" -f sql/001_r19_staging.sql
"${PSQL[@]}" -Atqc "SELECT 'baseline_public_tables=' || count(*) FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE';"

printf '\n== 2. Transactional migration rehearsal followed by ROLLBACK ==\n'
"${PSQL[@]}" <<'SQL'
BEGIN;
\i sql/002_r33_operational_retrieval.sql
\i sql/003_r33_enriched_staging.sql
\i sql/004_r33_staging_completeness_gate.sql
\i sql/005_r33_atomic_promotion_functions.sql

DO $$
BEGIN
    IF to_regclass('public.canonical_objects') IS NULL
       OR to_regclass('public.staging_sections') IS NULL
       OR to_regprocedure('public.assert_staging_complete(uuid,text)') IS NULL
       OR to_regprocedure('public.promote_staging_sections(uuid,text,text)') IS NULL
       OR to_regprocedure('public.promote_staging_chunks(uuid,text,text,text)') IS NULL
       OR to_regprocedure('public.promote_staging_embeddings(uuid,text,text)') IS NULL THEN
        RAISE EXCEPTION 'migration rehearsal did not materialize the expected R33 objects';
    END IF;
END;
$$;
ROLLBACK;

DO $$
BEGIN
    IF to_regclass('public.canonical_objects') IS NOT NULL
       OR to_regclass('public.staging_sections') IS NOT NULL
       OR to_regprocedure('public.assert_staging_complete(uuid,text)') IS NOT NULL
       OR to_regprocedure('public.promote_staging_sections(uuid,text,text)') IS NOT NULL
       OR to_regprocedure('public.promote_staging_chunks(uuid,text,text,text)') IS NOT NULL
       OR to_regprocedure('public.promote_staging_embeddings(uuid,text,text)') IS NOT NULL THEN
        RAISE EXCEPTION 'DDL rollback left R33 objects behind';
    END IF;
    IF EXISTS (
        SELECT 1
          FROM information_schema.columns
         WHERE table_schema='public'
           AND table_name='staging_chunks'
           AND column_name='section_id'
    ) THEN
        RAISE EXCEPTION 'DDL rollback left enriched staging columns behind';
    END IF;
END;
$$;
SQL

printf '\n== 3. Apply 002 -> 005 in one transaction ==\n'
"${PSQL[@]}" <<'SQL'
BEGIN;
\i sql/002_r33_operational_retrieval.sql
\i sql/003_r33_enriched_staging.sql
\i sql/004_r33_staging_completeness_gate.sql
\i sql/005_r33_atomic_promotion_functions.sql
COMMIT;
SQL

printf '\n== 4. Verify PostgreSQL/pgvector objects and generated-column compatibility ==\n'
"${PSQL[@]}" <<'SQL'
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname='vector') THEN
        RAISE EXCEPTION 'pgvector extension was not installed';
    END IF;
    IF to_regclass('public.chunks') IS NULL
       OR to_regclass('public.chunk_embeddings') IS NULL
       OR to_regclass('public.staging_sections') IS NULL THEN
        RAISE EXCEPTION 'expected operational/staging tables are missing';
    END IF;
    IF to_regprocedure('public.assert_staging_complete(uuid,text)') IS NULL
       OR to_regprocedure('public.promote_staging_sections(uuid,text,text)') IS NULL
       OR to_regprocedure('public.promote_staging_chunks(uuid,text,text,text)') IS NULL
       OR to_regprocedure('public.promote_staging_embeddings(uuid,text,text)') IS NULL THEN
        RAISE EXCEPTION 'expected R33 functions are missing';
    END IF;
END;
$$;
SQL

printf '\n== 5. Re-run 002 -> 005 to prove final-state idempotency ==\n'
"${PSQL[@]}" <<'SQL'
BEGIN;
\i sql/002_r33_operational_retrieval.sql
\i sql/003_r33_enriched_staging.sql
\i sql/004_r33_staging_completeness_gate.sql
\i sql/005_r33_atomic_promotion_functions.sql
COMMIT;
SQL

printf '\n== 6. Seed one disposable, promotion-compatible candidate ==\n'
"${PSQL[@]}" -v run_id="$RUN_ID" <<'SQL'
INSERT INTO canonical_objects
    (canonical_id, drive_file_id, canonical_status, agent_index_authorized, domain, access_scope)
VALUES
    ('VINC-CAN-PREFLIGHT', 'drive-preflight', 'CANONICO_VIGENTE', TRUE, 'editorial', 'PUBLICO');

INSERT INTO corpus_memberships
    (membership_id, canonical_id, target_corpus, access_scope, enabled)
VALUES
    ('MEM_PREFLIGHT', 'VINC-CAN-PREFLIGHT', 'CORPUS_PUBLICO', 'PUBLICO', TRUE);

INSERT INTO ingestion_runs (run_id, status, validation_gate)
VALUES (:'run_id'::uuid, 'VALIDATED', 'PASS');

INSERT INTO source_assets
    (asset_key, canonical_id, provider, provider_file_id, source_type)
VALUES
    ('asset-preflight', 'VINC-CAN-PREFLIGHT', 'gdrive', 'drive-preflight', 'HTML');

INSERT INTO source_revisions
    (source_revision_id, asset_key, run_id, material_fingerprint, provider_revision_hint, operational_current)
VALUES
    ('rev-preflight', 'asset-preflight', :'run_id'::uuid, 'fingerprint-preflight', 'rev-hint', FALSE);

INSERT INTO canonical_urls (url_key, url_order, slug, canonical_url, name)
VALUES ('url-preflight', 1, 'preflight', 'https://viesesinconscientes.org/preflight/', 'Preflight');

INSERT INTO staging_sections
    (section_id, source_revision_id, asset_key, normalized_section_locator,
     section_ordinal, source_section_locator, heading_path, ingestion_run_id)
VALUES
    ('section-preflight', 'rev-preflight', 'asset-preflight', 'section:1',
     1, 'section:1', ARRAY['Preflight'], :'run_id'::uuid);

INSERT INTO staging_chunks
    (chunk_id, source_revision_id, source_asset_id, chunk_ordinal, chunk_text, content_hash,
     ingestion_run_id, section_id, asset_key, canonical_id, url_key, canonical_url_order,
     canonical_url, source_type, source_title, h1, heading_path, source_section_locator,
     chunk_text_sha256, token_count, language, content_type, access_scope, sensitivity,
     instruction_authority, domain_authority, "references", source_locator, metadata,
     retrieval_enabled)
VALUES
    ('chunk-preflight', 'rev-preflight', 'asset-preflight', 1, 'Texto canônico de preflight.',
     repeat('0', 64), :'run_id'::uuid, 'section-preflight', 'asset-preflight',
     'VINC-CAN-PREFLIGHT', 'url-preflight', 1, 'https://viesesinconscientes.org/preflight/',
     'HTML', 'Preflight V''inC', 'Preflight', ARRAY['Preflight'], 'section:1',
     repeat('0', 64), 5, 'pt-BR', 'editorial', 'PUBLICO', 'PUBLICO', 'NONE', 'EDITORIAL',
     NULL, '{"kind":"preflight"}'::jsonb, '{"test":true}'::jsonb, TRUE);

INSERT INTO staging_chunk_embeddings
    (embedding_id, chunk_id, embedding_model, dimensions, embedding_vector, ingestion_run_id)
VALUES
    ('embedding-preflight', 'chunk-preflight', 'preflight-model', 3, '[0.1,0.2,0.3]'::vector, :'run_id'::uuid);

SELECT assert_staging_complete(:'run_id'::uuid, 'rev-preflight');
SQL

printf '\n== 7. Execute the publisher-equivalent DML inside a transaction, then ROLLBACK ==\n'
"${PSQL[@]}" -v run_id="$RUN_ID" <<'SQL'
BEGIN;
SELECT assert_staging_complete(:'run_id'::uuid, 'rev-preflight');

DELETE FROM chunk_embeddings
 WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE asset_key = 'asset-preflight');
DELETE FROM chunks WHERE asset_key = 'asset-preflight';
DELETE FROM sections WHERE asset_key = 'asset-preflight';

INSERT INTO sections
    (section_id, source_revision_id, asset_key, normalized_section_locator,
     section_ordinal, source_section_locator, heading_path)
SELECT *
  FROM promote_staging_sections(:'run_id'::uuid, 'asset-preflight', 'rev-preflight');

INSERT INTO chunks
    (chunk_id, section_id, source_revision_id, asset_key, canonical_id, url_key,
     canonical_url_order, canonical_url, source_type, source_title, h1, heading_path,
     source_section_locator, chunk_ordinal, chunk_text, chunk_text_sha256, token_count,
     language, content_type, access_scope, sensitivity, instruction_authority,
     domain_authority, "references", source_locator, metadata, ingestion_run_id,
     retrieval_enabled)
SELECT *
  FROM promote_staging_chunks(
      :'run_id'::uuid, 'asset-preflight', 'VINC-CAN-PREFLIGHT', 'rev-preflight'
  );

INSERT INTO chunk_embeddings
    (embedding_id, chunk_id, embedding_model, dimensions, embedding_vector)
SELECT *
  FROM promote_staging_embeddings(:'run_id'::uuid, 'asset-preflight', 'rev-preflight');

UPDATE source_revisions
   SET operational_current = (source_revision_id = 'rev-preflight')
 WHERE asset_key = 'asset-preflight';
UPDATE ingestion_runs SET status = 'PUBLISHED' WHERE run_id = :'run_id'::uuid;

DO $$
BEGIN
    IF (SELECT count(*) FROM sections WHERE asset_key='asset-preflight') <> 1 THEN
        RAISE EXCEPTION 'section promotion count mismatch';
    END IF;
    IF (SELECT count(*) FROM chunks WHERE asset_key='asset-preflight') <> 1 THEN
        RAISE EXCEPTION 'chunk promotion count mismatch';
    END IF;
    IF (SELECT count(*) FROM chunk_embeddings e JOIN chunks c USING (chunk_id) WHERE c.asset_key='asset-preflight') <> 1 THEN
        RAISE EXCEPTION 'embedding promotion count mismatch';
    END IF;
    IF EXISTS (SELECT 1 FROM chunks WHERE asset_key='asset-preflight' AND search_tsv IS NULL) THEN
        RAISE EXCEPTION 'generated search_tsv was not materialized';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM source_revisions WHERE source_revision_id='rev-preflight' AND operational_current) THEN
        RAISE EXCEPTION 'revision flip did not occur';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM ingestion_runs WHERE run_id='00000000-0000-0000-0000-000000000033'::uuid AND status='PUBLISHED') THEN
        RAISE EXCEPTION 'run did not reach PUBLISHED inside transaction';
    END IF;
END;
$$;

ROLLBACK;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM sections WHERE asset_key='asset-preflight')
       OR EXISTS (SELECT 1 FROM chunks WHERE asset_key='asset-preflight') THEN
        RAISE EXCEPTION 'publisher rollback left operational rows behind';
    END IF;
    IF EXISTS (SELECT 1 FROM source_revisions WHERE source_revision_id='rev-preflight' AND operational_current) THEN
        RAISE EXCEPTION 'publisher rollback left revision visible';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM ingestion_runs WHERE run_id='00000000-0000-0000-0000-000000000033'::uuid AND status='VALIDATED') THEN
        RAISE EXCEPTION 'publisher rollback did not restore ingestion run status';
    END IF;
END;
$$;
SQL

printf '\nR33 SQL DEPLOYMENT PREFLIGHT: PASS\n'
