from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Protocol

from .public_interface import (
    PublicAgentRequest,
    PublicAgentResponse,
    PublicInterfacePolicyError,
)

INTERNAL_QUERY_PATH = "/internal/v1/query"
JSON_CONTENT_TYPE = "application/json"


class PrivateQueryProtocolError(ValueError):
    """Raised when the private bridge contract is violated before reaching the boundary."""


class PublicBoundaryPort(Protocol):
    def answer(self, request: PublicAgentRequest) -> PublicAgentResponse: ...


@dataclass(frozen=True, slots=True)
class PrivateQueryHttpResponse:
    status_code: int
    body: bytes
    headers: tuple[tuple[str, str], ...]


def _json_response(status_code: int, payload: dict[str, object]) -> PrivateQueryHttpResponse:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return PrivateQueryHttpResponse(
        status_code=status_code,
        body=body,
        headers=(
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
            ("Cache-Control", "no-store"),
        ),
    )


def _serialize_public_response(response: PublicAgentResponse) -> dict[str, object]:
    return {
        "status": response.status,
        "text": response.text,
        "citations": [
            {
                "canonical_id": citation.canonical_id,
                "locator": citation.locator,
                "canonical_url": citation.canonical_url,
            }
            for citation in response.citations
        ],
        "abstention_code": response.abstention_code,
    }


class PrivateQueryReceiver:
    """R33 receiver contract; Cloud Run IAM must authenticate callers before this code runs."""

    def __init__(self, boundary: PublicBoundaryPort) -> None:
        self._boundary = boundary

    def handle(
        self,
        *,
        method: str,
        path: str,
        content_type: str,
        body: bytes,
    ) -> PrivateQueryHttpResponse:
        if path != INTERNAL_QUERY_PATH:
            return _json_response(404, {"status": "not_found"})
        if method.upper() != "POST":
            return _json_response(405, {"status": "method_not_allowed"})
        media_type = content_type.split(";", 1)[0].strip().lower()
        if media_type != JSON_CONTENT_TYPE:
            return _json_response(415, {"status": "unsupported_media_type"})

        try:
            decoded = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return _json_response(400, {"status": "invalid_request"})

        if not isinstance(decoded, dict) or set(decoded) != {"query_text"}:
            return _json_response(400, {"status": "invalid_request"})
        query_text = decoded.get("query_text")
        if not isinstance(query_text, str) or not query_text.strip():
            return _json_response(400, {"status": "invalid_request"})

        try:
            response = self._boundary.answer(PublicAgentRequest(query_text))
        except (ValueError, PublicInterfacePolicyError):
            return _json_response(500, {"status": "internal_error"})
        return _json_response(200, _serialize_public_response(response))
