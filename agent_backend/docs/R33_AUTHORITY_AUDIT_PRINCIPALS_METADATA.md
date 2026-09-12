# R33 — Authority Audit: Principals and Operational Metadata v0.1

Status: **AUTHORITY_AUDIT_CLOSED / PARTIAL_AUTHORITY_FOUND / DECISIONS_REQUIRED / NO_DB_CHANGE**

This document answers the two authority questions that had to be resolved before any future `006_r33_least_privilege.sql` may be written:

1. Do existing V'inC Agent authorities determine which database principal/role must carry the R19, R20 and R21 capabilities?
2. Do existing authorities determine which component/identity is authorized to materialize the operational metadata plane?

The audit is intentionally limited to already-approved V'inC Agent authorities and the currently versioned implementation. It does not create or imply any `GRANT`, `REVOKE`, PostgreSQL role, role membership, service account, corpus population, publisher execution, retrieval activation, endpoint wiring, IAM change or WordPress change.

## 1. Authorities inspected

Canonical registry/workbook authorities:

- `PIPELINE_INGESTAO_V0_1`
- `CONTRATO_BACKEND_V0_1`
- `INTERFACES_MODULOS_V0_1`
- `DEPENDENCIAS_BACKEND_V0_1`
- `SCHEMA_POSTGRES_V0_1`
- `R18_CANONICAL_PIPELINE_V0_1`
- `R19_STAGING_POSTGRES_V0_1`
- `R20_PUBLISH_ATOMICO_V0_1`
- `R21_RETRIEVAL_READONLY_V0_1`
- `R30_INTERNAL_BETA_READINESS_V0_1`
- R33 live ACL/role audit records

Versioned GitHub evidence:

- `R33_STAGING_TO_OPERATIONAL_CONTRACT.md`
- `R33_OPERATIONAL_RETRIEVAL_DESIGN.md`
- `R33_LEAST_PRIVILEGE_CAPABILITY_MATRIX.md`
- `persistence.py`
- `publisher.py`
- `postgres_read_model.py`
- `canonical_adapters.py`
- `pipeline.py`
- migrations `002` through `005`

The institutional hierarchy remains above this audit: the Carta Fundacional A0.0 and the canonical V'inC Evidence Methodological Statute govern scientific/methodological authority. Nothing in this document creates scientific authorization.

## 2. Question 1 — who carries R19 / R20 / R21?

### 2.1 What the canonical material DOES resolve

The architecture assigns capabilities unambiguously at the logical module level:

- **R19 / staging write** belongs to the indexing/persistence path. `M09 indexer` is authorized to create staging lexical/vector state and `D09` limits it to staging; `PostgresStagingIndexer` implements the current database writes.
- **R20 / visibility-changing publication** belongs exclusively to `M10 publisher`. `D10`, `I11` and the R20 contract make publisher the sole visibility-changing path and require one atomic transaction with rollback/fail-closed behavior.
- **R21 / retrieval** belongs to `M11 retrieval`, using persistence read models only. `D11`, `I16/I17` and R21 require read-only, policy-first, current-provenance retrieval with no write path.
- `M13 persistence` supplies repositories/transactions and may read/write only on behalf of an already-authorized caller. It is explicitly not business authority by itself.

Therefore the capability-to-component mapping is not open to redesign:

| Capability | Authorized logical owner |
|---|---|
| `CAP_STAGING_WRITER` | R19 / M09 indexer via M13 persistence |
| `CAP_PUBLISHER` | R20 / M10 publisher via M13 persistence |
| `CAP_RETRIEVAL_READER` | R21 / M11 retrieval via M13 persistence read model |
| `CAP_MIGRATION_ADMIN` | controlled administrative deployment path, never normal runtime |

### 2.2 What the canonical material DOES NOT resolve

No inspected authority specifies the concrete PostgreSQL principal topology for the completed R33 operational architecture.

In particular, no canonical authority says that:

- one login must carry all three capabilities;
- R19, R20 and R21 must use separate logins;
- `vinc_agent_runtime` must be expanded beyond its R30 staging purpose;
- publisher and retrieval must share the existing `vinc_agent_app` login;
- a specific new PostgreSQL role name must be created;
- a specific Cloud Run service identity must map one-to-one to a database role.

R30 created `vinc_agent_runtime` as a NOLOGIN role and assigned `vinc_agent_app` only the historical R19 staging privileges needed at that time. That proves an existing staging runtime topology; it does **not** authorize silently expanding the same role to R20 publication or R21 retrieval.

**Conclusion Q1:**

- logical component ownership = **RESOLVED**;
- concrete database principal/role topology = **UNRESOLVED DECISION C**.

A future ACL migration must not encode a concrete identity topology until that decision is explicitly approved.

## 3. Question 2 — who materializes the operational metadata plane?

The answer is not a single yes/no. Existing authorities resolve the authoritative source and lifecycle for several metadata classes, but do not fully assign the writer component/principal.

### 3.1 Governance projections — source and timing are resolved

`SCHEMA_POSTGRES_V0_1` defines the database as an operational projection, not the governance authority:

- `canonical_objects` is a technical mirror of approved Registry objects and must sync before ingestion;
- `corpus_memberships` is the operational scope/corpus authorization projection;
- `source_assets` is updated only from Registry/Manifest authority, never free discovery;
- `canonical_urls` is replace/sync from `116_URLs_VINC`, never generated by an LLM.

`PIPELINE_INGESTAO_V0_1` reinforces the ordering:

- P01 DISCOVER may materialize only objects/assets explicitly declared by the Registry/Manifest;
- P02 AUTHORIZE consumes `canonical_objects + corpus_memberships` already projected from the Registry;
- P03 FETCH consumes exact `source_assets` identity.

