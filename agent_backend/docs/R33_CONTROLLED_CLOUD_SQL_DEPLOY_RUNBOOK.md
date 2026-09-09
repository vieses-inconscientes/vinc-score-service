# R33 Controlled Cloud SQL Deployment Runbook

Status: **PREPARED / DO NOT EXECUTE WITHOUT EXPLICIT AUTHORIZATION**

Authority: `SCHEMA_POSTGRES_V0_1`, `CONTRATO_CHUNK_V0_1`, R19, R20, R21, `R33_STAGING_TO_OPERATIONAL_CONTRACT.md`, the R33 SQL deployment preflight, and the live read-only ownership/principal inspection recorded in `REGISTRO_CANONICO_VINC__AGENT__v0.1`.

This runbook governs only the structural deployment of migrations `002` through `005` to the existing Cloud SQL database. It does **not** authorize corpus ingestion, publication, runtime wiring, IAM/gateway changes, WordPress changes, or exposure of `/internal/v1/query`.

## 1. Fixed target and separation of duties

Target:

- Google Cloud project: `vinc-agent-internal-beta`
- Cloud SQL instance: `vinc-agent-postgres-beta`
- Region: `southamerica-east1`
- Database: `vinc_agent`
- Structural migration principal: `postgres`
- Runtime principal: `vinc_agent_app`

Live read-only evidence established before this runbook:

- `vinc_agent_app` has no `CREATE` privilege on database/schema and must not be elevated for this deployment.
- `postgres` owns `staging_chunks`, `staging_chunk_embeddings`, and the installed `vector` extension.
- `postgres` has `CREATE` on database `vinc_agent` and schema `public`.
- Live pgvector version is `0.8.5`.
- Known live baseline contains only `staging_chunks` and `staging_chunk_embeddings` as public base tables.

## 2. Authorized migration set

Only these files, in this exact order, are in scope:

1. `agent_backend/sql/002_r33_operational_retrieval.sql`
2. `agent_backend/sql/003_r33_enriched_staging.sql`
3. `agent_backend/sql/004_r33_staging_completeness_gate.sql`
4. `agent_backend/sql/005_r33_atomic_promotion_functions.sql`

Current migration blob SHAs at runbook preparation time:

- `002`: `8d846ff8979da1502b555a45f9c302d47c7eab38`
- `003`: `4a418c86a077b59cca9c466b602259a162f8c0a6`
- `004`: `134fbb30f71b1bf589076ddaca3a26cf44fa1495`
- `005`: `d10060fcac43f4d51d34681ee580a60aec427d11`

The deployment authorization record must name the exact Git commit SHA being deployed. A branch name alone is not sufficient authority. If any migration blob SHA differs from the values above, stop and repeat the disposable SQL preflight before considering live deployment.

## 3. Hard stop conditions

Do not begin DDL if any of the following is true:

- explicit deployment authorization has not been recorded after this runbook review;
- the exact repository commit has not passed Agent Backend CI;
- PostgreSQL/pgvector compatibility for the live pgvector version has not passed the disposable preflight;
- the live database is not `vinc_agent`;
- the connected migration user is not `postgres`;
- `staging_chunks` or `staging_chunk_embeddings` is not owned by `postgres`;
- unexpected public base tables already exist;
- any R33 operational table/function already exists in an unexplained state;
- a recoverability checkpoint (backup/PITR evidence) has not been recorded immediately before deployment;
- the exact `postgres` credential is not available through an approved secure path;
- any pre-deploy query returns an unexpected result.

Never solve a stop condition by granting `CREATE` to `vinc_agent_app`.

## 4. Deployment transport

Use Cloud SQL Studio for read-only inspection only.

For DDL, use `psql` against the Cloud SQL instance from an authenticated administrative environment with the repository checked out at the exact authorized commit. The four migration files must be executed by one `psql` process with `ON_ERROR_STOP=1` and `--single-transaction` so an error prevents commit of the entire migration set.

