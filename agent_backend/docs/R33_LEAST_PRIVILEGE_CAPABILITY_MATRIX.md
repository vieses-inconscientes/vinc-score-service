# R33 — Least-Privilege Capability Matrix v0.1

Status: **CAPABILITY_CONTRACT_FROZEN / PRINCIPAL_ASSIGNMENT_PENDING / NO_DB_CHANGE**

This document freezes the database capabilities required by the current R19/R20/R21 implementation without yet deciding which concrete database principal, role, service account, or runtime identity will receive each capability.

It is intentionally a design/governance artifact. It does **not** authorize any `GRANT`, `REVOKE`, role creation, role membership change, Cloud SQL mutation, corpus population, publisher execution, retrieval activation, endpoint wiring, IAM change, or WordPress change.

## 1. Authority boundary

The capability matrix is derived only from the approved V'inC Agent authorities and the implementation already materialized under them:

- `SCHEMA_POSTGRES_V0_1`
- `CONTRATO_CHUNK_V0_1`
- `R19_STAGING_POSTGRES_V0_1`
- `R20_PUBLISH_ATOMICO_V0_1`
- `R21_RETRIEVAL_READONLY_V0_1`
- `R33_STAGING_TO_OPERATIONAL_CONTRACT.md`
- `R33_OPERATIONAL_RETRIEVAL_DESIGN.md`
- current code in `persistence.py`, `publisher.py`, `postgres_read_model.py`
- live ACL/role inspection performed after controlled deployment of migrations 002→005

The institutional hierarchy remains above this technical artifact: Carta Fundacional A0.0 and the canonical V'inC Evidence Methodological Statute govern what scientific/methodological behavior may later be implemented. Database capability never constitutes scientific authorization.

## 2. Architectural invariant

**Capability is not identity.**

This document defines what a component must be able to do. It deliberately does not decide whether one principal or several principals will carry those capabilities.

The placeholders below are logical capability classes only:

- `CAP_STAGING_WRITER`
- `CAP_PUBLISHER`
- `CAP_RETRIEVAL_READER`
- `CAP_MIGRATION_ADMIN` (controlled human/administrative path, not runtime)

No PostgreSQL role with these names is authorized by this document.

## 3. Frozen capability matrix

| Capability | Authority | Required operations | Explicitly forbidden |
|---|---|---|---|
| `CAP_STAGING_WRITER` | R19 | transactional delete-by-`ingestion_run_id` + insert into `staging_sections`, `staging_chunks`, `staging_chunk_embeddings`; read only the predicate columns needed to target the current run | operational corpus writes; visibility changes; DDL; publisher actions; policy decisions |
| `CAP_PUBLISHER` | R20 | execute `assert_staging_complete` and the three `promote_staging_*` projections; read the staging/metadata fields those SECURITY INVOKER functions require; atomically replace `sections`, `chunks`, `chunk_embeddings`; update `source_revisions.operational_current`; update `ingestion_runs.status` | semantic repair; partial merge; DDL; web/history fallback; metadata invention; publication without gate PASS |
| `CAP_RETRIEVAL_READER` | R21 | read-only access to the operational relations actually queried by `PostgresReadModel`: `chunks`, `source_assets`, `source_revisions`, `canonical_objects` | INSERT/UPDATE/DELETE; DDL; historical fallback; policy bypass; direct corpus expansion |
| `CAP_MIGRATION_ADMIN` | controlled R33 deployment procedure | versioned DDL/migration execution under explicit checkpoint, review, rollback path and separate authorization | use as ordinary runtime identity; corpus operation by convenience; permanent application traffic |

## 4. R19 — staging writer: exact current requirement

`PostgresStagingIndexer.build_enriched_staging()` performs, in one transaction:

1. `DELETE FROM staging_chunk_embeddings WHERE ingestion_run_id = ...`
2. `DELETE FROM staging_chunks WHERE ingestion_run_id = ...`
3. `DELETE FROM staging_sections WHERE ingestion_run_id = ...`
4. INSERT complete section rows into `staging_sections`
5. INSERT complete promotion-compatible chunk rows into `staging_chunks`
6. INSERT embeddings, when present, into `staging_chunk_embeddings`
7. commit, or rollback on failure

Therefore the frozen minimum capability is:

- `DELETE` on the three staging tables;
- `INSERT` on the three staging tables for the columns enumerated by the implementation;
- `SELECT` only as required for columns referenced by delete predicates (currently `ingestion_run_id`) unless a later tested grant design proves a narrower equivalent.

R19 does **not** need direct privileges on `sections`, `chunks`, `chunk_embeddings`, `source_revisions`, `ingestion_runs`, or canonical metadata tables merely to stage data.

### Current live mismatch

The live audit confirmed that the existing R30 role `vinc_agent_runtime` supplies the application identity with the historical staging capability for:

- `staging_chunks`
- `staging_chunk_embeddings`

but the newly introduced `staging_sections` is not yet covered by that historical grant set.

This is a compatibility gap, not authority to issue a grant ad hoc.

## 5. R20 — atomic publisher: exact current requirement

`AtomicPublisher.publish()` is the sole current visibility-changing adapter. Its current SQL path requires the ability to:

- execute `assert_staging_complete(uuid,text)`;
- delete prior operational embeddings/chunks/sections for the explicit `asset_key`;
- insert sections from `promote_staging_sections(...)`;
- insert chunks from `promote_staging_chunks(...)`;
- insert embeddings from `promote_staging_embeddings(...)`;
- update `source_revisions.operational_current` for the explicit asset;
- update `ingestion_runs.status` to `PUBLISHED` for the explicit run;
- commit atomically; otherwise rollback.

The four gate/promotion functions are currently created without `SECURITY DEFINER`; therefore they execute under the caller's privileges. Under the current implementation, publisher capability must account for the underlying reads performed by those functions against:

