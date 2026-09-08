from __future__ import annotations

import json

import pytest

from vinc_agent.gateway_client import (
    AuthenticatedInternalQueryClient,
    GatewayBridgeError,
    PrivateServiceTarget,
)
from vinc_agent.internal_query import INTERNAL_QUERY_PATH, PrivateQueryReceiver
from vinc_agent.public_interface import (
    PUBLIC_ABSTENTION_CODE,
    PUBLIC_ABSTENTION_MESSAGE,
    PublicAgentRequest,
    PublicAgentResponse,
    PublicCitation,
)


class FakeBoundary:
    def __init__(self, response: PublicAgentResponse) -> None:
        self.response = response
        self.requests: list[PublicAgentRequest] = []

    def answer(self, request: PublicAgentRequest) -> PublicAgentResponse:
        self.requests.append(request)
        return self.response


def _answered() -> PublicAgentResponse:
    return PublicAgentResponse(
        "answered",
        "Resposta grounded",
        (
            PublicCitation(
                "VINC-CAN-001",
                "§1",
                "https://viesesinconscientes.org/",
            ),
        ),
    )


def test_private_receiver_accepts_only_query_text_and_projects_public_response() -> None:
    boundary = FakeBoundary(_answered())
    result = PrivateQueryReceiver(boundary).handle(
        method="POST",
        path=INTERNAL_QUERY_PATH,
        content_type="application/json; charset=utf-8",
        body=b'{"query_text":"O que e o VINC?"}',
    )

    payload = json.loads(result.body)
    assert result.status_code == 200
    assert boundary.requests == [PublicAgentRequest("O que e o VINC?")]
    assert set(payload) == {"status", "text", "citations", "abstention_code"}
    assert "source_revision_id" not in result.body.decode()
    assert dict(result.headers)["Cache-Control"] == "no-store"


def test_private_receiver_rejects_scope_injection_before_boundary_call() -> None:
    boundary = FakeBoundary(_answered())
    result = PrivateQueryReceiver(boundary).handle(
        method="POST",
        path=INTERNAL_QUERY_PATH,
        content_type="application/json",
        body=b'{"query_text":"q","requester_scope":"INTERNO"}',
    )

    assert result.status_code == 400
    assert boundary.requests == []


class FakeTokenProvider:
    def __init__(self) -> None:
        self.audiences: list[str] = []

    def fetch_id_token(self, audience: str) -> str:
        self.audiences.append(audience)
        return "signed-google-oidc-token"


class FakeTransport:
    def __init__(self, response: tuple[int, dict[str, object]]) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, str], dict[str, object]]] = []

    def post_json(
        self,
        *,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> tuple[int, dict[str, object]]:
        self.calls.append((url, dict(headers), dict(payload)))
        return self.response


def test_gateway_client_binds_oidc_audience_and_sends_bearer_to_private_route() -> None:
    target = PrivateServiceTarget("https://internal.example.run.app/")
    tokens = FakeTokenProvider()
    transport = FakeTransport(
        (
            200,
            {
                "status": "answered",
                "text": "Resposta grounded",
                "citations": [
                    {
                        "canonical_id": "VINC-CAN-001",
                        "locator": "§1",
                        "canonical_url": None,
                    }
                ],
                "abstention_code": None,
            },
        )
    )

    response = AuthenticatedInternalQueryClient(
        target=target,
        token_provider=tokens,
        transport=transport,
    ).query(PublicAgentRequest("q"))

    assert response.status == "answered"
    assert tokens.audiences == ["https://internal.example.run.app"]
    url, headers, payload = transport.calls[0]
    assert url == "https://internal.example.run.app/internal/v1/query"
    assert headers["Authorization"] == "Bearer signed-google-oidc-token"
    assert payload == {"query_text": "q"}


def test_gateway_client_rejects_non_https_target_and_empty_token() -> None:
    with pytest.raises(GatewayBridgeError):
        PrivateServiceTarget("http://internal.example")

    class EmptyToken:
        def fetch_id_token(self, audience: str) -> str:
            return ""

    with pytest.raises(GatewayBridgeError, match="no token"):
        AuthenticatedInternalQueryClient(
            target=PrivateServiceTarget("https://internal.example"),
            token_provider=EmptyToken(),
            transport=FakeTransport((200, {})),
        ).query(PublicAgentRequest("q"))


def test_gateway_client_rejects_internal_field_leakage() -> None:
    payload: dict[str, object] = {
        "status": "abstained",
        "text": PUBLIC_ABSTENTION_MESSAGE,
        "citations": [],
        "abstention_code": PUBLIC_ABSTENTION_CODE,
        "filter_hash": "should-never-cross-boundary",
    }

    with pytest.raises(GatewayBridgeError, match="public projection"):
        AuthenticatedInternalQueryClient(
            target=PrivateServiceTarget("https://internal.example"),
            token_provider=FakeTokenProvider(),
            transport=FakeTransport((200, payload)),
        ).query(PublicAgentRequest("q"))
