"""Typed ports for external and cross-layer dependencies."""

from typing import Protocol, Sequence

from vinc_agent.domain.types import (
    AssetRef,
    ChunkBatch,
    FingerprintResult,
    IngestionResult,
    PolicySnapshot,
    ProviderPayload,
    ValidationReport,
)


class RegistryPort(Protocol):
    def get_asset(self, canonical_id: str, provider_file_id: str) -> AssetRef: ...


class PolicyPort(Protocol):
    def authorize_asset(self, asset: AssetRef, snapshot: PolicySnapshot) -> bool: ...


class DrivePort(Protocol):
    def fetch_exact(self, asset: AssetRef) -> ProviderPayload: ...


class FingerprintPort(Protocol):
    def compute(self, payload: ProviderPayload, profile: str) -> FingerprintResult: ...


class ExtractorPort(Protocol):
    def extract(self, payload: ProviderPayload, profile: str) -> object: ...


class ValidatorPort(Protocol):
    def validate(self, stage_payload: object, gate_set: Sequence[str]) -> ValidationReport: ...


class ChunkerPort(Protocol):
    def build_chunks(self, normalized_document: object, profile: str) -> ChunkBatch: ...


class IndexerPort(Protocol):
    def build_staging_index(self, chunks: ChunkBatch, config: object) -> object: ...


class PublisherPort(Protocol):
    def atomic_publish(self, request: object) -> object: ...


class AuditPort(Protocol):
    def finalize_run(self, result: IngestionResult) -> object: ...