Do not copy/paste the four migrations manually into separate Cloud SQL Studio executions; that would weaken the all-or-nothing guarantee and increase transcription risk.

Recommended execution form after the secure database connection is established:

```bash
psql -X --no-psqlrc \
  -v ON_ERROR_STOP=1 \
  --single-transaction \
  -f agent_backend/sql/002_r33_operational_retrieval.sql \
  -f agent_backend/sql/003_r33_enriched_staging.sql \
  -f agent_backend/sql/004_r33_staging_completeness_gate.sql \
  -f agent_backend/sql/005_r33_atomic_promotion_functions.sql
```

This command is **not authorized for execution merely because it appears in this runbook**.

## 5. Pre-deploy evidence — read only

Record all results before DDL.

### 5.1 Identity and extension

```sql
SELECT
    current_database() AS database_name,
    current_user AS current_user,
    current_setting('server_version') AS server_version,
    (SELECT extversion FROM pg_extension WHERE extname = 'vector') AS pgvector_version,
    has_schema_privilege(current_user, 'public', 'CREATE') AS can_create_in_public,
    has_database_privilege(current_user, current_database(), 'CREATE') AS can_create_in_database;
```

Expected at deployment time:

- database: `vinc_agent`
- user: `postgres`
- PostgreSQL major: `18`
- pgvector: version explicitly covered by green disposable preflight
- both CREATE privilege checks: `true`

### 5.2 Existing public base tables and ownership

```sql
SELECT tablename, tableowner
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;
```

Expected live baseline before first deployment:

- `staging_chunk_embeddings` — owner `postgres`
- `staging_chunks` — owner `postgres`

No additional base table is silently accepted.

### 5.3 Existing R33 objects must be absent before the first deployment

```sql
SELECT
    to_regclass('public.canonical_objects') AS canonical_objects,
    to_regclass('public.corpus_memberships') AS corpus_memberships,
    to_regclass('public.source_assets') AS source_assets,
    to_regclass('public.ingestion_runs') AS ingestion_runs,
    to_regclass('public.source_revisions') AS source_revisions,
    to_regclass('public.canonical_urls') AS canonical_urls,
    to_regclass('public.sections') AS sections,
    to_regclass('public.chunks') AS chunks,
    to_regclass('public.chunk_embeddings') AS chunk_embeddings,
    to_regclass('public.staging_sections') AS staging_sections,
    to_regprocedure('public.assert_staging_complete(uuid,text)') AS completeness_gate,
    to_regprocedure('public.promote_staging_sections(uuid,text,text)') AS promote_sections,
    to_regprocedure('public.promote_staging_chunks(uuid,text,text,text)') AS promote_chunks,
    to_regprocedure('public.promote_staging_embeddings(uuid,text,text)') AS promote_embeddings;
```

For the first deployment, every value above must be `NULL`.

### 5.4 Preserve staging row-count baseline

```sql
SELECT
    (SELECT count(*) FROM staging_chunks) AS staging_chunks_rows,
    (SELECT count(*) FROM staging_chunk_embeddings) AS staging_embeddings_rows;
```

Record both numbers. Migrations `002`–`005` are structural and must not delete or publish staged content.

## 6. Recoverability checkpoint

Immediately before DDL, record evidence that recovery is available for this instance. The deployment record must include either:

- an on-demand backup created for this deployment, with identifier/timestamp; or
- verified point-in-time recovery coverage sufficient for the deployment window, with timestamp/evidence.

If recoverability cannot be evidenced, stop.

The SQL transaction rollback is the first recovery mechanism for migration errors; Cloud SQL backup/PITR is the defense for failures outside the SQL transaction boundary or operator/environment mistakes.

## 7. Deployment transaction

After all preconditions pass and explicit authorization has been recorded:

1. check out the exact authorized Git commit;
2. verify the four migration blob SHAs match Section 2;
3. establish the secure database connection as `postgres` to `vinc_agent`;
4. run the four files with `psql --single-transaction -v ON_ERROR_STOP=1` in the exact order `002 → 003 → 004 → 005`;
5. treat any non-zero `psql` exit as deployment failure;
6. do not run corpus ingestion or publisher actions in the same maintenance act.

