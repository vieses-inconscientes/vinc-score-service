from __future__ import annotations

import pytest

from vinc_agent.domain import Chunk, ChunkBatch
from vinc_agent.persistence import PostgresStagingIndexer, StagingBuilder


class FakeEmbedding:
    model_id = "fake-embedding-v0"
    dimensions = 3

    def __init__(self, *, incomplete: bool = False, wrong_dims: bool = False) -> None:
        self.incomplete = incomplete
        self.wrong_dims = wrong_dims

    def embed(self, texts):
        rows = [[float(i + 1), 0.0, 1.0] for i, _ in enumerate(texts)]
        if self.wrong_dims and rows:
            rows[0] = [1.0, 2.0]
        if self.incomplete and rows:
            rows.pop()
        return rows


class FakeSession:
    def __init__(self, fail_on_insert: bool = False) -> None:
        self.events = []
        self.fail_on_insert = fail_on_insert

    def begin(self): self.events.append(("begin", None))
    def commit(self): self.events.append(("commit", None))
    def rollback(self): self.events.append(("rollback", None))

    def execute(self, statement, params):
        self.events.append((statement, params))
        if self.fail_on_insert and statement.startswith("INSERT INTO staging_chunk_embeddings"):
            raise RuntimeError("simulated write failure")


def sample_batch() -> ChunkBatch:
    return ChunkBatch(
        chunks=(
            Chunk("c0", "asset-1", 0, "alpha", "h0"),
            Chunk("c1", "asset-1", 1, "beta", "h1"),
        )
    )


def test_staging_requires_exact_embedding_coverage():
    with pytest.raises(ValueError, match="incomplete coverage"):
        StagingBuilder(FakeEmbedding(incomplete=True)).build(sample_batch())


def test_staging_rejects_wrong_vector_dimensions():
    with pytest.raises(ValueError, match="wrong dimensions"):
        StagingBuilder(FakeEmbedding(wrong_dims=True)).build(sample_batch())


def test_staging_write_is_transactional_and_never_publishes():
    session = FakeSession()
    bundle = StagingBuilder(FakeEmbedding()).build(sample_batch())
    PostgresStagingIndexer(session).build_staging(
        bundle, run_id="00000000-0000-0000-0000-000000000019", source_revision_id="rev-19"
    )
    statements = [event[0] for event in session.events if isinstance(event[0], str)]
    assert session.events[0][0] == "begin"
    assert session.events[-1][0] == "commit"
    assert not any("active" in statement.lower() or "publish" in statement.lower() for statement in statements)


def test_staging_rolls_back_on_partial_embedding_write():
    session = FakeSession(fail_on_insert=True)
    bundle = StagingBuilder(FakeEmbedding()).build(sample_batch())
    with pytest.raises(RuntimeError):
        PostgresStagingIndexer(session).build_staging(
            bundle, run_id="00000000-0000-0000-0000-000000000019", source_revision_id="rev-19"
        )
    assert session.events[-1][0] == "rollback"
