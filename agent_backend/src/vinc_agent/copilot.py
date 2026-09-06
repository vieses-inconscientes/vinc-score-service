from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from .model_adapter import GuardedModelAdapter
from .response_composer import ComposedAnswer, CompositionPolicyError, GroundedResponseComposer
from .retrieval import ReadOnlyRetrievalService, RetrievalRequest


@dataclass(frozen=True, slots=True)
class CopilotRequest:
    query_text: str
    requester_scope: str
    target_corpus: str
    top_k: int = 5
    modes: tuple[str, ...] = ("lexical",)


@dataclass(frozen=True, slots=True)
class CopilotTrace:
    query_hash: str
    filter_hash: str
    evidence_chunk_ids: tuple[str, ...]
    answer_hash: str | None
    abstention_reason: str | None


@dataclass(frozen=True, slots=True)
class CopilotResult:
    answer: ComposedAnswer
    trace: CopilotTrace


class InternalCopilot:
    """R25/R26 alpha orchestration. Retrieval stays authoritative for evidence scope."""

    def __init__(self, retrieval: ReadOnlyRetrievalService, model: GuardedModelAdapter) -> None:
        self._retrieval = retrieval
        self._model = model
        self._composer = GroundedResponseComposer()

    def answer(self, request: CopilotRequest) -> CopilotResult:
        retrieval = self._retrieval.search(
            RetrievalRequest(request.query_text, request.requester_scope, request.target_corpus, request.top_k, request.modes)
        )
        if retrieval.insufficiency_reason or not retrieval.hits:
            reason = retrieval.insufficiency_reason or "NO_AUTHORIZED_EVIDENCE"
            return self._abstained(retrieval.query_hash, retrieval.filter_hash, reason)

        provenance = {}
        try:
            for hit in retrieval.hits:
                provenance[hit.chunk_id] = self._retrieval.resolve_provenance(hit.chunk_id)
            context = self._composer.build_context(
                query_text=request.query_text,
                requester_scope=request.requester_scope,
                target_corpus=request.target_corpus,
                retrieval=retrieval,
                provenance_by_chunk=provenance,
            )
            model_response = self._model.generate(self._composer.to_model_request(context))
            answer = self._composer.compose(context=context, response=model_response, provenance_by_chunk=provenance)
        except CompositionPolicyError as exc:
            return self._abstained(retrieval.query_hash, retrieval.filter_hash, str(exc))
        answer_hash = sha256(answer.text.encode("utf-8")).hexdigest()
        return CopilotResult(answer, CopilotTrace(retrieval.query_hash, retrieval.filter_hash, tuple(p.chunk_id for p in context.evidence), answer_hash, None))

    @staticmethod
    def _abstained(query_hash: str, filter_hash: str, reason: str) -> CopilotResult:
        answer = GroundedResponseComposer.abstain(reason)
        return CopilotResult(answer, CopilotTrace(query_hash, filter_hash, (), None, reason))
