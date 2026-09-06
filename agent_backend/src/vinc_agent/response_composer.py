from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Mapping

from .model_adapter import EvidenceExcerpt, ModelRequest, ModelResponse
from .retrieval import ProvenanceBundle, RetrievalResult


class CompositionPolicyError(PermissionError):
    """Raised when a grounded Copilot response cannot be composed safely."""


@dataclass(frozen=True, slots=True)
class GroundedContext:
    query_text: str
    requester_scope: str
    target_corpus: str
    evidence: tuple[EvidenceExcerpt, ...]
    retrieval_query_hash: str
    retrieval_filter_hash: str

    @property
    def context_hash(self) -> str:
        payload = "|".join(
            [
                self.query_text.strip(),
                self.requester_scope,
                self.target_corpus,
                self.retrieval_query_hash,
                self.retrieval_filter_hash,
                *(e.content_hash for e in self.evidence),
            ]
        )
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Citation:
    chunk_id: str
    canonical_id: str
    source_revision_id: str
    locator: str
    canonical_url: str | None
    content_hash: str


@dataclass(frozen=True, slots=True)
class ComposedAnswer:
    text: str
    citations: tuple[Citation, ...]
    grounded_context_hash: str
    abstained: bool = False
    insufficiency_reason: str | None = None


class GroundedResponseComposer:
    """R24: close the model context over current canonical retrieval evidence only."""

    def build_context(
        self,
        *,
        query_text: str,
        requester_scope: str,
        target_corpus: str,
        retrieval: RetrievalResult,
        provenance_by_chunk: Mapping[str, ProvenanceBundle],
    ) -> GroundedContext:
        if retrieval.insufficiency_reason or not retrieval.hits:
            raise CompositionPolicyError(retrieval.insufficiency_reason or "NO_AUTHORIZED_EVIDENCE")
        evidence: list[EvidenceExcerpt] = []
        for hit in retrieval.hits:
            provenance = provenance_by_chunk.get(hit.chunk_id)
            if provenance is None:
                raise CompositionPolicyError("PROVENANCE_MISSING")
            if (
                provenance.canonical_id != hit.canonical_id
                or provenance.asset_key != hit.asset_key
                or provenance.source_revision_id != hit.source_revision_id
                or provenance.locator != hit.locator
            ):
                raise CompositionPolicyError("PROVENANCE_MISMATCH")
            evidence.append(
                EvidenceExcerpt(
                    chunk_id=hit.chunk_id,
                    canonical_id=hit.canonical_id,
                    source_revision_id=hit.source_revision_id,
                    locator=hit.locator,
                    text=hit.text,
                    content_hash=provenance.content_hash,
                )
            )
        return GroundedContext(
            query_text=query_text,
            requester_scope=requester_scope,
            target_corpus=target_corpus,
            evidence=tuple(evidence),
            retrieval_query_hash=retrieval.query_hash,
            retrieval_filter_hash=retrieval.filter_hash,
        )

    @staticmethod
    def to_model_request(context: GroundedContext) -> ModelRequest:
        return ModelRequest(
            user_query=context.query_text,
            requester_scope=context.requester_scope,
            target_corpus=context.target_corpus,
            evidence=context.evidence,
        )

    def compose(
        self,
        *,
        context: GroundedContext,
        response: ModelResponse,
        provenance_by_chunk: Mapping[str, ProvenanceBundle],
    ) -> ComposedAnswer:
        evidence_ids = {e.chunk_id for e in context.evidence}
        if not response.cited_chunk_ids or any(cid not in evidence_ids for cid in response.cited_chunk_ids):
            raise CompositionPolicyError("CITATION_OUTSIDE_GROUNDED_CONTEXT")
        citations = []
        for chunk_id in response.cited_chunk_ids:
            p = provenance_by_chunk.get(chunk_id)
            if p is None:
                raise CompositionPolicyError("CITATION_PROVENANCE_MISSING")
            citations.append(Citation(chunk_id, p.canonical_id, p.source_revision_id, p.locator, p.canonical_url, p.content_hash))
        return ComposedAnswer(response.text, tuple(citations), context.context_hash)

    @staticmethod
    def abstain(reason: str) -> ComposedAnswer:
        if not reason:
            raise ValueError("abstention reason is required")
        return ComposedAnswer("", (), "", abstained=True, insufficiency_reason=reason)
