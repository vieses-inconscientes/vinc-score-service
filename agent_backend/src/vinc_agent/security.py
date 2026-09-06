from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from .model_adapter import ModelRequest, ModelResponse


@dataclass(frozen=True, slots=True)
class RedactedSecurityRecord:
    request_hash: str
    query_hash: str
    evidence_hash: str
    response_hash: str
    provider: str
    model: str
    cited_chunk_ids: tuple[str, ...]


class CopilotSecurityAudit:
    """Create an audit-safe proof without persisting raw query/evidence/answer text."""

    @staticmethod
    def from_exchange(request: ModelRequest, response: ModelResponse) -> RedactedSecurityRecord:
        return RedactedSecurityRecord(
            request_hash=response.request_hash,
            query_hash=sha256(request.user_query.strip().encode("utf-8")).hexdigest(),
            evidence_hash=request.evidence_hash,
            response_hash=sha256(response.text.encode("utf-8")).hexdigest(),
            provider=response.provider,
            model=response.model,
            cited_chunk_ids=response.cited_chunk_ids,
        )
