# R33 — Architecture Decisions: Database Identities and Metadata Materialization v0.1

Status: **DECISIONS_FROZEN / IMPLEMENTATION_PENDING / NO_DB_CHANGE**

This document closes the three explicit architecture decisions left open by `R33_AUTHORITY_AUDIT_PRINCIPALS_METADATA.md` before any future `006_r33_least_privilege.sql` may be written.

It is a design/governance decision artifact only. It does **not** itself authorize live Cloud SQL mutation, role/user creation, `GRANT`, `REVOKE`, corpus population, publisher execution, retrieval activation, endpoint wiring, IAM change, Secret Manager change or WordPress change.

The institutional hierarchy remains above this artifact: Carta Fundacional A0.0 and the canonical V'inC Evidence Methodological Statute govern scientific/methodological authority. Operational metadata projection and database privilege never create scientific authorization.

## 1. Design principles used for the decisions

The decisions below optimize simultaneously for:

1. least privilege and fail-closed operation;
2. explicit separation between preparation, publication and retrieval;
3. auditable authority boundaries that can be explained and maintained later;
4. minimal hidden coupling between runtime components;
5. operational simplicity sufficient for a small project without collapsing all capabilities into one credential;
6. preservation of R19 staging-only, R20 sole visibility-changing publisher and R21 read-only retrieval;
7. no free discovery, no historical/web fallback and no metadata invention;
8. future ability to change one capability without silently broadening the others.

## 2. DEC-R33-IDENTITY-01 — runtime database identity topology

**Decision: APPROVED — three isolated normal-runtime trust zones.**

R19/pre-publication ingestion, R20 publication and R21 retrieval shall not share one normal-runtime database login.

The target topology is:

| Trust zone | Logical capability | Target NOLOGIN role | Target application login | Normal purpose |
|---|---|---|---|---|
| ingestion | governance projection + run/revision initialization + R19 staging | `vinc_agent_ingestion_runtime` | `vinc_agent_ingestion_app` | prepare a publish candidate, never make it visible |
| publisher | R20 atomic publication only | `vinc_agent_publisher_runtime` | `vinc_agent_publisher_app` | sole normal-runtime path allowed to change corpus visibility |
| retrieval | R21 read-only retrieval | `vinc_agent_retrieval_runtime` | `vinc_agent_retrieval_app` | serve authorized current evidence; no writes |
| migration/admin | DDL and controlled maintenance | existing controlled administrative path | administrative identity only | explicit migrations/checkpoints; never application traffic |

### 2.1 Why three zones instead of one

A single login carrying staging, publisher and retrieval capability would preserve logical module separation in code but collapse the security boundary at the database. A defect or compromise in the public-facing retrieval path could then reach publication or staging privileges merely because the same credential carries them.

R21 is the path most directly exposed to query-serving runtime and therefore must remain structurally read-only at the database identity level.

R20 changes corpus visibility and therefore receives its own identity. Publication is intentionally a higher-trust operation than candidate preparation.

R19 and the pre-publication metadata lifecycle are grouped into the ingestion zone because both prepare a candidate that remains invisible until R20 revalidates and commits it. This avoids unnecessary proliferation of credentials while preserving the most important security boundary: **prepare ≠ publish ≠ read**.

### 2.2 Existing R30 identities

The existing `vinc_agent_app` + `vinc_agent_runtime` arrangement is classified as **R30 legacy staging topology**.

It shall:

- remain unchanged until a tested transition is ready;
- not be broadened to publisher or retrieval capability;
- not be silently repurposed as the target topology;
- be retired or narrowed only by a separately tested and authorized migration/provisioning step.

### 2.3 Role/login rule

Capability roles are `NOLOGIN`. Normal application logins are mapped one-to-one to their trust-zone role.

A normal application login must not be made a member of more than one of the three target runtime roles. This prevents nominal separation from being defeated by a multi-role login that can simply assume another capability.

Concrete credential provisioning and Cloud Run service-account mapping remain implementation/deployment work and are not performed by this document.

## 3. DEC-R33-METADATA-01 — canonical operational metadata projector

