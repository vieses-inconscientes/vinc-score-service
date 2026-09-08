from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, cast
from urllib.parse import urlsplit

from .internal_query import INTERNAL_QUERY_PATH
from .public_interface import (
    PublicAgentRequest,
    PublicAgentResponse,
    PublicCitation,
    PublicResponseStatus,
)


class GatewayBridgeError(RuntimeError):
    """Raised when the authenticated private bridge cannot be used safely."""


class OidcIdTokenProvider(Protocol):
    def fetch_id_token(self, audience: str) -> str: ...


class JsonHttpTransport(Protocol):
    def post_json(
        self,
        *,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
    ) -> tuple[int, Mapping[str, object]]: ...


@dataclass(frozen=True, slots=True)
class PrivateServiceTarget:
    base_url: str
    audience: str | None = None

    def __post_init__(self) -> None:
        parsed = urlsplit(self.base_url)
        if parsed.scheme != "https" or not parsed.netloc or parsed.query or parsed.fragment:
            raise GatewayBridgeError("private service target must be a clean HTTPS origin")
        if parsed.path not in ("", "/"):
            raise GatewayBridgeError("private service target must not include an application path")
        normalized = self.base_url.rstrip("/")
        object.__setattr__(self, "base_url", normalized)
        if self.audience is None:
            object.__setattr__(self, "audience", normalized)
        elif not self.audience.strip():
            raise GatewayBridgeError("OIDC audience is required")


class AuthenticatedInternalQueryClient:
    """Gateway-side caller for the IAM-protected internal service."""

    def __init__(
        self,
        *,
        target: PrivateServiceTarget,
        token_provider: OidcIdTokenProvider,
        transport: JsonHttpTransport,
    ) -> None:
        self._target = target
        self._token_provider = token_provider
        self._transport = transport

    def query(self, request: PublicAgentRequest) -> PublicAgentResponse:
        audience = self._target.audience
        assert audience is not None
        token = self._token_provider.fetch_id_token(audience).strip()
        if not token:
            raise GatewayBridgeError("OIDC token provider returned no token")

        status_code, payload = self._transport.post_json(
            url=f"{self._target.base_url}{INTERNAL_QUERY_PATH}",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            payload={"query_text": request.query_text},
        )
        if status_code != 200:
            raise GatewayBridgeError(f"internal service returned HTTP {status_code}")
        return self._parse_public_response(payload)

    @staticmethod
    def _parse_public_response(payload: Mapping[str, object]) -> PublicAgentResponse:
        allowed_keys = {"status", "text", "citations", "abstention_code"}
        if set(payload) != allowed_keys:
            raise GatewayBridgeError("internal response violated public projection")

        status = payload.get("status")
        text = payload.get("text")
        abstention_code = payload.get("abstention_code")
        raw_citations = payload.get("citations")
        if status not in {"answered", "abstained"} or not isinstance(text, str):
            raise GatewayBridgeError("internal response schema is invalid")
        if abstention_code is not None and not isinstance(abstention_code, str):
            raise GatewayBridgeError("internal response schema is invalid")
        if not isinstance(raw_citations, list):
            raise GatewayBridgeError("internal response schema is invalid")

        citations: list[PublicCitation] = []
        for raw in raw_citations:
            if not isinstance(raw, dict) or set(raw) != {
                "canonical_id",
                "locator",
                "canonical_url",
            }:
                raise GatewayBridgeError("internal citation schema is invalid")
            canonical_id = raw.get("canonical_id")
            locator = raw.get("locator")
            canonical_url = raw.get("canonical_url")
            if not isinstance(canonical_id, str) or not isinstance(locator, str):
                raise GatewayBridgeError("internal citation schema is invalid")
            if canonical_url is not None and not isinstance(canonical_url, str):
                raise GatewayBridgeError("internal citation schema is invalid")
            citations.append(PublicCitation(canonical_id, locator, canonical_url))

        return PublicAgentResponse(
            status=cast(PublicResponseStatus, status),
            text=text,
            citations=tuple(citations),
            abstention_code=abstention_code,
        )