Because PostgreSQL transactional DDL is used, any migration error before successful completion must abort the transaction rather than leave an intentionally partial R33 schema.

## 8. Immediate post-deploy verification — read only

### 8.1 Expected base tables

```sql
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_type = 'BASE TABLE'
ORDER BY table_name;
```

Expected set after deployment:

- `canonical_objects`
- `canonical_urls`
- `chunk_embeddings`
- `chunks`
- `corpus_memberships`
- `ingestion_runs`
- `sections`
- `source_assets`
- `source_revisions`
- `staging_chunk_embeddings`
- `staging_chunks`
- `staging_sections`

No corpus population is expected from the migrations.

### 8.2 Expected R33 functions

```sql
SELECT
    to_regprocedure('public.assert_staging_complete(uuid,text)') AS completeness_gate,
    to_regprocedure('public.promote_staging_sections(uuid,text,text)') AS promote_sections,
    to_regprocedure('public.promote_staging_chunks(uuid,text,text,text)') AS promote_chunks,
    to_regprocedure('public.promote_staging_embeddings(uuid,text,text)') AS promote_embeddings;
```

All four must be non-NULL.

### 8.3 Staging row counts unchanged

Re-run the row-count query from Section 5.4 and compare to the recorded pre-deploy values. Any unexplained difference is a deployment incident and blocks the next R33 step.

### 8.4 Operational plane remains empty immediately after structural deployment

```sql
SELECT
    (SELECT count(*) FROM canonical_objects) AS canonical_objects_rows,
    (SELECT count(*) FROM corpus_memberships) AS corpus_memberships_rows,
    (SELECT count(*) FROM source_assets) AS source_assets_rows,
    (SELECT count(*) FROM source_revisions) AS source_revisions_rows,
    (SELECT count(*) FROM sections) AS sections_rows,
    (SELECT count(*) FROM chunks) AS chunks_rows,
    (SELECT count(*) FROM chunk_embeddings) AS chunk_embeddings_rows;
```

For this structural-only act, all counts are expected to be zero unless a separately authorized prior metadata operation is explicitly documented. This runbook does not authorize such an operation.

### 8.5 Runtime separation remains intact

```sql
SELECT
    has_schema_privilege('vinc_agent_app', 'public', 'CREATE') AS runtime_can_create_public,
    has_database_privilege('vinc_agent_app', current_database(), 'CREATE') AS runtime_can_create_database;
```

Expected: `false`, `false`.

## 9. Success criteria

The structural deployment is PASS only when all of the following are true:

- exact authorized commit and migration blobs were used;
- one single transaction completed successfully;
- expected tables/functions exist;
- pre-existing staging row counts are unchanged;
- no corpus was populated or promoted;
- `vinc_agent_app` remains without CREATE authority;
- `/internal/v1/query` remains unwired;
- gateway/IAM/WordPress remain unchanged;
- evidence and timestamps are written back to the canonical R33 registry.

## 10. Failure handling

If `psql` fails before completion:

- do not retry blindly;
- record the exact error and exit status;
- confirm the transaction rolled back by re-running the pre-deploy object/baseline checks;
- stop R33 deployment work until the cause is reproduced and corrected in a disposable PostgreSQL 18 + matching-pgvector environment;
- do not patch the live database manually to make the migration continue.

If post-deploy verification fails after a successful transaction:

- classify the mismatch before any corrective DDL;
- preserve the live evidence;
- do not populate corpus or wire runtime;
- decide recovery from evidence, using transactional reversibility and the recorded Cloud SQL recovery checkpoint as applicable.

## 11. Explicit boundary after structural deployment

A successful `002 → 005` deployment changes only the database structure. It does **not** prove that the operational public corpus exists, that `PostgresReadModel` is composed into the live service, that model generation is wired, or that service-to-service IAM works.

The next R33 act after structural PASS must therefore be separately authorized and evidenced. No automatic continuation is permitted.
