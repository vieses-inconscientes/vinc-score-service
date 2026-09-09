# R33 — Operational Retrieval Design (pre-deploy)

Status: **DESIGN_ONLY / DO_NOT_APPLY_TO_CLOUD_SQL**

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

## 2. Audit findings that block deployment

### BLK-R33-OP-01 — staging does not carry the complete chunk contract

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

R20 promotion therefore cannot safely synthesize a complete operational chunk
from the current staging row without inventing data.

### BLK-R33-OP-02 — ordinal semantics disagree

Current `ChunkBatch`/R19 tests use contiguous zero-based ordinals (`0, 1, ...`).
`CONTRATO_CHUNK_V0_1` requires `chunk_ordinal >= 1`.

A promotion function must not silently translate this until the canonical
contract explicitly states where the conversion belongs.

### BLK-R33-OP-03 — R20 SQL depends on functions that do not exist

`AtomicPublisher` invokes:

- `assert_staging_complete(...)`
- `promote_staging_chunks(...)`
- `promote_staging_embeddings(...)`

No implementation of those functions is present in the versioned SQL, and the
current staging shape is insufficient to implement `promote_staging_chunks`
without the missing metadata above.

### BLK-R33-OP-04 — membership cardinality needs an explicit projection rule

`SCHEMA_POSTGRES_V0_1` gives `source_assets` a singular `membership_id`, while
the canonical registry can authorize one canonical object for multiple scopes
and corpora (for example `PUBLICO|INTERNO` and
`CORPUS_PUBLICO|CORPUS_INTERNO`).

This design preserves the schema field but does not invent a normalization
rule. Corpus/scope authorization remains in the live canonical policy adapter
until the projection rule is explicitly closed.

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

It must not be applied to Cloud SQL until BLK-R33-OP-01 through OP-04 are
resolved and covered by tests.

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

The read model does not reinterpret pipe-delimited registry scope/corpus values.
That authority remains upstream in `CanonicalPolicyAdapter`, which supplies the
already-scoped `CandidateFilter`.

## 5. Required next step before any Cloud SQL DDL

Close the staging-to-operational mapping explicitly. The smallest safe contract
change is to define a staging record that already contains every immutable or
governance-derived field required by `CONTRATO_CHUNK_V0_1`, or to define a
canonical enrichment join whose inputs and precedence are fully specified.

Only then should we:

1. implement and test `assert_staging_complete`;
2. implement and test `promote_staging_chunks`;
3. implement and test `promote_staging_embeddings`;
4. run the full CI;
5. review the migration diff;
6. execute DDL in Cloud SQL;
7. verify schema and row counts read-only;
8. wire `PostgresReadModel` into the private runtime;
9. perform one authenticated service-to-service query;
10. only after that continue the WordPress/public-gateway portion of R33.
