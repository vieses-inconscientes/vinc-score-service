from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol, Sequence

from .domain import Chunk, ChunkBatch


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


class StagingBuilder:
    def __init__(self, embedding: EmbeddingPort) -> None:
        self._embedding = embedding

    def build(self, batch: ChunkBatch) -> StagingBundle:
        vectors = tuple(tuple(float(v) for v in row) for row in self._embedding.embed([c.text for c in batch.chunks]))
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