Thus the **what**, **source**, and **pre-ingestion timing** of those projections are already governed.

### 3.2 But the writer component is not assigned

The same canonical material prevents us from simply assigning that write to existing modules by inference:

- `M02 registry` owns only an in-memory `RegistrySnapshot`; its contract says the governance authority remains in the Google Sheet and explicitly says **no backend governance write in v0.1**.
- `I01 load_snapshot` is an EFFECTFUL_READ interface, not a projection-write interface.
- `D02 registry → Google Sheets adapter` permits external read only and says **sem escrita automática**.
- `M01 orchestrator` says it writes only run state through audit/persistence; it is not authorized to decide canonicity or become an ad hoc metadata synchronizer.
- `M13 persistence` can execute database I/O only for an authorized caller and therefore cannot create authority by itself.
- the current `canonical_adapters.py` is read-only and constructs snapshots/authorization decisions; it has no PostgreSQL materialization path.

Therefore no existing module/interface currently owns a canonical **Registry → operational metadata projection/sync** operation.

### 3.3 Run/audit metadata is partially resolved

For the audit plane, authority is clearer:

- `M12 audit` owns `ingestion_runs + ingestion_audit`;
- `I14 finalize_run` and `I18 record_event` are append/audit persistence interfaces;
- `D12` explicitly authorizes PostgreSQL append-only audit writes.

So audit/run persistence has a logical owner. This does not automatically define a concrete database principal or all lifecycle operations needed to create a run before later R20 status updates.

### 3.4 Source revision creation remains unresolved

The pipeline defines revision semantics but not a complete writer assignment:

- P04 FINGERPRINT derives `source_revision_id` candidate, `material_fingerprint` and provider revision hint;
- `SCHEMA_POSTGRES_V0_1` defines `source_revisions` as the operational revision identity;
- R20/M10 is authorized to flip `operational_current` during atomic publication;
- the R33 completeness gate requires the `source_revision`/`source_asset`/`run` binding to already exist before publication.

But no inspected interface authorizes a module to perform the **initial INSERT/materialization** of `source_revisions` before staging/publish.

That is a real precondition gap, not permission for R20 to invent revision metadata.

### 3.5 Policy snapshot writer is likewise not assigned

`M03 policy` consumes RegistrySnapshot plus an operational `retrieval_policy_snapshot`, but no inspected interface assigns the creation/persistence of that operational snapshot. This is a related metadata-plane gap and must not be hidden in ACL SQL.

## 4. Metadata authority classification

| Metadata class | Source/semantic authority | Logical writer authority | Concrete DB principal |
|---|---|---|---|
| `canonical_objects` | resolved: Registry | **unresolved projection writer** | unresolved |
| `corpus_memberships` | resolved: Registry/policy pairs | **unresolved projection writer** | unresolved |
| `source_assets` | resolved: Registry/Manifest | **unresolved projection writer** | unresolved |
| `canonical_urls` | resolved: `116_URLs_VINC` | **unresolved projection writer** | unresolved |
| `ingestion_runs` | resolved: M12 audit/run lifecycle + R20 status update boundary | partially resolved | unresolved |
| `ingestion_audit` | resolved: M12 audit | resolved logically | unresolved |
| `source_revisions` | resolved semantics: P04/schema; R20 owns current flip only | **initial writer unresolved** | unresolved |
| `retrieval_policy_snapshot` | policy authority resolved conceptually | **writer unresolved** | unresolved |

## 5. Consequence for `006_r33_least_privilege.sql`

The authority audit does **not** authorize writing `006` yet.

A correct ACL migration requires concrete grantees. Existing authority tells us what R19/R20/R21 may do, but not which concrete principal(s) should carry those capabilities. It also reveals that ACLs alone cannot complete the runtime path because a versioned metadata materializer/synchronizer is still missing.

Writing `006` now would force at least two unauthorized choices:

1. choose a principal topology for staging/publisher/retrieval;
2. choose or imply a metadata writer that the canonical architecture has not yet assigned.

Both remain Decision C items.

## 6. Narrow decisions now required

Before SQL 006, explicit architecture decisions are required for exactly these points:

**DEC-R33-IDENTITY-01 — runtime database identity topology**

Choose whether staging writer, publisher and retrieval reader use one or separate database roles/logins, while preserving the already-frozen capability separation. Existing `vinc_agent_runtime` must not be broadened by default.

**DEC-R33-METADATA-01 — canonical projection/materialization component**

Define the module/interface that projects only canonically authorized Registry/Manifest/URL metadata into the operational PostgreSQL metadata plane. It must be deterministic, sync/replace by explicit IDs, deny free discovery, and have no authority to alter the source governance records.

**DEC-R33-REVISION-01 — revision/run initialization responsibility**

Define who creates the pre-publish `ingestion_runs` and `source_revisions` records/bindings required by staging completeness and R20. Preserve P04 as the source of revision identity and R20 as the sole authority to change operational visibility.

A policy-snapshot persistence decision may be included in the metadata materializer decision or separately frozen, but it cannot be inferred from R21 runtime needs.

## 7. Safe sequencing after decisions

Only after those decisions are explicitly frozen should implementation continue in this order:

1. version the missing metadata projection/materialization contract and implementation;
2. add its positive/negative deterministic tests;
3. freeze the concrete DB principal topology;
4. implement `006_r33_least_privilege.sql` against those named principals/roles;
5. test grants/revokes, function ACLs, trigger behavior, rollback and idempotency in disposable PostgreSQL;
6. run full CI and review the diff;
7. request separate authorization before any live ACL or metadata population change.

Until then, the live Cloud SQL database remains structurally deployed but intentionally unpopulated and unchanged by this audit.