**Decision: APPROVED — introduce a dedicated `OperationalMetadataProjector` boundary in the ingestion zone.**

The operational PostgreSQL metadata plane is a deterministic projection of already-authorized canonical authorities. It is not a new source of governance truth.

The projector shall own synchronization of the following governance-derived relations:

- `canonical_objects`
- `corpus_memberships`
- `source_assets`
- `canonical_urls`

Its inputs are only explicit immutable snapshots/allowlists produced from the canonical Registry, Manifest and official URL authority. It may not discover records by folder browsing, title similarity, web lookup, historical fallback or LLM inference.

### 3.1 Required invariants

The projector must:

- receive canonical IDs and provider IDs from approved authority snapshots;
- sync by explicit deterministic keys;
- reject ambiguous, duplicate or incomplete authority input;
- never change the source Google Sheet/Drive governance records;
- never widen `agent_index_authorized`, corpus membership, access scope or sensitivity;
- never synthesize a canonical URL;
- be idempotent for the same authority snapshot;
- produce a projection/snapshot hash suitable for audit;
- fail closed before ingestion if the projection cannot be proven consistent;
- use M13/persistence only as a typed database adapter, not as a source of authority.

### 3.2 Placement in the pipeline

The projector executes before an asset proceeds through authorization/fetch for an ingestion run.

Conceptually:

`canonical authority snapshot -> OperationalMetadataProjector -> operational metadata projection -> P02 AUTHORIZE / P03 FETCH prerequisites`

This preserves the existing rule that P02 consumes projected `canonical_objects + corpus_memberships` and P03 consumes exact `source_assets` identity.

### 3.3 Scope deliberately excluded

The first projector contract does not silently absorb unrelated lifecycle state.

It does **not** own:

- `sections`, `chunks`, `chunk_embeddings`;
- staging tables;
- publication;
- scientific interpretation;
- source governance edits;
- historical corpus preservation;
- arbitrary `retrieval_policy_snapshot` persistence until that persistence contract is separately frozen.

## 4. DEC-R33-REVISION-01 — run and source-revision initialization

**Decision: APPROVED — initialization belongs to the pre-publication ingestion zone; visibility changes remain exclusive to R20.**

The lifecycle is split by authority:

### 4.1 `ingestion_runs`

The audit/run lifecycle creates the `ingestion_runs` row when a run begins. This is invoked in the ingestion zone through a typed persistence repository.

The initial record is operational/audit state, not corpus visibility.

R20 may later update that explicit run to `PUBLISHED` only as part of the successful atomic publication transaction.

### 4.2 `source_revisions`

P04 FINGERPRINT remains the sole semantic source of the candidate revision identity/material fingerprint.

After P04 determines a materially changed revision, the ingestion lifecycle registers exactly one `source_revisions` candidate bound to:

- the already-projected `source_asset`;
- the current `ingestion_run`;
- the P04 `material_fingerprint`;
- the provider revision hint/audit metadata permitted by the schema.

The candidate is inserted with `operational_current = FALSE`.

This registration step may not make content retrievable and may not mark another revision current.

R20 remains the sole authority to flip `operational_current` and replace the operational `sections/chunks/embeddings` inside the atomic publication transaction.

### 4.3 Why revision creation is not assigned to publisher

The staging completeness gate requires the run/revision/asset binding before publication. Making publisher invent the candidate identity would mix pre-publication provenance creation with the visibility boundary and weaken the distinction between preparing a candidate and publishing it.

Therefore:

**ingestion may create an invisible candidate revision; publisher alone may make a revision operationally current.**

## 5. Resulting trust-boundary map

```text
CANONICAL AUTHORITIES
Registry / Manifest / official URLs
        |
        v
OperationalMetadataProjector
[INGESTION IDENTITY]
        |
        +--> canonical_objects
        +--> corpus_memberships
        +--> source_assets
        +--> canonical_urls
        |
        v
P04 fingerprint / run + revision initialization
[INGESTION IDENTITY]
        |
        +--> ingestion_runs (start/lifecycle)
        +--> source_revisions candidate (current = false)
        |
        v
R19 staging
[INGESTION IDENTITY]
        |
        +--> staging_sections
        +--> staging_chunks
        +--> staging_chunk_embeddings
        |
        v
R20 gate + atomic publish
[PUBLISHER IDENTITY]
        |
        +--> operational sections/chunks/embeddings
        +--> source_revisions current flip
        +--> ingestion_runs status = PUBLISHED
        |
        v
R21 retrieval
[RETRIEVAL IDENTITY]
        |
        +--> SELECT current authorized evidence only
```

