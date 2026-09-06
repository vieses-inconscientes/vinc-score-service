from __future__ import annotations

import pytest

from vinc_agent.retrieval import (
    CandidateFilter,
    ProvenanceBundle,
    ProvenanceError,
    ReadOnlyRetrievalService,
    RetrievalHit,
    RetrievalPolicyError,
    RetrievalRequest,
)


class FakePolicy:
    def __init__(self, candidate_filter: CandidateFilter) -> None:
        self.filter = candidate_filter
        self.calls = 0

    def filter_candidate_scope(self, request: RetrievalRequest) -> CandidateFilter:
        self.calls += 1
        return self.filter


class FakeReadModel:
    def __init__(self, hits=(), provenance=None) -> None:
        self.hits = tuple(hits)
        self.provenance = provenance
        self.search_calls = 0
        self.last_filter = None

    def search_authorized(self, *, query_text, candidate_filter, top_k, modes):
        self.search_calls += 1
        self.last_filter = candidate_filter
        return self.hits

    def resolve_current_provenance(self, chunk_id: str):
        return self.provenance


def request() -> RetrievalRequest:
    return RetrievalRequest("carta fundacional", "PUBLIC", "AGENT_CORE", top_k=3)


def filt(ids=frozenset({"VINC-CAN-001"}), enabled=True) -> CandidateFilter:
    return CandidateFilter(ids, "AGENT_CORE", "PUBLIC", "policy-v1", enabled)


def hit(canonical_id="VINC-CAN-001", score=0.9) -> RetrievalHit:
    return RetrievalHit("CHK_001", canonical_id, "asset-001", "rev-current", score, "texto", "p:1")


def test_policy_runs_before_candidate_generation_and_filter_is_passed_to_repository():
    policy = FakePolicy(filt())
    repo = FakeReadModel([hit()])
    service = ReadOnlyRetrievalService(policy, repo)

    result = service.search(request())

    assert policy.calls == 1
    assert repo.search_calls == 1
    assert repo.last_filter == policy.filter
    assert result.hits[0].canonical_id == "VINC-CAN-001"


def test_empty_allowlist_returns_insufficiency_without_search_or_fallback():
    policy = FakePolicy(filt(frozenset()))
    repo = FakeReadModel([hit()])
    service = ReadOnlyRetrievalService(policy, repo)

    result = service.search(request())

    assert result.hits == ()
    assert result.insufficiency_reason == "NO_AUTHORIZED_CANDIDATES"
    assert repo.search_calls == 0


def test_disabled_retrieval_fails_closed_before_repository_read():
    policy = FakePolicy(filt(enabled=False))
    repo = FakeReadModel()
    service = ReadOnlyRetrievalService(policy, repo)

    with pytest.raises(RetrievalPolicyError):
        service.search(request())
    assert repo.search_calls == 0


def test_repository_leak_outside_allowlist_is_rejected():
    policy = FakePolicy(filt())
    repo = FakeReadModel([hit("VINC-CAN-008")])
    service = ReadOnlyRetrievalService(policy, repo)

    with pytest.raises(RetrievalPolicyError):
        service.search(request())


def test_zero_authorized_hits_is_insufficient_not_external_fallback():
    service = ReadOnlyRetrievalService(FakePolicy(filt()), FakeReadModel([]))

    result = service.search(request())

    assert result.hits == ()
    assert result.insufficiency_reason == "ZERO_AUTHORIZED_HITS"


def test_provenance_requires_current_complete_bundle():
    current = ProvenanceBundle(
        "VINC-CAN-001", "asset-001", "rev-current", "p:1", "https://example.invalid/canonical", "abc123"
    )
    service = ReadOnlyRetrievalService(FakePolicy(filt()), FakeReadModel(provenance=current))
    assert service.resolve_provenance("CHK_001") == current

    broken = ReadOnlyRetrievalService(FakePolicy(filt()), FakeReadModel(provenance=None))
    with pytest.raises(ProvenanceError):
        broken.resolve_provenance("CHK_OLD")
