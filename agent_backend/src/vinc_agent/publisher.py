from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class PublishSession(Protocol):
    def begin(self) -> None: ...
    def execute(self, statement: str, params: dict[str, object]) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class CachePort(Protocol):
    def invalidate_corpus(self, canonical_id: str) -> None: ...


@dataclass(frozen=True, slots=True)
class PublishRequest:
    run_id: str
    canonical_id: str
    asset_key: str
    source_revision_id: str
    validation_gate: str

    def __post_init__(self) -> None:
        if self.validation_gate != "PASS":
            raise ValueError("publication requires validation_gate=PASS")
        if not all((self.run_id, self.canonical_id, self.asset_key, self.source_revision_id)):
            raise ValueError("publish request identifiers are required")


class AtomicPublisher:
    """Sole visibility-changing adapter for corpus promotion in v0.1."""

    def __init__(self, session: PublishSession, cache: CachePort) -> None:
        self._session = session
        self._cache = cache

    def publish(self, request: PublishRequest) -> None:
        params = {
            "run_id": request.run_id,
            "canonical_id": request.canonical_id,
            "asset_key": request.asset_key,
            "source_revision_id": request.source_revision_id,
        }
        self._session.begin()
        try:
            self._session.execute(
                "SELECT assert_staging_complete(%(run_id)s, %(source_revision_id)s)",
                params,
            )
            self._session.execute(
                "DELETE FROM chunk_embeddings WHERE chunk_id IN (SELECT chunk_id FROM chunks WHERE asset_key = %(asset_key)s)",
                params,
            )
            self._session.execute(
                "DELETE FROM chunks WHERE asset_key = %(asset_key)s",
                params,
            )
            self._session.execute(
                "DELETE FROM sections WHERE asset_key = %(asset_key)s",
                params,
            )
            self._session.execute(
                """INSERT INTO sections
                   (section_id, source_revision_id, asset_key, normalized_section_locator,
                    section_ordinal, source_section_locator, heading_path)
                   SELECT section_id, source_revision_id, asset_key, normalized_section_locator,
                          section_ordinal, source_section_locator, heading_path
                   FROM promote_staging_sections(
                        %(run_id)s, %(asset_key)s, %(source_revision_id)s
                   )""",
                params,
            )
            self._session.execute(
                """INSERT INTO chunks
                   (chunk_id, section_id, source_revision_id, asset_key, canonical_id,
                    url_key, canonical_url_order, canonical_url, source_type, source_title,
                    h1, heading_path, source_section_locator, chunk_ordinal, chunk_text,
                    chunk_text_sha256, token_count, language, content_type, access_scope,
                    sensitivity, instruction_authority, domain_authority, "references",
                    source_locator, metadata, ingestion_run_id, retrieval_enabled)
                   SELECT chunk_id, section_id, source_revision_id, asset_key, canonical_id,
                          url_key, canonical_url_order, canonical_url, source_type, source_title,
                          h1, heading_path, source_section_locator, chunk_ordinal, chunk_text,
                          chunk_text_sha256, token_count, language, content_type, access_scope,
                          sensitivity, instruction_authority, domain_authority, "references",
                          source_locator, metadata, ingestion_run_id, retrieval_enabled
                   FROM promote_staging_chunks(
                        %(run_id)s, %(asset_key)s, %(canonical_id)s, %(source_revision_id)s
                   )""",
                params,
            )
            self._session.execute(
                """INSERT INTO chunk_embeddings
                   (embedding_id, chunk_id, embedding_model, dimensions, embedding_vector)
                   SELECT embedding_id, chunk_id, embedding_model, dimensions, embedding_vector
                   FROM promote_staging_embeddings(
                        %(run_id)s, %(asset_key)s, %(source_revision_id)s
                   )""",
                params,
            )
            self._session.execute(
                "UPDATE source_revisions SET operational_current = (source_revision_id = %(source_revision_id)s) WHERE asset_key = %(asset_key)s",
                params,
            )
            self._session.execute(
                "UPDATE ingestion_runs SET status = 'PUBLISHED' WHERE run_id = %(run_id)s",
                params,
            )
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise
        self._cache.invalidate_corpus(request.canonical_id)
