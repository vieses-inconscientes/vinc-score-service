from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Protocol


class ModelPolicyError(PermissionError):
    """Raised when a model call would violate the Copilot boundary."""


@dataclass(frozen=True, slots=True)
class EvidenceExcerpt:
    chunk_id: str
    canonical_id: str
    source_revision_id: str
    locator: str
    text: str
    content_hash: str

    def __post_init__(self) -> None:
        required = (
            self.chunk_id,
            self.canonical_id,
            self.source_revision_id,
            self.locator,
            self.text,
            self.content_hash,
        )
        if any(not value.strip() for value in required):
            raise ValueError("evidence excerpt fields must be non-empty")


@dataclass(frozen=True, slots=True)
class ModelRequest:
    user_query: str
    requester_scope: str
    target_corpus: str
    evidence: tuple[EvidenceExcerpt, ...]
    instruction_profile: str = "COPILOT_GROUNDED_V0_1"

    def __post_init__(self) -> None:
        if not self.user_query.strip():
            raise ValueError("user_query is required")
        if not self.requester_scope or not self.target_corpus:
            raise ValueError("requester_scope and target_corpus are required")
        if not self.evidence:
            raise ModelPolicyError("generative call requires canonical evidence")

    @property
    def evidence_hash(self) -> str:
        payload = "\n".join(
            "|".join(
                [
                    e.chunk_id,
                    e.canonical_id,
                    e.source_revision_id,
                    e.locator,
                    e.content_hash,
                    e.text,
                ]
            )
            for e in self.evidence
        )
        return sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class ModelResponse:
    text: str
    cited_chunk_ids: tuple[str, ...]
    provider: str
    model: str
    request_hash: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("model response text is required")
        if not self.provider or not self.model or not self.request_hash:
            raise ValueError("provider, model and request_hash are required")


class GenerativeModelPort(Protocol):
    """Substitutable model boundary for the Copilot layer only."""

    def generate(self, request: ModelRequest) -> ModelResponse: ...


class GuardedModelAdapter:
    """Guard generation after retrieval without granting governance authority.

    The adapter cannot choose sources, widen scopes, retrieve content, or infer
    canonicity. It only receives an already-authorized evidence bundle and delegates
    text generation to a provider port.
    """

    def __init__(self, provider: GenerativeModelPort) -> None:
        self._provider = provider

    def generate(self, request: ModelRequest) -> ModelResponse:
        allowed_chunks = {item.chunk_id for item in request.evidence}
        response = self._provider.generate(request)
        if not response.cited_chunk_ids:
            raise ModelPolicyError("grounded response must cite at least one evidence chunk")
        if any(chunk_id not in allowed_chunks for chunk_id in response.cited_chunk_ids):
            raise ModelPolicyError("model cited evidence outside authorized bundle")
        expected_hash = self._request_hash(request)
        if response.request_hash != expected_hash:
            raise ModelPolicyError("provider response is not bound to the current request")
        return response

    @staticmethod
    def _request_hash(request: ModelRequest) -> str:
        payload = "|".join(
            [
                request.user_query.strip(),
                request.requester_scope,
                request.target_corpus,
                request.instruction_profile,
                request.evidence_hash,
            ]
        )
        return sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def bind_request_hash(cls, request: ModelRequest) -> str:
        """Deterministic helper for provider adapters and contract tests."""
        return cls._request_hash(request)
