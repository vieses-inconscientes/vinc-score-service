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

expect_denied() {
    local label="$1"
    local sql="$2"
    local output
    local rc

    set +e
    output=$("${PSQL[@]}" -c "$sql" 2>&1)
    rc=$?
    set -e

    if [[ $rc -eq 0 ]]; then
        printf 'EXPECTED DENIAL FAILED: %s\n%s\n' "$label" "$output" >&2
        exit 1
    fi
    if ! grep -qi 'permission denied' <<<"$output"; then
        printf 'EXPECTED PERMISSION DENIAL, GOT DIFFERENT ERROR: %s\n%s\n' "$label" "$output" >&2
        exit 1
    fi
    printf 'DENY PASS: %s\n' "$label"
}

printf '\n== R33 ACL preflight ==\n'

printf '\n== 1. Rehearse 006 role/ACL migration and prove transactional rollback ==\n'
"${PSQL[@]}" <<'SQL'
BEGIN;
\i sql/006_r33_least_privilege.sql
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='vinc_agent_ingestion_runtime')
       OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='vinc_agent_publisher_runtime')
       OR NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='vinc_agent_retrieval_runtime') THEN
        RAISE EXCEPTION '006 rehearsal did not create all target capability roles';
    END IF;
END;
$$;
ROLLBACK;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_roles
         WHERE rolname IN (
            'vinc_agent_ingestion_runtime',
            'vinc_agent_publisher_runtime',
            'vinc_agent_retrieval_runtime'
         )
    ) THEN
        RAISE EXCEPTION '006 rollback left capability roles behind';
    END IF;
END;
$$;
SQL

printf '\n== 2. Apply 006, then re-run to prove final-state idempotency ==\n'
"${PSQL[@]}" -f sql/006_r33_least_privilege.sql
"${PSQL[@]}" -f sql/006_r33_least_privilege.sql

printf '\n== 3. Verify exact role attributes, grants and function hardening ==\n'
"${PSQL[@]}" <<'SQL'
DO $$
DECLARE
    role_name text;