- `source_revisions`
- `source_assets`
- `canonical_urls`
- `staging_sections`
- `staging_chunks`
- `staging_chunk_embeddings`

and for the direct reads needed by its own predicates/subqueries against operational tables.

This document does not redesign those functions as `SECURITY DEFINER`; doing so would be a separate architectural/security decision.

### Direct function execution

Only these functions are part of the current publisher call path:

- `assert_staging_complete(uuid,text)`
- `promote_staging_sections(uuid,text,text)`
- `promote_staging_chunks(uuid,text,text,text)`
- `promote_staging_embeddings(uuid,text,text)`

`vinc_set_chunks_search_tsv()` is a trigger helper. Direct runtime invocation of that helper is not an R20 requirement.

## 6. R21 — retrieval reader: exact current requirement

`PostgresReadModel` currently supports lexical retrieval only and directly queries:

- `chunks`
- `source_assets`
- `source_revisions`
- `canonical_objects`

Its SQL enforces current provenance and authorized canonical IDs before ranking. It performs no DML.

Therefore `CAP_RETRIEVAL_READER` requires only `SELECT` over the fields used by those queries. It does not require direct access to:

- `staging_*`
- `chunk_embeddings` for current lexical mode
- `corpus_memberships`
- `canonical_urls`
- promotion functions
- migration/DDL capability

If vector or structured retrieval is later authorized, this matrix must be revised before privileges are expanded.

## 7. Public EXECUTE discovered in the live database

Post-deployment ACL inspection showed that the five R33 functions currently expose `EXECUTE` through PostgreSQL's `PUBLIC` grantee rather than a direct grant to `vinc_agent_app`.

That observed state must not be mistaken for the target least-privilege policy.

It is also not authorization to revoke `PUBLIC EXECUTE` immediately. Before hardening, a disposable PostgreSQL test must prove the behavior of:

- publisher calls after explicit function grants;
- the `chunks_search_tsv_before_write` trigger after any change to function ACLs;
- rollback and idempotent migration behavior.

Only then may an ACL migration encode the final rule.

## 8. Operational metadata writer remains unresolved

The current operational schema contains metadata relations required before publish/retrieval can succeed:

- `canonical_objects`
- `corpus_memberships`
- `source_assets`
- `ingestion_runs`
- `source_revisions`
- `canonical_urls`

The audited R19/R20/R21 implementation does **not** establish a complete authorized writer for initially materializing all of those relations.

R20 updates `source_revisions.operational_current` and `ingestion_runs.status`, but that does not authorize it to create or populate the metadata plane.

Therefore the following is frozen as an explicit blocker/gap:

**BLK-R33-ACL-01 — operational metadata materialization authority is unresolved.**

No INSERT/UPDATE privileges over those metadata relations may be added by inference. The authority and responsible component must be found in existing canonical material or separately decided before corpus population.

## 9. A / B / C classification

### A — preserved canonical principles

- R19 writes staging only.
- R20 is the sole visibility-changing publication boundary.
- R20 publication is atomic and fail-closed.
- R21 is read-only, policy-first, deny-by-default, current-provenance-only.
- No historical/web/generative fallback may be used to repair missing authority or provenance.
- Technical capability never creates methodological/scientific authorization.

### B — mechanically derived implementation requirements

- R19 now needs equivalent staging write capability on `staging_sections` in addition to the two historical staging tables.
- R20 needs the DML and underlying read capability actually exercised by `publisher.py` and its SECURITY INVOKER gate/projection functions.
- R21 needs SELECT only on the four relations queried by `postgres_read_model.py` for lexical retrieval.
- the trigger helper does not need to be directly callable merely because inserts into `chunks` fire the trigger.

These are consequences of approved contracts plus current code; they do not decide identity topology.

### C — decisions still requiring explicit authorization

- whether one or several database principals will carry R19/R20/R21 capabilities;
- names of any new PostgreSQL roles;
- whether `vinc_agent_runtime` will remain staging-only or be expanded;
- whether publisher and retrieval will share an application DB identity;
- whether grants will be table-level or column-level where both can satisfy the contract;
- whether any function will be redesigned as `SECURITY DEFINER`;
- whether/when `PUBLIC EXECUTE` will be revoked;
- which component/identity materializes the operational metadata plane;
- any future vector/structured retrieval privileges.

No C item may be silently encoded in SQL.

## 10. Current-state map for future maintenance

When a future change request says "open/close access", locate the affected layer before editing privileges:

- **R19 / staging ingestion changed** → inspect `persistence.py`, staging table grants, staging tests.
- **R20 / publication changed** → inspect `publisher.py`, gate/projection functions, operational DML grants, rollback tests.
- **R21 / retrieval changed** → inspect `postgres_read_model.py`, policy-first contract, read-only grants, retrieval tests.
- **scientific/corpus authorization changed** → inspect canonical governance/policy first; database ACL is not the source of scientific permission.
- **new metadata source/process introduced** → resolve BLK-R33-ACL-01 before granting write access.

## 11. Next safe act

The next act after this matrix is frozen is **not** a live `GRANT`/`REVOKE`.

Sequence:

1. audit whether existing canonical material already resolves the principal/role topology and metadata writer authority;
2. if not, record the unresolved choices explicitly for decision;
3. only after that decision, implement a versioned ACL migration (candidate future `006_r33_least_privilege.sql`);
4. add disposable PostgreSQL tests for positive and negative privilege cases;
5. prove idempotency, function/trigger behavior and rollback;
6. run CI and review the diff;
7. obtain a separate live-database application authorization;
8. apply and re-audit effective privileges read-only.

Until those steps are complete, the live database must remain unchanged by this capability-design document.
