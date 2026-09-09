from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .retrieval import (
    CandidateFilter,
    ProvenanceBundle,
    RetrievalHit,
    RetrievalPolicyError,
)


class PostgresReadModel:
    """Concrete read-only R21 adapter over the operational PostgreSQL projection.

    The adapter deliberately supports lexical retrieval only in this R33 wiring step.
    Scope/corpus authorization stays upstream in CanonicalPolicyAdapter; the exact
    canonical-id allowlist is applied in SQL before ranking, and current provenance
    is enforced through source_revisions.operational_current.
    """

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect

    def search_authorized(
        self,
        *,
        query_text: str,
        candidate_filter: CandidateFilter,
        top_k: int,
        modes: tuple[str, ...],
    ) -> tuple[RetrievalHit, ...]:
        if modes != ("lexical",):
            raise RetrievalPolicyError("postgres read model only authorizes lexical mode in R33")
        if not candidate_filter.retrieval_enabled:
            raise RetrievalPolicyError("retrieval disabled by canonical policy")
        if not candidate_filter.allowed_canonical_ids:
            return ()

        params = {
            "query_text": query_text.strip(),
            "allowed_ids": sorted(candidate_filter.allowed_canonical_ids),
            "top_k": top_k,
        }
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(_LEXICAL_SEARCH_SQL, params)
                rows = tuple(cursor.fetchall())

        return tuple(
            RetrievalHit(
                chunk_id=str(row[0]),
                canonical_id=str(row[1]),
                asset_key=str(row[2]),
                source_revision_id=str(row[3]),
                score=float(row[4]),
                text=str(row[5]),
                locator=str(row[6]),
            )
            for row in rows
        )

    def resolve_current_provenance(self, chunk_id: str) -> ProvenanceBundle | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(_CURRENT_PROVENANCE_SQL, {"chunk_id": chunk_id})
                row = cursor.fetchone()

        if row is None:
            return None
        return ProvenanceBundle(
            canonical_id=str(row[0]),
            asset_key=str(row[1]),
            source_revision_id=str(row[2]),
            locator=str(row[3]),
            canonical_url=None if row[4] is None else str(row[4]),
            content_hash=str(row[5]),
        )


_LEXICAL_SEARCH_SQL = """
SELECT
    c.chunk_id,
    c.canonical_id,
    c.asset_key,
    c.source_revision_id,
    ts_rank_cd(
        c.search_tsv,
        plainto_tsquery('portuguese'::regconfig, %(query_text)s)
    )::float8 AS score,
    c.chunk_text,
    COALESCE(c.source_section_locator, c.source_locator::text) AS locator
FROM chunks AS c
JOIN source_assets AS sa
  ON sa.asset_key = c.asset_key
 AND sa.canonical_id = c.canonical_id
JOIN source_revisions AS sr
  ON sr.source_revision_id = c.source_revision_id
 AND sr.asset_key = c.asset_key
 AND sr.operational_current = TRUE
JOIN canonical_objects AS co
  ON co.canonical_id = c.canonical_id
 AND co.canonical_status = 'CANONICO_VIGENTE'
 AND co.agent_index_authorized = TRUE
WHERE c.retrieval_enabled = TRUE
  AND c.canonical_id = ANY(%(allowed_ids)s)
  AND c.search_tsv @@ plainto_tsquery('portuguese'::regconfig, %(query_text)s)
ORDER BY score DESC, c.chunk_id ASC
LIMIT %(top_k)s
""".strip()


_CURRENT_PROVENANCE_SQL = """
SELECT
    c.canonical_id,
    c.asset_key,
    c.source_revision_id,
    COALESCE(c.source_section_locator, c.source_locator::text) AS locator,
    c.canonical_url,
    c.chunk_text_sha256
FROM chunks AS c
JOIN source_assets AS sa
  ON sa.asset_key = c.asset_key
 AND sa.canonical_id = c.canonical_id
JOIN source_revisions AS sr
  ON sr.source_revision_id = c.source_revision_id
 AND sr.asset_key = c.asset_key
 AND sr.operational_current = TRUE
JOIN canonical_objects AS co
  ON co.canonical_id = c.canonical_id
 AND co.canonical_status = 'CANONICO_VIGENTE'
 AND co.agent_index_authorized = TRUE
WHERE c.chunk_id = %(chunk_id)s
  AND c.retrieval_enabled = TRUE
""".strip()