No arrow may be reversed merely for implementation convenience.

## 6. Capability assignment after these decisions

The previously frozen logical capabilities now map to concrete target trust zones:

| Capability | Target trust zone |
|---|---|
| `CAP_STAGING_WRITER` | ingestion |
| governance metadata projection capability | ingestion |
| run/revision initialization capability | ingestion |
| `CAP_PUBLISHER` | publisher |
| `CAP_RETRIEVAL_READER` | retrieval |
| `CAP_MIGRATION_ADMIN` | controlled administrative path only |

This assignment does not itself grant database privileges.

## 7. Database privilege design consequences

A future `006_r33_least_privilege.sql` may now be designed against these target NOLOGIN roles, but it must remain a code artifact until disposable PostgreSQL tests and a separate live-application authorization are complete.

At minimum, its design must prove:

### ingestion role

- only the governance projection writes explicitly required by the projector;
- run/revision initialization writes required before staging;
- R19 staging INSERT/DELETE and only necessary predicate reads;
- no operational corpus visibility-changing DML;
- no DDL.

### publisher role

- exact reads required by `assert_staging_complete` and `promote_staging_*` under SECURITY INVOKER;
- exact DML required by `AtomicPublisher`;
- no governance projection writes;
- no staging construction writes;
- no DDL.

### retrieval role

- SELECT only over the current R21 operational relations actually queried by `PostgresReadModel`;
- no staging access unless a later approved retrieval design requires it;
- no function execution unrelated to read path;
- no DML/DDL.

### function hardening

`PUBLIC EXECUTE` discovered on R33 functions is not the target policy. A tested ACL migration should revoke broad execution where safe and grant only the publisher the gate/promotion functions. The trigger helper must remain callable through trigger execution without granting unnecessary direct application invocation. This must be proven in disposable PostgreSQL before live use.

## 8. Required implementation artifacts before live ACL change

The next safe implementation sequence is now:

1. version `OperationalMetadataProjector` contract and typed DTOs/repository ports;
2. implement deterministic projection for `canonical_objects`, `corpus_memberships`, `source_assets`, `canonical_urls`;
3. implement run/revision initialization repositories with `source_revisions.operational_current = FALSE` on insert;
4. add positive/negative tests proving no free discovery, no scope widening and no visibility change;
5. draft `006_r33_least_privilege.sql` for the three target NOLOGIN roles;
6. add disposable PostgreSQL privilege tests, including denial tests and function/trigger behavior;
7. run full CI and review exact diff;
8. only then provision target application logins/secrets/service mappings in a separate controlled step;
9. obtain separate authorization before applying ACL or metadata changes to live Cloud SQL;
10. perform read-only post-deploy privilege and metadata projection audit.

## 9. Explicit non-decisions / still blocked

This document does not decide or authorize:

- whether future vector retrieval changes R21 privileges;
- how `retrieval_policy_snapshot` is persisted;
- scientific interpretation or scoring of participant responses;
- R36–R40 scientific capabilities;
- public endpoint activation;
- WordPress publication;
- migration of production traffic to new DB logins;
- retirement timing for `vinc_agent_app` / `vinc_agent_runtime`;
- live population of the canonical corpus.

Those remain separately governed.

## 10. Maintenance rule

Future maintainers should read this document before changing DB identities or metadata writers.

If a requested feature requires crossing one of the three trust zones — prepare, publish, read — the default is **not** to broaden an existing credential. First update the authority/capability contract, test the new boundary, and record why the crossing is authorized.

The architectural invariant is:

**prepare != publish != read; governance source != operational projection; technical capability != scientific authority.**