BEGIN
    FOREACH role_name IN ARRAY ARRAY[
        'vinc_agent_ingestion_runtime',
        'vinc_agent_publisher_runtime',
        'vinc_agent_retrieval_runtime'
    ]
    LOOP
        IF NOT EXISTS (
            SELECT 1
              FROM pg_roles
             WHERE rolname = role_name
               AND rolcanlogin = FALSE
               AND rolsuper = FALSE
               AND rolcreatedb = FALSE
               AND rolcreaterole = FALSE
               AND rolreplication = FALSE
               AND rolbypassrls = FALSE
        ) THEN
            RAISE EXCEPTION 'unsafe or missing attributes for role %', role_name;
        END IF;
        IF has_schema_privilege(role_name, 'public', 'CREATE') THEN
            RAISE EXCEPTION 'runtime role % can CREATE in public schema', role_name;
        END IF;
        IF NOT has_schema_privilege(role_name, 'public', 'USAGE') THEN
            RAISE EXCEPTION 'runtime role % lacks public schema USAGE', role_name;
        END IF;
    END LOOP;

    -- Ingestion: projector/lifecycle/staging only.
    IF NOT has_table_privilege('vinc_agent_ingestion_runtime', 'canonical_objects', 'SELECT')
       OR NOT has_table_privilege('vinc_agent_ingestion_runtime', 'canonical_objects', 'INSERT')
       OR NOT has_column_privilege('vinc_agent_ingestion_runtime', 'canonical_objects', 'agent_index_authorized', 'UPDATE')
       OR has_column_privilege('vinc_agent_ingestion_runtime', 'canonical_objects', 'canonical_id', 'UPDATE')
       OR NOT has_table_privilege('vinc_agent_ingestion_runtime', 'ingestion_runs', 'INSERT')
       OR NOT has_column_privilege('vinc_agent_ingestion_runtime', 'ingestion_runs', 'validation_gate', 'UPDATE')
       OR NOT has_table_privilege('vinc_agent_ingestion_runtime', 'source_revisions', 'INSERT')
       OR has_column_privilege('vinc_agent_ingestion_runtime', 'source_revisions', 'operational_current', 'UPDATE')
       OR NOT has_table_privilege('vinc_agent_ingestion_runtime', 'staging_sections', 'INSERT')
       OR NOT has_table_privilege('vinc_agent_ingestion_runtime', 'staging_sections', 'DELETE')
       OR has_table_privilege('vinc_agent_ingestion_runtime', 'staging_sections', 'UPDATE')
       OR has_table_privilege('vinc_agent_ingestion_runtime', 'chunks', 'SELECT') THEN
        RAISE EXCEPTION 'ingestion least-privilege matrix mismatch';
    END IF;

    -- Publisher: exact gate/staging reads + operational replace + narrow state flips.
    IF NOT has_table_privilege('vinc_agent_publisher_runtime', 'staging_chunks', 'SELECT')
       OR has_table_privilege('vinc_agent_publisher_runtime', 'staging_chunks', 'INSERT')
       OR NOT has_table_privilege('vinc_agent_publisher_runtime', 'chunks', 'SELECT')
       OR NOT has_table_privilege('vinc_agent_publisher_runtime', 'chunks', 'INSERT')
       OR NOT has_table_privilege('vinc_agent_publisher_runtime', 'chunks', 'DELETE')
       OR has_table_privilege('vinc_agent_publisher_runtime', 'chunks', 'UPDATE')
       OR NOT has_column_privilege('vinc_agent_publisher_runtime', 'source_revisions', 'operational_current', 'UPDATE')
       OR has_column_privilege('vinc_agent_publisher_runtime', 'source_revisions', 'material_fingerprint', 'UPDATE')
       OR NOT has_column_privilege('vinc_agent_publisher_runtime', 'ingestion_runs', 'status', 'UPDATE')
       OR has_column_privilege('vinc_agent_publisher_runtime', 'ingestion_runs', 'validation_gate', 'UPDATE')
       OR has_table_privilege('vinc_agent_publisher_runtime', 'canonical_objects', 'UPDATE') THEN
        RAISE EXCEPTION 'publisher least-privilege matrix mismatch';
    END IF;

    -- Retrieval: exact R21 read relations and nothing writable/staging.
    IF NOT has_table_privilege('vinc_agent_retrieval_runtime', 'chunks', 'SELECT')
       OR NOT has_table_privilege('vinc_agent_retrieval_runtime', 'source_assets', 'SELECT')
       OR NOT has_table_privilege('vinc_agent_retrieval_runtime', 'source_revisions', 'SELECT')
       OR NOT has_table_privilege('vinc_agent_retrieval_runtime', 'canonical_objects', 'SELECT')
       OR has_table_privilege('vinc_agent_retrieval_runtime', 'chunks', 'INSERT')
       OR has_table_privilege('vinc_agent_retrieval_runtime', 'chunks', 'UPDATE')
       OR has_table_privilege('vinc_agent_retrieval_runtime', 'chunks', 'DELETE')
       OR has_table_privilege('vinc_agent_retrieval_runtime', 'staging_chunks', 'SELECT') THEN
        RAISE EXCEPTION 'retrieval least-privilege matrix mismatch';
    END IF;

    -- Gate/promotion execution belongs only to publisher. Trigger helper has no direct runtime grant.
    IF has_function_privilege('vinc_agent_ingestion_runtime', 'assert_staging_complete(uuid,text)', 'EXECUTE')
       OR NOT has_function_privilege('vinc_agent_publisher_runtime', 'assert_staging_complete(uuid,text)', 'EXECUTE')
       OR NOT has_function_privilege('vinc_agent_publisher_runtime', 'promote_staging_sections(uuid,text,text)', 'EXECUTE')
       OR NOT has_function_privilege('vinc_agent_publisher_runtime', 'promote_staging_chunks(uuid,text,text,text)', 'EXECUTE')
       OR NOT has_function_privilege('vinc_agent_publisher_runtime', 'promote_staging_embeddings(uuid,text,text)', 'EXECUTE')
       OR has_function_privilege('vinc_agent_retrieval_runtime', 'assert_staging_complete(uuid,text)', 'EXECUTE')
       OR has_function_privilege('vinc_agent_publisher_runtime', 'vinc_set_chunks_search_tsv()', 'EXECUTE') THEN
        RAISE EXCEPTION 'runtime function ACL mismatch';
    END IF;

    IF EXISTS (
        SELECT 1
          FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
          CROSS JOIN LATERAL aclexplode(COALESCE(p.proacl, acldefault('f', p.proowner))) a
         WHERE n.nspname='public'
           AND p.proname IN (
                'assert_staging_complete',
                'promote_staging_sections',
                'promote_staging_chunks',
                'promote_staging_embeddings',
                'vinc_set_chunks_search_tsv'
           )
           AND a.grantee = 0
           AND a.privilege_type = 'EXECUTE'
    ) THEN
        RAISE EXCEPTION 'PUBLIC EXECUTE remains on an R33 function';
    END IF;
