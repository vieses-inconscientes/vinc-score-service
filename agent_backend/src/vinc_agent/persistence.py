from __future__ import annotations

import json
import re
from dataclasses import dataclass
from hashlib import sha256
from typing import Mapping, Protocol, Sequence

from .domain import Chunk, ChunkBatch


_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_TYPES = frozenset({"GOOGLE_DOC", "HTML", "SHEET_STRUCTURED"})
_CONTENT_TYPES = frozenset({"institutional", "editorial", "technical", "reference"})
_INSTRUCTION_AUTHORITIES = frozenset({"NONE", "RAG_REFERENCE_ONLY"})


class EmbeddingPort(Protocol):
    @property
    def model_id(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class PersistenceSession(Protocol):
    def begin(self) -> None: ...
    def execute(self, statement: str, params: dict[str, object]) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


@dataclass(frozen=True, slots=True)
class EmbeddingRecord:
    embedding_id: str
    chunk_id: str
    model_id: str
    dimensions: int
    vector: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class StagingBundle:
    """Legacy R19 skeletal staging bundle.

    This remains only to preserve the already-tested R19 contract. It is not
    promotion-compatible with the R33 staging-to-operational contract.
    """

    batch: ChunkBatch
    embeddings: tuple[EmbeddingRecord, ...]

    def __post_init__(self) -> None:
        chunk_ids = tuple(chunk.chunk_id for chunk in self.batch.chunks)
        embedded_ids = tuple(item.chunk_id for item in self.embeddings)
        if chunk_ids != embedded_ids:
            raise ValueError("embedding coverage must exactly match chunk order")
        if len(set(chunk_ids)) != len(chunk_ids):
            raise ValueError("chunk ids must be unique")
        if not self.embeddings:
            raise ValueError("staging requires embeddings")
        model_dims = {(item.model_id, item.dimensions) for item in self.embeddings}
        if len(model_dims) != 1:
            raise ValueError("one embedding model/dimension set is required per staging bundle")
        for item in self.embeddings:
            if len(item.vector) != item.dimensions:
                raise ValueError("embedding vector dimension mismatch")


@dataclass(frozen=True, slots=True)
class StagingSectionRecord:
    section_id: str
    source_revision_id: str
    asset_key: str
    normalized_section_locator: str
    section_ordinal: int
    source_section_locator: str | None = None
    heading_path: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        required = (
            self.section_id,
            self.source_revision_id,
            self.asset_key,
            self.normalized_section_locator,
        )
        if any(not value.strip() for value in required):
            raise ValueError("staging section identity/provenance fields are required")
        if self.section_ordinal < 1:
            raise ValueError("section_ordinal must be one-based")
        if any(not part.strip() for part in self.heading_path):
            raise ValueError("heading_path cannot contain blank entries")


@dataclass(frozen=True, slots=True)
class StagingChunkRecord:
    chunk_id: str
    section_id: str
    source_revision_id: str
    asset_key: str
    canonical_id: str
    source_type: str
    source_title: str
    chunk_ordinal: int
    chunk_text: str
    chunk_text_sha256: str
    token_count: int
    language: str
    content_type: str
    access_scope: str
    sensitivity: str
    instruction_authority: str
    domain_authority: str
    source_locator: Mapping[str, object]
    url_key: str | None = None
    canonical_url_order: int | None = None
    canonical_url: str | None = None
    h1: str | None = None
    heading_path: tuple[str, ...] = ()
    source_section_locator: str | None = None
    references: object | None = None
    metadata: Mapping[str, object] | None = None
    retrieval_enabled: bool = True

    def __post_init__(self) -> None:
        required = (
            self.chunk_id,
            self.section_id,
            self.source_revision_id,
            self.asset_key,
            self.canonical_id,
            self.source_type,
            self.source_title,
            self.chunk_text,
            self.chunk_text_sha256,
            self.language,
            self.content_type,
            self.access_scope,
            self.sensitivity,
            self.instruction_authority,
            self.domain_authority,
        )
        if any(not value.strip() for value in required):
            raise ValueError("staging chunk required fields cannot be blank")
        if self.chunk_ordinal < 1:
            raise ValueError("chunk_ordinal must be one-based")
        if self.token_count < 1:
            raise ValueError("token_count must be positive")
        if self.source_type not in _SOURCE_TYPES:
            raise ValueError("unsupported source_type")
        if self.content_type not in _CONTENT_TYPES:
            raise ValueError("unsupported content_type")
        if self.instruction_authority not in _INSTRUCTION_AUTHORITIES:
            raise ValueError("unsupported instruction_authority")
        if not _SHA256_RE.fullmatch(self.chunk_text_sha256):
            raise ValueError("chunk_text_sha256 must be lowercase SHA-256")
        actual_hash = sha256(self.chunk_text.encode("utf-8")).hexdigest()
        if actual_hash != self.chunk_text_sha256:
            raise ValueError("chunk_text_sha256 does not match chunk_text")
        if not self.source_locator:
            raise ValueError("source_locator is required")
        if any(not part.strip() for part in self.heading_path):
            raise ValueError("heading_path cannot contain blank entries")

        url_values = (self.url_key, self.canonical_url_order, self.canonical_url)
        supplied = tuple(value is not None for value in url_values)
        if any(supplied) and not all(supplied):
            raise ValueError("URL provenance must be complete or absent")
        if self.canonical_url_order is not None and not 1 <= self.canonical_url_order <= 116:
            raise ValueError("canonical_url_order must be between 1 and 116")
        if self.canonical_url is not None and not self.canonical_url.startswith("https://"):
            raise ValueError("canonical_url must be absolute HTTPS")

        _json_text(self.source_locator)
        if self.references is not None:
            _json_text(self.references)
        if self.metadata is not None:
            _json_text(self.metadata)


@dataclass(frozen=True, slots=True)
class EnrichedStagingBundle:
    sections: tuple[StagingSectionRecord, ...]
    chunks: tuple[StagingChunkRecord, ...]
    embeddings: tuple[EmbeddingRecord, ...] = ()

    def __post_init__(self) -> None:
        if not self.sections:
            raise ValueError("enriched staging requires sections")
        if not self.chunks:
            raise ValueError("enriched staging requires chunks")

        section_ids = tuple(section.section_id for section in self.sections)
        chunk_ids = tuple(chunk.chunk_id for chunk in self.chunks)
        if len(set(section_ids)) != len(section_ids):
            raise ValueError("section ids must be unique")
        if len(set(chunk_ids)) != len(chunk_ids):
            raise ValueError("chunk ids must be unique")

        sections_by_id = {section.section_id: section for section in self.sections}
        revision_asset_pairs = {
            (section.source_revision_id, section.asset_key) for section in self.sections
        }
        if len(revision_asset_pairs) != 1:
            raise ValueError("one source revision/asset binding is required per enriched bundle")

        ordinals_by_section: dict[str, list[int]] = {}
        canonical_ids: set[str] = set()
        for chunk in self.chunks:
            section = sections_by_id.get(chunk.section_id)
            if section is None:
                raise ValueError("every staged chunk must reference a staged section")
            if (chunk.source_revision_id, chunk.asset_key) != (
                section.source_revision_id,
                section.asset_key,
            ):
                raise ValueError("chunk section/revision/asset binding mismatch")
            ordinals_by_section.setdefault(chunk.section_id, []).append(chunk.chunk_ordinal)
            canonical_ids.add(chunk.canonical_id)

        if len(canonical_ids) != 1:
            raise ValueError("one canonical_id is required per enriched bundle")
        for ordinals in ordinals_by_section.values():
            if sorted(ordinals) != list(range(1, len(ordinals) + 1)):
                raise ValueError("chunk ordinals must be contiguous and one-based per section")

        if self.embeddings:
            embedded_ids = tuple(item.chunk_id for item in self.embeddings)
            if len(set(embedded_ids)) != len(embedded_ids):
                raise ValueError("embedding chunk ids must be unique")
            if set(embedded_ids) != set(chunk_ids):
                raise ValueError("embedding coverage must exactly match staged chunks")
            model_dims = {(item.model_id, item.dimensions) for item in self.embeddings}
            if len(model_dims) != 1:
                raise ValueError("one embedding model/dimension set is required per enriched bundle")
            for item in self.embeddings:
                if len(item.vector) != item.dimensions:
                    raise ValueError("embedding vector dimension mismatch")


def _json_text(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class StagingBuilder:
    def __init__(self, embedding: EmbeddingPort) -> None:
        self._embedding = embedding

    def build(self, batch: ChunkBatch) -> StagingBundle:
        vectors = tuple(
            tuple(float(v) for v in row)
            for row in self._embedding.embed([c.text for c in batch.chunks])
        )
        if len(vectors) != len(batch.chunks):
            raise ValueError("embedding provider returned incomplete coverage")
        records: list[EmbeddingRecord] = []
        for chunk, vector in zip(batch.chunks, vectors, strict=True):
            if len(vector) != self._embedding.dimensions:
                raise ValueError("embedding provider returned wrong dimensions")
            raw_id = f"{chunk.chunk_id}|{self._embedding.model_id}|{self._embedding.dimensions}"
            records.append(
                EmbeddingRecord(
                    embedding_id="emb_" + sha256(raw_id.encode("utf-8")).hexdigest()[:24],
                    chunk_id=chunk.chunk_id,
                    model_id=self._embedding.model_id,
                    dimensions=self._embedding.dimensions,
                    vector=vector,
                )
            )
        return StagingBundle(batch=batch, embeddings=tuple(records))


class PostgresStagingIndexer:
    """Writes only to staging. It has no API for promoting corpus visibility."""

    def __init__(self, session: PersistenceSession) -> None:
        self._session = session

    def build_staging(self, bundle: StagingBundle, *, run_id: str, source_revision_id: str) -> None:
        """Legacy R19 writer; retained for compatibility, not for R33 promotion."""
        if not run_id or not source_revision_id:
            raise ValueError("run_id and source_revision_id are required")
        self._session.begin()
        try:
            self._session.execute(
                "DELETE FROM staging_chunk_embeddings WHERE ingestion_run_id = %(run_id)s",
                {"run_id": run_id},
            )
            self._session.execute(
                "DELETE FROM staging_chunks WHERE ingestion_run_id = %(run_id)s",
                {"run_id": run_id},
            )
            for chunk in bundle.batch.chunks:
                self._insert_chunk(chunk, run_id=run_id, source_revision_id=source_revision_id)
            for embedding in bundle.embeddings:
                self._insert_embedding(embedding, run_id=run_id)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    def build_enriched_staging(self, bundle: EnrichedStagingBundle, *, run_id: str) -> None:
        """Write a complete R33 promotion-compatible staging representation.

        This method still has no ability to alter operational visibility.
        """
        if not run_id:
            raise ValueError("run_id is required")
        self._session.begin()
        try:
            self._session.execute(
                "DELETE FROM staging_chunk_embeddings WHERE ingestion_run_id = %(run_id)s",
                {"run_id": run_id},
            )
            self._session.execute(
                "DELETE FROM staging_chunks WHERE ingestion_run_id = %(run_id)s",
                {"run_id": run_id},
            )
            self._session.execute(
                "DELETE FROM staging_sections WHERE ingestion_run_id = %(run_id)s",
                {"run_id": run_id},
            )
            for section in bundle.sections:
                self._insert_enriched_section(section, run_id=run_id)
            for chunk in bundle.chunks:
                self._insert_enriched_chunk(chunk, run_id=run_id)
            for embedding in bundle.embeddings:
                self._insert_embedding(embedding, run_id=run_id)
            self._session.commit()
        except Exception:
            self._session.rollback()
            raise

    def _insert_chunk(self, chunk: Chunk, *, run_id: str, source_revision_id: str) -> None:
        self._session.execute(
            """INSERT INTO staging_chunks
               (chunk_id, source_revision_id, source_asset_id, chunk_ordinal, chunk_text, content_hash, ingestion_run_id)
               VALUES (%(chunk_id)s, %(source_revision_id)s, %(source_asset_id)s, %(ordinal)s, %(text)s, %(content_hash)s, %(run_id)s)""",
            {
                "chunk_id": chunk.chunk_id,
                "source_revision_id": source_revision_id,
                "source_asset_id": chunk.source_asset_id,
                "ordinal": chunk.ordinal,
                "text": chunk.text,
                "content_hash": chunk.content_hash,
                "run_id": run_id,
            },
        )

    def _insert_enriched_section(self, item: StagingSectionRecord, *, run_id: str) -> None:
        self._session.execute(
            """INSERT INTO staging_sections
               (section_id, source_revision_id, asset_key, normalized_section_locator,
                section_ordinal, source_section_locator, heading_path, ingestion_run_id)
               VALUES
               (%(section_id)s, %(source_revision_id)s, %(asset_key)s, %(normalized_section_locator)s,
                %(section_ordinal)s, %(source_section_locator)s, %(heading_path)s, %(run_id)s)""",
            {
                "section_id": item.section_id,
                "source_revision_id": item.source_revision_id,
                "asset_key": item.asset_key,
                "normalized_section_locator": item.normalized_section_locator,
                "section_ordinal": item.section_ordinal,
                "source_section_locator": item.source_section_locator,
                "heading_path": list(item.heading_path),
                "run_id": run_id,
            },
        )

    def _insert_enriched_chunk(self, item: StagingChunkRecord, *, run_id: str) -> None:
        self._session.execute(
            """INSERT INTO staging_chunks
               (chunk_id, source_revision_id, source_asset_id, chunk_ordinal, chunk_text, content_hash,
                ingestion_run_id, section_id, asset_key, canonical_id, url_key, canonical_url_order,
                canonical_url, source_type, source_title, h1, heading_path, source_section_locator,
                chunk_text_sha256, token_count, language, content_type, access_scope, sensitivity,
                instruction_authority, domain_authority, "references", source_locator, metadata,
                retrieval_enabled)
               VALUES
               (%(chunk_id)s, %(source_revision_id)s, %(asset_key)s, %(chunk_ordinal)s, %(chunk_text)s,
                %(chunk_text_sha256)s, %(run_id)s, %(section_id)s, %(asset_key)s, %(canonical_id)s,
                %(url_key)s, %(canonical_url_order)s, %(canonical_url)s, %(source_type)s,
                %(source_title)s, %(h1)s, %(heading_path)s, %(source_section_locator)s,
                %(chunk_text_sha256)s, %(token_count)s, %(language)s, %(content_type)s,
                %(access_scope)s, %(sensitivity)s, %(instruction_authority)s, %(domain_authority)s,
                CAST(%(references)s AS jsonb), CAST(%(source_locator)s AS jsonb),
                CAST(%(metadata)s AS jsonb), %(retrieval_enabled)s)""",
            {
                "chunk_id": item.chunk_id,
                "source_revision_id": item.source_revision_id,
                "asset_key": item.asset_key,
                "chunk_ordinal": item.chunk_ordinal,
                "chunk_text": item.chunk_text,
                "chunk_text_sha256": item.chunk_text_sha256,
                "run_id": run_id,
                "section_id": item.section_id,
                "canonical_id": item.canonical_id,
                "url_key": item.url_key,
                "canonical_url_order": item.canonical_url_order,
                "canonical_url": item.canonical_url,
                "source_type": item.source_type,
                "source_title": item.source_title,
                "h1": item.h1,
                "heading_path": list(item.heading_path),
                "source_section_locator": item.source_section_locator,
                "token_count": item.token_count,
                "language": item.language,
                "content_type": item.content_type,
                "access_scope": item.access_scope,
                "sensitivity": item.sensitivity,
                "instruction_authority": item.instruction_authority,
                "domain_authority": item.domain_authority,
                "references": None if item.references is None else _json_text(item.references),
                "source_locator": _json_text(item.source_locator),
                "metadata": None if item.metadata is None else _json_text(item.metadata),
                "retrieval_enabled": item.retrieval_enabled,
            },
        )

    def _insert_embedding(self, item: EmbeddingRecord, *, run_id: str) -> None:
        self._session.execute(
            """INSERT INTO staging_chunk_embeddings
               (embedding_id, chunk_id, embedding_model, dimensions, embedding_vector, ingestion_run_id)
               VALUES (%(embedding_id)s, %(chunk_id)s, %(model_id)s, %(dimensions)s, %(vector)s, %(run_id)s)""",
            {
                "embedding_id": item.embedding_id,
                "chunk_id": item.chunk_id,
                "model_id": item.model_id,
                "dimensions": item.dimensions,
                "vector": list(item.vector),
                "run_id": run_id,
            },
        )
