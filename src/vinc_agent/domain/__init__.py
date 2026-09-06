"""Pure domain contracts for V'inC Agent."""

from .errors import StableCode
from .types import (
    AssetRef,
    Chunk,
    ChunkBatch,
    FingerprintResult,
    IngestionResult,
    IngestionState,
    NormalizedDocument,
    PolicySnapshot,
    ProviderPayload,
    Section,
    ValidationGateResult,
    ValidationReport,
)

__all__ = [
    "AssetRef",
    "Chunk",
    "ChunkBatch",
    "FingerprintResult",
    "IngestionResult",
    "IngestionState",
    "NormalizedDocument",
    "PolicySnapshot",
    "ProviderPayload",
    "Section",
    "StableCode",
    "ValidationGateResult",
    "ValidationReport",
]
