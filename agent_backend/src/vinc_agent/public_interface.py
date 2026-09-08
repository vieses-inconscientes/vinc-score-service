from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from .copilot import CopilotRequest, CopilotResult


PUBLIC_REQUESTER_SCOPE = "PUBLICO"
PUBLIC_TARGET_CORPUS = "CORPUS_PUBLICO"
PUBLIC_TOP_K = 5
PUBLIC_MODES = ("lexical",)
PUBLIC_ABSTENTION_CODE = "INSUFFICIENT_CANONICAL_PUBLIC_EVIDENCE"
PUBLIC_ABSTENTION_MESSAGE = "Não há evidência canônica pública suficiente para responder."


class PublicInterfacePolicyError(PermissionError):
    """Raised when an internal result cannot be projected safely to the public boundary."""


class CopilotPort(Protocol):
    def answer(self, request: CopilotRequest) -> CopilotResult: ...


@dataclass(frozen=True, slots=True)
class PublicAgentRequest:
    query_text: str

    def __post_init__(self) -> None:
        if not self.query_text.strip():
            raise ValueError("query_text is required")


@dataclass(frozen=True, slots=True)
class PublicCitation:
    canonical_id: str
    locator: str
    canonical_url: str | None

    def __post_init__(self) -> None:
        if not self.canonical_id.strip() or not self.locator.strip():
            raise PublicInterfacePolicyError("PUBLIC_CITATION_INCOMPLETE")


PublicResponseStatus = Literal["answered", "abstained"]


@dataclass(frozen=True, slots=True)
class PublicAgentResponse:
    status: PublicResponseStatus
    text: str
    citations: tuple[PublicCitation, ...]
    abstention_code: str | None = None

    def __post_init__(self) -> None:
        if self.status == "answered":
            if not self.text.strip() or not self.citations or self.abstention_code is not None:
                raise PublicInterfacePolicyError("PUBLIC_ANSWER_NOT_GROUNDED")
        elif self.status == "abstained":
            if self.citations or self.abstention_code != PUBLIC_ABSTENTION_CODE:
                raise PublicInterfacePolicyError("PUBLIC_ABSTENTION_INVALID")


class PublicAgentBoundary:
    """R32 application boundary for the future public Agent; no HTTP surface is opened here."""

    def __init__(self, copilot: CopilotPort) -> None:
        self._copilot = copilot

    def answer(self, request: PublicAgentRequest) -> PublicAgentResponse:
        internal_request = CopilotRequest(
            query_text=request.query_text.strip(),
            requester_scope=PUBLIC_REQUESTER_SCOPE,
            target_corpus=PUBLIC_TARGET_CORPUS,
            top_k=PUBLIC_TOP_K,
            modes=PUBLIC_MODES,
        )
        result = self._copilot.answer(internal_request)
        answer = result.answer
        if answer.abstained:
            return PublicAgentResponse(
                status="abstained",
                text=PUBLIC_ABSTENTION_MESSAGE,
                citations=(),
                abstention_code=PUBLIC_ABSTENTION_CODE,
            )
        if not answer.text.strip() or not answer.citations:
            raise PublicInterfacePolicyError("PUBLIC_ANSWER_NOT_GROUNDED")
        citations = tuple(
            PublicCitation(
                canonical_id=citation.canonical_id,
                locator=citation.locator,
                canonical_url=citation.canonical_url,
            )
            for citation in answer.citations
        )
        return PublicAgentResponse(
            status="answered",
            text=answer.text.strip(),
            citations=citations,
        )
