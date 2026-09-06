from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol, Sequence


class RetrievalPolicyError(PermissionError):
    """Raised when retrieval is not explicitly authorized."""


class ProvenanceError(RuntimeError):
    """Raised when a hit cannot be resolved to a current canonical revision."""


@dataclass(frozen=True, slots=True)
class RetrievalRequest:
    query_text: str
    requester_scope: str
    target_corpus: str
    top_k: int = 5
    modes: tuple[str, ...] = ("lexical",)

    def __post_init__(self) -> None:
        if not self.query_text.strip():
            raise ValueError("query_text is required")
        if not self.requester_scope or not self.target_corpus:
            raise ValueError("requester_scope and target_corpus are required")
        if self.top_k < 1 or self.top_k > 50:
            raise ValueError("top_k must be between 1 and 50")
        allowed_modes = {"structured", "lexical", "vector"}
        if not self.modes or not set(self.modes).issubset(allowed_modes):
            raise ValueError("unsupported retrieval mode")


@dataclass(frozen=True, slots=True)
class CandidateFilter:
    allowed_canonical_ids: frozenset[str]
    target_corpus: str
    requester_scope: str
    policy_hash: str
    retrieval_enabled: bool = True

    @property
    def filter_hash(self) -> str:
        payload = "|".join(
            [
                self.target_corpus,
                self.requester_scope,
                self.policy_hash,
                ",".join(sorted(self.allowed_canonical_ids)),
                str(self.retrieval_enabled),
            ]
        )
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RetrievalHit:
    chunk_id: str
    canonical_id: str
    asset_key: str
    source_revision_id: str
    score: float
    text: str
    locator: str


@dataclass(frozen=True, slots=True)
class ProvenanceBundle:
    canonical_id: str
    asset_key: str
    source_revision_id: str
    locator: str
    canonical_url: str | None
    content_hash: str


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    hits: tuple[RetrievalHit, ...]
    query_hash: str
    filter_hash: str
    insufficiency_reason: str | None = None


class RetrievalPolicyPort(Protocol):
    def filter_candidate_scope(self, request: RetrievalRequest) -> CandidateFilter: ...


class RetrievalReadPort(Protocol):
    def search_authorized(
        self,
        *,
        query_text: str,
        candidate_filter: CandidateFilter,
        top_k: int,
        modes: tuple[str, ...],
    ) -> Sequence[RetrievalHit]: ...

    def resolve_current_provenance(self, chunk_id: str) -> ProvenanceBundle | None: ...


class ReadOnlyRetrievalService:
    """M11/D11 retrieval contract: policy first, then authorized read models only."""

    def __init__(self, policy: RetrievalPolicyPort, read_model: RetrievalReadPort) -> None:
        self._policy = policy
        self._read_model = read_model

    def search(self, request: RetrievalRequest) -> RetrievalResult:
        # I15 is deliberately evaluated before any lexical/vector candidate generation.
        candidate_filter = self._policy.filter_candidate_scope(request)
        if not candidate_filter.retrieval_enabled:
            raise RetrievalPolicyError("retrieval disabled by canonical policy")
        if candidate_filter.target_corpus != request.target_corpus:
            raise RetrievalPolicyError("policy corpus mismatch")
        if candidate_filter.requester_scope != request.requester_scope:
            raise RetrievalPolicyError("policy scope mismatch")
        if not candidate_filter.allowed_canonical_ids:
            return self._insufficient(request, candidate_filter, "NO_AUTHORIZED_CANDIDATES")

        raw_hits = tuple(
            self._read_model.search_authorized(
                query_text=request.query_text,
                candidate_filter=candidate_filter,
                top_k=request.top_k,
                modes=request.modes,
            )
        )
        # Defense in depth: repository is required to filter pre-search; leaked IDs still fail closed.
        if any(hit.canonical_id not in candidate_filter.allowed_canonical_ids for hit in raw_hits):
            raise RetrievalPolicyError("read model returned candidate outside canonical allowlist")

        hits = tuple(sorted(raw_hits, key=lambda h: (-h.score, h.chunk_id))[: request.top_k])
        if not hits:
            return self._insufficient(request, candidate_filter, "ZERO_AUTHORIZED_HITS")
        return RetrievalResult(
            hits=hits,
            query_hash=self._query_hash(request),
            filter_hash=candidate_filter.filter_hash,
        )

    def resolve_provenance(self, chunk_id: str) -> ProvenanceBundle:
        provenance = self._read_model.resolve_current_provenance(chunk_id)
        if provenance is None:
            raise ProvenanceError("current canonical provenance unavailable")
        if not provenance.source_revision_id or not provenance.content_hash:
            raise ProvenanceError("provenance is incomplete")
        return provenance

    @staticmethod
    def _query_hash(request: RetrievalRequest) -> str:
        payload = "|".join(
            [request.query_text.strip(), request.requester_scope, request.target_corpus, ",".join(request.modes)]
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def _insufficient(
        cls,
        request: RetrievalRequest,
        candidate_filter: CandidateFilter,
        reason: str,
    ) -> RetrievalResult:
        # Canonical contract forbids historical/web fallback for insufficiency.
        return RetrievalResult(
            hits=(),
            query_hash=cls._query_hash(request),
            filter_hash=candidate_filter.filter_hash,
            insufficiency_reason=reason,
        )