END;
$$;
SQL

printf '\n== 4. Prove ingestion can prepare but cannot publish/read operational corpus ==\n'
"${PSQL[@]}" <<'SQL'
BEGIN;
SET LOCAL ROLE vinc_agent_ingestion_runtime;

INSERT INTO canonical_objects
    (canonical_id, drive_file_id, canonical_status, agent_index_authorized, domain, access_scope)
VALUES
    ('VINC-CAN-ACL-INGEST', 'drive-acl-ingest', 'CANONICO_VIGENTE', TRUE, 'technical', 'INTERNO')
ON CONFLICT (canonical_id) DO UPDATE SET
    drive_file_id=EXCLUDED.drive_file_id,
    canonical_status=EXCLUDED.canonical_status,
    agent_index_authorized=EXCLUDED.agent_index_authorized,
    domain=EXCLUDED.domain,
    access_scope=EXCLUDED.access_scope
RETURNING canonical_id;

INSERT INTO corpus_memberships
    (membership_id, canonical_id, target_corpus, access_scope, enabled)
VALUES
    ('MEM-ACL-INGEST', 'VINC-CAN-ACL-INGEST', 'CORPUS_INTERNO', 'INTERNO', TRUE)
ON CONFLICT (membership_id) DO UPDATE SET enabled=EXCLUDED.enabled
WHERE corpus_memberships.canonical_id=EXCLUDED.canonical_id
  AND corpus_memberships.target_corpus=EXCLUDED.target_corpus
  AND corpus_memberships.access_scope=EXCLUDED.access_scope
RETURNING membership_id;

INSERT INTO source_assets
    (asset_key, canonical_id, provider, provider_file_id, source_type)
VALUES
    ('asset-acl-ingest', 'VINC-CAN-ACL-INGEST', 'gdrive', 'drive-acl-ingest', 'HTML')
ON CONFLICT (asset_key) DO UPDATE SET source_type=EXCLUDED.source_type
WHERE source_assets.canonical_id=EXCLUDED.canonical_id
  AND source_assets.provider=EXCLUDED.provider
  AND source_assets.provider_file_id=EXCLUDED.provider_file_id
RETURNING asset_key;

INSERT INTO canonical_urls (url_key, url_order, slug, canonical_url, name)
VALUES ('url-acl-ingest', 116, 'acl-ingest', 'https://viesesinconscientes.org/acl-ingest/', 'ACL Ingest')
ON CONFLICT (url_key) DO UPDATE SET
    slug=EXCLUDED.slug,
    canonical_url=EXCLUDED.canonical_url,
    name=EXCLUDED.name
WHERE canonical_urls.url_order=EXCLUDED.url_order
RETURNING url_key;

