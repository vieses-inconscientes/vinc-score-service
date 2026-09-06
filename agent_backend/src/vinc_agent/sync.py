from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SyncAction(str, Enum):
    INGEST = "INGEST"
    NO_CHANGE = "NO_CHANGE"
    WITHDRAW = "WITHDRAW"
    EXCLUDE = "EXCLUDE"


@dataclass(frozen=True, slots=True)
class CanonicalSyncState:
    canonical_id: str
    status: str
    agent_index_authorized: bool
    target_corpus: str
    material_fingerprint: str | None

    def __post_init__(self) -> None:
        if not self.canonical_id.strip():
            raise ValueError("canonical_id is required")


@dataclass(frozen=True, slots=True)
class PublishedSyncState:
    canonical_id: str
    target_corpus: str
    material_fingerprint: str


@dataclass(frozen=True, slots=True)
class SyncDecision:
    canonical_id: str
    action: SyncAction
    reason: str


class IncrementalSyncPlanner:
    """R29: deterministic planner; never promotes non-canonical or unauthorized content."""

    @staticmethod
    def decide(current: CanonicalSyncState, published: PublishedSyncState | None) -> SyncDecision:
        if current.status != "CANONICO_VIGENTE" or not current.agent_index_authorized:
            if published is not None:
                return SyncDecision(current.canonical_id, SyncAction.WITHDRAW, "NO_LONGER_AUTHORIZED")
            return SyncDecision(current.canonical_id, SyncAction.EXCLUDE, "NOT_CANONICAL_AUTHORIZED")
        if not current.target_corpus or current.target_corpus == "FORA_DO_CORPUS_AGENT":
            if published is not None:
                return SyncDecision(current.canonical_id, SyncAction.WITHDRAW, "OUTSIDE_AGENT_CORPUS")
            return SyncDecision(current.canonical_id, SyncAction.EXCLUDE, "OUTSIDE_AGENT_CORPUS")
        if not current.material_fingerprint:
            raise ValueError("authorized canonical item requires material_fingerprint")
        if published is None:
            return SyncDecision(current.canonical_id, SyncAction.INGEST, "NEW_AUTHORIZED_CANONICAL")
        if published.canonical_id != current.canonical_id:
            raise ValueError("published state must match exact canonical_id")
        if published.target_corpus != current.target_corpus:
            return SyncDecision(current.canonical_id, SyncAction.INGEST, "TARGET_CORPUS_CHANGED")
        if published.material_fingerprint == current.material_fingerprint:
            return SyncDecision(current.canonical_id, SyncAction.NO_CHANGE, "MATERIAL_FINGERPRINT_UNCHANGED")
        return SyncDecision(current.canonical_id, SyncAction.INGEST, "MATERIAL_CHANGE")
