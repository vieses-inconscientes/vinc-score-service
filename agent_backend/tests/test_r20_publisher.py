from __future__ import annotations

import pytest

from vinc_agent.publisher import AtomicPublisher, PublishRequest


class FakeSession:
    def __init__(self, fail_at: str | None = None) -> None:
        self.events = []
        self.fail_at = fail_at

    def begin(self): self.events.append(("begin", None))
    def commit(self): self.events.append(("commit", None))
    def rollback(self): self.events.append(("rollback", None))

    def execute(self, statement, params):
        self.events.append((statement, params))
        if self.fail_at and self.fail_at in statement:
            raise RuntimeError("simulated publish failure")


class FakeCache:
    def __init__(self) -> None:
        self.invalidated = []

    def invalidate_corpus(self, canonical_id):
        self.invalidated.append(canonical_id)


def request() -> PublishRequest:
    return PublishRequest(
        run_id="00000000-0000-0000-0000-000000000020",
        canonical_id="VINC-CAN-001",
        asset_key="asset-001",
        source_revision_id="rev-current",
        validation_gate="PASS",
    )


def test_publish_requires_pass_gate():
    with pytest.raises(ValueError, match="validation_gate=PASS"):
        PublishRequest("r", "c", "a", "rev", "WARN")


def test_publish_changes_visibility_inside_one_transaction_then_invalidates_cache():
    session = FakeSession()
    cache = FakeCache()
    AtomicPublisher(session, cache).publish(request())
    assert session.events[0][0] == "begin"
    assert session.events[-1][0] == "commit"
    assert cache.invalidated == ["VINC-CAN-001"]


def test_publish_rolls_back_and_does_not_invalidate_cache_on_partial_failure():
    session = FakeSession(fail_at="promote_staging_embeddings")
    cache = FakeCache()
    with pytest.raises(RuntimeError):
        AtomicPublisher(session, cache).publish(request())
    assert session.events[-1][0] == "rollback"
    assert cache.invalidated == []


def test_only_requested_asset_is_replaced():
    session = FakeSession()
    cache = FakeCache()
    AtomicPublisher(session, cache).publish(request())
    params = [p for s, p in session.events if isinstance(p, dict)]
    assert any(p.get("asset_key") == "asset-001" for p in params)
    assert all(p.get("asset_key", "asset-001") == "asset-001" for p in params)