INSERT INTO ingestion_runs (run_id, status, validation_gate)
VALUES ('00000000-0000-0000-0000-000000000034'::uuid, 'STARTED', NULL);

INSERT INTO source_revisions
    (source_revision_id, asset_key, run_id, material_fingerprint, provider_revision_hint, operational_current)
VALUES
    ('rev-acl-ingest', 'asset-acl-ingest', '00000000-0000-0000-0000-000000000034'::uuid,
     'fingerprint-acl-ingest', 'hint-acl-ingest', FALSE);

UPDATE ingestion_runs
   SET status='VALIDATED', validation_gate='PASS'
 WHERE run_id='00000000-0000-0000-0000-000000000034'::uuid;

INSERT INTO staging_sections
    (section_id, source_revision_id, asset_key, normalized_section_locator,
     section_ordinal, source_section_locator, heading_path, ingestion_run_id)
VALUES
    ('section-acl-ingest', 'rev-acl-ingest', 'asset-acl-ingest', 'section:1',
     1, 'section:1', ARRAY['ACL'], '00000000-0000-0000-0000-000000000034'::uuid);
DELETE FROM staging_sections
 WHERE ingestion_run_id='00000000-0000-0000-0000-000000000034'::uuid;

INSERT INTO staging_chunks
    (chunk_id, source_revision_id, source_asset_id, chunk_ordinal, chunk_text, content_hash, ingestion_run_id)
VALUES
    ('chunk-acl-ingest', 'rev-acl-ingest', 'asset-acl-ingest', 1, 'acl staging', repeat('a',64),
     '00000000-0000-0000-0000-000000000034'::uuid);
DELETE FROM staging_chunks
 WHERE ingestion_run_id='00000000-0000-0000-0000-000000000034'::uuid;

INSERT INTO staging_chunk_embeddings
    (embedding_id, chunk_id, embedding_model, dimensions, embedding_vector, ingestion_run_id)
VALUES
    ('embedding-acl-ingest', 'chunk-acl-ingest', 'acl-model', 3, '[0.1,0.2,0.3]'::vector,
     '00000000-0000-0000-0000-000000000034'::uuid);
DELETE FROM staging_chunk_embeddings
 WHERE ingestion_run_id='00000000-0000-0000-0000-000000000034'::uuid;

ROLLBACK;
SQL

expect_denied \
    'ingestion cannot read operational chunks' \
    "SET ROLE vinc_agent_ingestion_runtime; SELECT count(*) FROM chunks;"
expect_denied \
    'ingestion cannot flip source revision visibility' \
    "SET ROLE vinc_agent_ingestion_runtime; UPDATE source_revisions SET operational_current=TRUE WHERE FALSE;"
expect_denied \
    'ingestion cannot execute publisher gate' \
    "SET ROLE vinc_agent_ingestion_runtime; SELECT assert_staging_complete('${RUN_ID}'::uuid, 'rev-preflight');"

printf '\n== 5. Prove publisher boundary and trigger behavior, then ROLLBACK ==\n'
"${PSQL[@]}" -v run_id="$RUN_ID" <<'SQL'
BEGIN;
SET LOCAL ROLE vinc_agent_publisher_runtime;
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
    IF NOT EXISTS (
        SELECT 1 FROM chunks
         WHERE asset_key='asset-preflight'
           AND search_tsv IS NOT NULL
    ) THEN
        RAISE EXCEPTION 'publisher insert did not fire search_tsv trigger after direct EXECUTE revoke';
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM source_revisions
         WHERE source_revision_id='rev-preflight'
           AND operational_current
    ) THEN
        RAISE EXCEPTION 'publisher did not flip operational_current';
    END IF;
END;
$$;
ROLLBACK;
SQL

expect_denied \
    'publisher cannot mutate canonical governance projection' \
    "SET ROLE vinc_agent_publisher_runtime; UPDATE canonical_objects SET agent_index_authorized=FALSE WHERE FALSE;"
