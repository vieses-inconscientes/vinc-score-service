from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256


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


class StableCode(StrEnum):
    E_REGISTRY_DENY = "E_REGISTRY_DENY"
    E_ASSET_NOT_ALLOWLISTED = "E_ASSET_NOT_ALLOWLISTED"
    E_FETCH_INTEGRITY = "E_FETCH_INTEGRITY"
    E_FINGERPRINT_INVALID = "E_FINGERPRINT_INVALID"
    E_EXTRACTION_INCOMPLETE = "E_EXTRACTION_INCOMPLETE"
    E_CONTENT_BOUNDARY = "E_CONTENT_BOUNDARY"
    E_CHUNK_CONTRACT = "E_CHUNK_CONTRACT"
    E_ACCESS_POLICY = "E_ACCESS_POLICY"
    E_POST_PUBLISH_SMOKE = "E_POST_PUBLISH_SMOKE"
    E_PROVENANCE_BROKEN = "E_PROVENANCE_BROKEN"
    N_NO_CHANGE = "N_NO_CHANGE"


@dataclass(frozen=True, slots=True)
class AssetRef:
    canonical_object_id: str
    source_asset_id: str
    provider: str = "gdrive"

    def __post_init__(self) -> None:
        if not self.canonical_object_id or not self.source_asset_id:
            raise ValueError("canonical_object_id and source_asset_id are required")
        if self.provider != "gdrive":
            raise ValueError("provider must be gdrive in v0.1")


@dataclass(frozen=True, slots=True)
class PolicySnapshot:
    policy_hash: str
    allowed_asset_ids: frozenset[str]
    requester_scope: str | None = None
    target_corpus: str | None = None

    def __post_init__(self) -> None:
        if bool(self.requester_scope) != bool(self.target_corpus):
            raise ValueError("requester_scope and target_corpus must be bound together")

    @property
    def is_scope_bound(self) -> bool:
        return self.requester_scope is not None and self.target_corpus is not None

    def allows(self, asset: AssetRef) -> bool:
        return asset.source_asset_id in self.allowed_asset_ids


@dataclass(frozen=True, slots=True)
class ProviderPayload:
    source_asset_id: str
    content: bytes

    def __post_init__(self) -> None:
        if not self.content:
            raise ValueError("provider payload cannot be empty")


@dataclass(frozen=True, slots=True)
class FingerprintResult:
    sha256_hex: str
    material_changed: bool

    @classmethod
    def from_bytes(cls, content: bytes, previous_sha256: str | None = None) -> "FingerprintResult":
        digest = sha256(content).hexdigest()
        return cls(digest, digest != previous_sha256)


@dataclass(frozen=True, slots=True)
class NormalizedDocument:
    source_asset_id: str
    title: str
    text: str

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("normalized document text cannot be empty")


@dataclass(frozen=True, slots=True)
class ValidationReport:
    blocker_codes: tuple[str, ...] = ()

    @property
    def can_advance(self) -> bool:
        return not self.blocker_codes


@dataclass(frozen=True, slots=True)
class Chunk:
    chunk_id: str
    source_asset_id: str
    ordinal: int
    text: str
    content_hash: str


@dataclass(frozen=True, slots=True)
class ChunkBatch:
    chunks: tuple[Chunk, ...]

    def __post_init__(self) -> None:
        if not self.chunks:
            raise ValueError("chunk batch cannot be empty")
        if tuple(c.ordinal for c in self.chunks) != tuple(range(1, len(self.chunks) + 1)):
            raise ValueError("chunk ordinals must be contiguous and one-based")


@dataclass(frozen=True, slots=True)
class IngestionResult:
    state: IngestionState
    code: str | None = None
