from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CopilotMetricEvent:
    outcome: str
    query_hash: str
    filter_hash: str
    evidence_count: int
    answer_hash: str | None
    abstention_reason: str | None


class CopilotMetrics:
    """R28: derive non-sensitive observability events from Copilot traces only."""

    @staticmethod
    def from_trace(trace, *, abstained: bool) -> CopilotMetricEvent:
        outcome = "ABSTAINED" if abstained else "ANSWERED"
        if not trace.query_hash or not trace.filter_hash:
            raise ValueError("trace hashes are required")
        if abstained and not trace.abstention_reason:
            raise ValueError("abstention reason is required for abstained outcome")
        if not abstained and trace.answer_hash is None:
            raise ValueError("answer hash is required for answered outcome")
        return CopilotMetricEvent(
            outcome=outcome,
            query_hash=trace.query_hash,
            filter_hash=trace.filter_hash,
            evidence_count=len(trace.evidence_chunk_ids),
            answer_hash=trace.answer_hash,
            abstention_reason=trace.abstention_reason,
        )