expect_denied \
    'publisher cannot construct staging' \
    "SET ROLE vinc_agent_publisher_runtime; DELETE FROM staging_chunks WHERE FALSE;"

printf '\n== 6. Commit one disposable publication for retrieval verification ==\n'
"${PSQL[@]}" -v run_id="$RUN_ID" <<'SQL'
BEGIN;
SET LOCAL ROLE vinc_agent_publisher_runtime;
SELECT assert_staging_complete(:'run_id'::uuid, 'rev-preflight');
DELETE FROM chunk_embeddings
 WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE asset_key = 'asset-preflight');
DELETE FROM chunks WHERE asset_key = 'asset-preflight';
DELETE FROM sections WHERE asset_key = 'asset-preflight';
INSERT INTO sections
    (section_id, source_revision_id, asset_key, normalized_section_locator,
     section_ordinal, source_section_locator, heading_path)
SELECT * FROM promote_staging_sections(:'run_id'::uuid, 'asset-preflight', 'rev-preflight');
INSERT INTO chunks
    (chunk_id, section_id, source_revision_id, asset_key, canonical_id, url_key,
     canonical_url_order, canonical_url, source_type, source_title, h1, heading_path,
     source_section_locator, chunk_ordinal, chunk_text, chunk_text_sha256, token_count,
     language, content_type, access_scope, sensitivity, instruction_authority,
     domain_authority, "references", source_locator, metadata, ingestion_run_id,
     retrieval_enabled)
SELECT * FROM promote_staging_chunks(
    :'run_id'::uuid, 'asset-preflight', 'VINC-CAN-PREFLIGHT', 'rev-preflight'
);
INSERT INTO chunk_embeddings
    (embedding_id, chunk_id, embedding_model, dimensions, embedding_vector)
SELECT * FROM promote_staging_embeddings(:'run_id'::uuid, 'asset-preflight', 'rev-preflight');
UPDATE source_revisions
   SET operational_current = (source_revision_id = 'rev-preflight')
 WHERE asset_key='asset-preflight';
UPDATE ingestion_runs SET status='PUBLISHED' WHERE run_id=:'run_id'::uuid;
COMMIT;
SQL

printf '\n== 7. Prove retrieval is functional and structurally read-only ==\n'
retrieval_count=$("${PSQL[@]}" -Atqc "
SET ROLE vinc_agent_retrieval_runtime;
SELECT count(*)
  FROM chunks c
  JOIN source_assets sa
    ON sa.asset_key=c.asset_key AND sa.canonical_id=c.canonical_id
  JOIN source_revisions sr
    ON sr.source_revision_id=c.source_revision_id
   AND sr.asset_key=c.asset_key
   AND sr.operational_current=TRUE
  JOIN canonical_objects co
    ON co.canonical_id=c.canonical_id
   AND co.canonical_status='CANONICO_VIGENTE'
   AND co.agent_index_authorized=TRUE
 WHERE c.retrieval_enabled=TRUE
   AND c.canonical_id='VINC-CAN-PREFLIGHT'
   AND c.search_tsv @@ plainto_tsquery('portuguese'::regconfig, 'texto');
")
if [[ "$retrieval_count" != "1" ]]; then
    printf 'retrieval positive-path count mismatch: %s\n' "$retrieval_count" >&2
    exit 1
fi

expect_denied \
    'retrieval cannot read staging' \
    "SET ROLE vinc_agent_retrieval_runtime; SELECT count(*) FROM staging_chunks;"
expect_denied \
    'retrieval cannot delete operational chunks' \
    "SET ROLE vinc_agent_retrieval_runtime; DELETE FROM chunks WHERE FALSE;"
expect_denied \
    'retrieval cannot execute publisher gate' \
    "SET ROLE vinc_agent_retrieval_runtime; SELECT assert_staging_complete('${RUN_ID}'::uuid, 'rev-preflight');"

printf '\nR33 ACL PREFLIGHT: PASS\n'
