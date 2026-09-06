"""Immutable domain data structures for backend v0.1."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Mapping, Sequence

from .errors import StableCode


class IngestionState(StrEnum):
    REQUESTED = "REQUESTED"
    DISCOVERED = "DISCOVERED"
    AUTHORIZED = "AUTHORIZED"
    FETCHED = "FETCHED"
    FINGERPRINTED = "FINGERPRINTED"
    NO_CHANGE = "NO_CHANGE"
    EXTRACTED = "EXTRACTED"
    VALIDATED = "VALIDATED"
    CHUNKED = "CHUNKED"
    INDEXED_STAGING = "INDEXED_STAGING"
    PUBLISHED = "PUBLISHED"
    AUDITED = "AUDITED"
    FAILED_DISCOVERY = "FAILED_DISCOVERY"
    FAILED_AUTHORIZATION = "FAILED_AUTHORIZATION"
    FAILED_FETCH = "FAILED_FETCH"
    FAILED_FINGERPRINT = "FAILED_FINGERPRINT"
    FAILED_EXTRACTION = "FAILED_EXTRACTION"
    FAILED_VALIDATION = "FAILED_VALIDATION"
    FAILED_CHUNKING = "FAILED_CHUNKING"
    FAILED_INDEXING = "FAILED_INDEXING"
    FAILED_PUBLISH = "FAILED_PUBLISH"
    FAILED_AUDIT = "FAILED_AUDIT"
    RESTORE_REQUIRED = "RESTORE_REQUIRED"
    RESTORED_AUDITED = "RESTORED_AUDITED"


@dataclass(frozen=True, slots=True)
class AssetRef:
    canonical_id: str
    asset_key: str
    provider: str
    provider_file_id: str
    source_type: str
    expected_mime: str | None = None


@dataclass(frozen=True, slots=True)
class PolicySnapshot:
    policy_snapshot_id: str
    policy_hash: str
    target_corpus: str
    allowed_scopes: frozenset[str]
    sensitivity_ceiling: str


@dataclass(frozen=True, slots=True)
class ProviderPayload:
    provider_file_id: str
    mime: str
    content: bytes
    provider_revision_hint: str | None = None
    metadata: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FingerprintResult:
    raw_sha256: str
    normalized_sha256: str
    material_fingerprint: str
    provider_revision_hint: str | None
    algorithm_version: str


@dataclass(frozen=True, slots=True)
class Section:
    section_id: str
    heading_path: tuple[str, ...]
    source_locator: str
    text: str


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_id: str
    section_id: str
    source_revision_id: str
    asset_key: str
    canonical_id: str
    chunk_ordinal: int
    chunk_text: str
    chunk_text_sha256: str
    token_count: int
    access_scope: str
    sensitivity: str
    instruction_authority: str
    source_locator: str


@dataclass(frozen=True, slots=True)
class ChunkBatch:
    source_revision_id: str
    sections: Sequence[Section]
    chunks: Sequence[Chunk]
    batch_hash: str


@dataclass(frozen=True, slots=True)
class ValidationGateResult:
    gate_id: str
    passed: bool
    blocker: bool
    evidence_hash: str | None = None
    message: str | None = None


@dataclass(frozen=True, slots=True)
class ValidationReport:
    ruleset_version: str
    gate_results: Sequence[ValidationGateResult]
    report_hash: str

    @property
    def blocker_count(self) -> int:
        return sum(1 for result in self.gate_results if result.blocker and not result.passed)


@dataclass(frozen=True, slots=True)
class IngestionResult:
    run_id: str
    state: IngestionState
    code: StableCode | None = None
    details: Mapping[str, str] = field(default_factory=dict)
