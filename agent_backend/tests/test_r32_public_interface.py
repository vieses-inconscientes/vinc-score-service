from __future__ import annotations

from dataclasses import fields

import pytest

from vinc_agent.copilot import CopilotRequest, CopilotResult, CopilotTrace
from vinc_agent.public_interface import (
    PUBLIC_ABSTENTION_CODE,
    PUBLIC_ABSTENTION_MESSAGE,
    PUBLIC_MODES,
    PUBLIC_REQUESTER_SCOPE,
    PUBLIC_TARGET_CORPUS,
    PUBLIC_TOP_K,
    PublicAgentBoundary,
    PublicAgentRequest,
    PublicAgentResponse,
    PublicCitation,
    PublicInterfacePolicyError,
)
from vinc_agent.response_composer import Citation, ComposedAnswer


class FakeCopilot:
    def __init__(self, result: CopilotResult) -> None:
        self.result = result
        self.requests: list[CopilotRequest] = []

    def answer(self, request: CopilotRequest) -> CopilotResult:
        self.requests.append(request)
        return self.result


def _trace(reason: str | None = None) -> CopilotTrace:
    return CopilotTrace("query-hash", "filter-hash", ("CHK-1",), "answer-hash", reason)


def _answered_result() -> CopilotResult:
    citation = Citation(
        "CHK-1",
        "VINC-CAN-001",
        "rev-internal",
        "§1",
        "https://example.org",
        "internal-content-hash",
    )
    answer = ComposedAnswer("Resposta grounded", (citation,), "internal-context-hash")
    return CopilotResult(answer, _trace())


def test_public_request_exposes_only_query_text() -> None:
    assert [field.name for field in fields(PublicAgentRequest)] == ["query_text"]
    with pytest.raises(ValueError):
        PublicAgentRequest("   ")


def test_boundary_injects_public_scope_corpus_and_fixed_retrieval_config() -> None:
    fake = FakeCopilot(_answered_result())
    response = PublicAgentBoundary(fake).answer(PublicAgentRequest("  O que é o V'inC?  "))
    assert response.status == "answered"
    assert fake.requests == [
        CopilotRequest(
            "O que é o V'inC?",
            PUBLIC_REQUESTER_SCOPE,
            PUBLIC_TARGET_CORPUS,
            PUBLIC_TOP_K,
            PUBLIC_MODES,
        )
    ]


def test_public_response_projects_only_safe_fields() -> None:
    response = PublicAgentBoundary(FakeCopilot(_answered_result())).answer(PublicAgentRequest("q"))
    assert [field.name for field in fields(PublicAgentResponse)] == [
        "status",
        "text",
        "citations",
        "abstention_code",
    ]
    assert [field.name for field in fields(PublicCitation)] == [
        "canonical_id",
        "locator",
        "canonical_url",
    ]
    assert response.citations == (
        PublicCitation("VINC-CAN-001", "§1", "https://example.org"),
    )


def test_abstention_is_generic_and_does_not_leak_internal_reason() -> None:
    answer = ComposedAnswer("", (), "", True, "PROVENANCE_MISMATCH:secret")
    response = PublicAgentBoundary(FakeCopilot(CopilotResult(answer, _trace("secret")))).answer(
        PublicAgentRequest("q")
    )
    assert response.status == "abstained"
    assert response.text == PUBLIC_ABSTENTION_MESSAGE
    assert response.abstention_code == PUBLIC_ABSTENTION_CODE
    assert "PROVENANCE" not in response.text
    assert "secret" not in response.text


def test_ungrounded_answer_fails_closed() -> None:
    answer = ComposedAnswer("texto sem citação", (), "ctx")
    with pytest.raises(PublicInterfacePolicyError, match="PUBLIC_ANSWER_NOT_GROUNDED"):
        PublicAgentBoundary(FakeCopilot(CopilotResult(answer, _trace()))).answer(
            PublicAgentRequest("q")
        )
