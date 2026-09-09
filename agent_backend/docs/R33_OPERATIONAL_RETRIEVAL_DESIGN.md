# R33 — Operational Retrieval Design (pre-deploy)

Status: **CONTRACT_CLOSED / IMPLEMENTATION_PENDING / DO_NOT_APPLY_TO_CLOUD_SQL**

The pre-closure audit findings in this document are retained as evidence of how the runtime gap was discovered. Their staging/ordinal/membership decisions are now closed by `R33_STAGING_TO_OPERATIONAL_CONTRACT.md`. Promotion functions are still not implemented, and no database execution is authorized.

Authority used for this design is intentionally limited to:

- `SCHEMA_POSTGRES_V0_1`
- `CONTRATO_CHUNK_V0_1`
- `R19_STAGING_POSTGRES_V0_1`
- `R20_PUBLISH_ATOMICO_V0_1`
- `R21_RETRIEVAL_READONLY_V0_1`

The live Cloud SQL inspection on 2026-09-08 confirmed that schema `public`
contains only `staging_chunks` and `staging_chunk_embeddings`. This document
does not authorize publication, public access, WordPress wiring, or database
migration execution.

## 1. What is already authoritative

R19 establishes that PostgreSQL staging is transactional and staging-only.
R20 establishes a single atomic publisher as the only visibility-changing path.
R21 establishes policy-first, deny-by-default, read-only retrieval with current
provenance and no web/historical fallback.

`SCHEMA_POSTGRES_V0_1` defines the operational projections required by those
contracts. `CONTRATO_CHUNK_V0_1` defines the fields and invariants of the
retrievable `chunks` table.

## 2. Pre-closure audit findings

### BLK-R33-OP-01 — staging did not carry the complete chunk contract

Current `staging_chunks` contains only:

- `chunk_id`
- `source_revision_id`
- `source_asset_id`
- `chunk_ordinal`
- `chunk_text`
- `content_hash`
- `ingestion_run_id`

`CONTRATO_CHUNK_V0_1` requires, among other fields, `section_id`, `asset_key`,
`canonical_id`, URL binding, source type/title, heading context, token count,
language, content type, access scope, sensitivity, instruction authority,
domain authority, reproducible source locator, metadata, and retrieval state.

**Contract status: RESOLVED.** P07 staging must carry every source field required
for the operational contract. `created_at` and `search_tsv` remain derived by
the database/index. The publisher may not synthesize missing fields.

### BLK-R33-OP-02 — ordinal semantics disagreed

Current historical R19 code/tests used contiguous zero-based ordinals (`0, 1, ...`).
`CONTRATO_CHUNK_V0_1` requires `chunk_ordinal >= 1`.

**Contract status: RESOLVED.** Ordinals are one-based end-to-end: P07 emits `1..N`,
staging preserves them, publisher copies them unchanged, operational storage
preserves them.

### BLK-R33-OP-03 — R20 SQL depends on functions that do not exist

`AtomicPublisher` invokes:

- `assert_staging_complete(...)`
- `promote_staging_chunks(...)`
- `promote_staging_embeddings(...)`

No implementation of those functions is present in the versioned SQL.

**Status: IMPLEMENTATION_PENDING.** The staging contract is now sufficient to
author those functions, but they must be implemented/tested in a later commit
before any Cloud SQL migration execution.

### BLK-R33-OP-04 — membership cardinality needed an explicit projection rule

The original design gave `source_assets` a singular `membership_id`, while the
canonical registry can authorize one canonical object for multiple scopes and
corpora.

**Contract status: RESOLVED.** `source_assets` references only `canonical_id`.
`corpus_memberships` contains one row per valid pair. v0.1 accepts only
`PUBLICO/CORPUS_PUBLICO` and `INTERNO/CORPUS_INTERNO`; crossed pairs fail closed.

## 3. Safe versioned artifacts

`sql/002_r33_operational_retrieval.sql` is a **DDL-only design migration**.
It creates the minimum operational retrieval projection needed by R20/R21:

- `canonical_objects`
- `corpus_memberships`
- `source_assets`
- `ingestion_runs`
- `source_revisions`
- `canonical_urls`
- `sections`
- `chunks`
- `chunk_embeddings`

It deliberately does **not** define promotion functions and does not contain
data mutation statements (`INSERT`, `UPDATE`, `DELETE`).

It must not be applied to Cloud SQL until the enriched staging/promotion
implementation is complete, covered by tests, and explicitly reauthorized.

## 4. Concrete PostgresReadModel

`src/vinc_agent/postgres_read_model.py` implements the existing R21
`RetrievalReadPort` against the future operational tables.

For this R33 step it supports only lexical retrieval because the public R32
boundary currently requests `("lexical",)`.

Its security properties are:

1. exact canonical-id allowlist is present in the SQL `WHERE` clause before
   ranking;
2. only `retrieval_enabled = TRUE` rows are candidates;
3. only `CANONICO_VIGENTE` and `agent_index_authorized = TRUE` objects are
   candidates;
4. only `operational_current = TRUE` source revisions are candidates;
5. unsupported vector/structured modes fail closed;
6. current provenance uses the same operational-current constraint and maps
   `chunk_text_sha256` to the retrieval `content_hash`;
7. zero allowlist performs no database read.

The read model does not reinterpret registry scope/corpus values. That authority
remains upstream in `CanonicalPolicyAdapter`, which now also rejects crossed
scope/corpus pairs before candidate generation.

## 5. Next implementation step before any Cloud SQL DDL

The contract is closed. The next code-only act is now mechanical rather than
architectural:

1. add versioned enriched staging structures (`staging_sections` + complete
   staging chunk fields);
2. update staging writer/DTOs to populate them;
3. implement and test `assert_staging_complete`;
4. implement and test section/chunk/embedding promotion;
5. run full CI;
6. review the migration diff;
7. only then request authorization to execute DDL in Cloud SQL;
8. verify schema and row counts read-only;
9. populate only canonically authorized current corpus;
10. wire `PostgresReadModel` into the private runtime and perform one
    authenticated service-to-service query.
