from __future__ import annotations

from typing import Protocol

from .domain import AssetRef, ChunkBatch, NormalizedDocument, PolicySnapshot, ProviderPayload, ValidationReport


class RegistryPort(Protocol):
    def load_asset(self, canonical_object_id: str) -> AssetRef: ...


class PolicyPort(Protocol):
    def snapshot(self) -> PolicySnapshot: ...

    def authorize_asset(self, asset: AssetRef, snapshot: PolicySnapshot) -> bool: ...


class ProviderPort(Protocol):
    def fetch_exact(self, asset: AssetRef) -> ProviderPayload: ...


class ExtractorPort(Protocol):
    def extract(self, payload: ProviderPayload) -> NormalizedDocument: ...


class ValidatorPort(Protocol):
    def validate(self, document: NormalizedDocument) -> ValidationReport: ...


class ChunkerPort(Protocol):
    def build_chunks(self, document: NormalizedDocument) -> ChunkBatch: ...


class IndexerPort(Protocol):
    def build_staging_index(self, batch: ChunkBatch) -> None: ...


class PublisherPort(Protocol):
    def atomic_publish(self, batch: ChunkBatch) -> None: ...


class AuditPort(Protocol):
    def record(self, event: str, detail: str) -> None: ...
