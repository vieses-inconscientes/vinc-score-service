# R33 — Staging → Operational Contract v0.1

Status: **CONTRACT_CLOSED / IMPLEMENTATION_PENDING / DO_NOT_APPLY_TO_CLOUD_SQL**

This contract closes the staging-to-operational decisions discovered during the R33 runtime preflight. It is grounded only in the canonical authorities already approved for V'inC Agent:

- `REGISTRO_CANONICO`
- `REGRAS_INGESTAO`
- `MANIFESTO_CORPUS_V0_1`
- `MATRIZ_ASSET_URL_V0_1` / `116_URLs_VINC`
- `CONTRATO_CHUNK_V0_1`
- `SCHEMA_POSTGRES_V0_1`
- `PIPELINE_INGESTAO_V0_1`
- R19 staging, R20 atomic publish, R21 read-only retrieval
- R31 public-corpus closure

This file authorizes code implementation only. It does **not** authorize applying DDL/DML to Cloud SQL, populating the operational corpus, wiring `/internal/v1/query`, opening IAM/public ingress, or changing WordPress.

## 1. Staging completeness rule

P07 is the authoritative boundary that creates complete sections/chunks. Therefore staging is not allowed to be a skeletal transport that relies on the publisher to reconstruct missing semantics later.

For every chunk that can eventually become operational, staging MUST already carry every source field needed by `CONTRATO_CHUNK_V0_1`, with provenance recorded before publish.

The publisher MUST NOT synthesize missing governance or provenance.

### Field provenance

| Operational field/group | Authoritative origin before publish |
|---|---|
| `chunk_id`, `section_id`, `source_revision_id`, `asset_key` | P04/P07 deterministic identity chain |
| `canonical_id` | exact `REGISTRO_CANONICO` binding used by the run |
| `url_key`, `canonical_url_order`, `canonical_url` | `MATRIZ_ASSET_URL_V0_1` + `116_URLs_VINC`, when applicable |
| `source_type`, `source_title` | authorized `source_asset` / Manifesto source definition |
| `h1`, `heading_path`, `source_section_locator` | P05 parser/extractor output |
| `chunk_ordinal`, `chunk_text`, `chunk_text_sha256`, `token_count`, `language`, `content_type` | P07 chunker output and deterministic validation |
| `access_scope`, `sensitivity` | exact Registry/policy snapshot used by the run |
| `instruction_authority`, `domain_authority` | `MANIFESTO_CORPUS_V0_1` / canonical governance metadata |
| `references`, `source_locator`, `metadata` | P05/P07 parser/pipeline output restricted to approved schema |
| `ingestion_run_id` | current immutable ingestion run |
| `retrieval_enabled` | policy/pipeline state revalidated by R20 publish |
| `created_at` | database-generated at successful operational promotion |
| `search_tsv` | database/index-derived from the staged source fields; never authored by the publisher |

`assert_staging_complete` must fail closed if any required field is absent, malformed, or inconsistent with the same run/revision/asset/canonical binding.

## 2. Section staging

Because operational `chunks.section_id` references `sections`, P07 staging must also contain complete section rows. A later implementation must therefore introduce `staging_sections` (or an exactly equivalent versioned structure) containing at least the operational section identity, source revision, asset binding, locator, ordinal, heading path, and run binding.

The publisher must promote sections before chunks and must replace the previous operational sections for the same asset in the same transaction that replaces chunks/embeddings.

## 3. `chunk_ordinal` is one-based end-to-end

`CONTRATO_CHUNK_V0_1` is authoritative: **chunk_ordinal is one-based end-to-end**.

The invariant is:

- chunker/P07 emits `1..N` within a section;
- staging stores exactly `1..N`;
- publisher copies the ordinal unchanged;
- operational `chunks` stores exactly the same value;
- no SQL or publisher layer may silently translate `0 → 1`.

The earlier R19 implementation/test that used zero-based ordinals is an implementation divergence and must be corrected before promotion code is allowed.

## 4. Membership projection

R31 already closes the public pair as `PUBLICO / CORPUS_PUBLICO`, and the internal policy path uses `INTERNO / CORPUS_INTERNO`.

The only valid v0.1 scope/corpus pairs are:

- **PUBLICO ↔ CORPUS_PUBLICO**
- **INTERNO ↔ CORPUS_INTERNO**

Crossed pairs are denied even when a Registry row contains both scope tokens and both corpus tokens:

- `PUBLICO / CORPUS_INTERNO` → deny
- `INTERNO / CORPUS_PUBLICO` → deny

`corpus_memberships` stores one row per valid pair present in the Registry for that `canonical_id`.

`source_assets` MUST NOT carry a singular `membership_id`. A physical asset remains unique by provider/provider_file_id and references its `canonical_id`; zero or more membership rows associate that canonical object to valid scope/corpus pairs. This avoids duplicating the same asset merely because it is authorized in more than one corpus.

## 5. Deterministic membership identity

Membership identity follows the deterministic-key rule:

```text
membership_id = "MEM_" + first24hex(
  SHA256(canonical_id + "|" + target_corpus + "|" + access_scope)
)
```

The ID depends only on the logical membership tuple. It must not depend on title, row order, provider metadata, file name, or discovery order.

## 6. Publish contract after closure

Once the enriched staging representation is implemented and tested, R20 promotion is authorized to do only the following inside one validated transaction:

1. `assert_staging_complete(run_id, source_revision_id)`;
2. remove prior operational embeddings/chunks/sections for the explicit `asset_key`;
3. promote complete staged sections;
4. promote complete staged chunks without semantic repair or enrichment;
5. promote staged embeddings when present/required by the run profile;
6. set exactly one `source_revisions.operational_current=TRUE` for the asset;
7. mark the run `PUBLISHED` only with validation gate `PASS`;
8. commit;
9. invalidate cache only after commit.

Any missing canonical/URL/policy/provenance field aborts the transaction. Historical/web/LLM fallback is forbidden.

## 7. What remains implementation work

This contract closes the prior R33 blockers for:

- incomplete staging semantics (contract now explicit);
- ordinal ambiguity (one-based);
- membership cardinality/projection (normalized through canonical_id);
- scope/corpus crossed-pair ambiguity (deny).

The following remain implementation tasks, not design decisions:

- introduce versioned enriched staging DDL (`staging_sections` + complete staging chunk fields);
- update the staging writer/DTOs to populate that contract;
- implement `assert_staging_complete`;
- implement `promote_staging_sections`;
- implement `promote_staging_chunks`;
- implement `promote_staging_embeddings`;
- test atomic replacement, rollback, completeness and pair isolation;
- run full CI and review the migration diff.

Only after those steps pass may a separate decision authorize applying the migrations to the real Cloud SQL instance.
