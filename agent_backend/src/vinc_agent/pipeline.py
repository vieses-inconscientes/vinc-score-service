from __future__ import annotations

from dataclasses import dataclass

from .domain import FingerprintResult, IngestionResult, IngestionState
from .ports import AuditPort, ChunkerPort, ExtractorPort, IndexerPort, PolicyPort, ProviderPort, PublisherPort, RegistryPort, ValidatorPort


@dataclass(slots=True)
class InMemoryIngestionPipeline:
    registry: RegistryPort
    policy: PolicyPort
    provider: ProviderPort
    extractor: ExtractorPort
    validator: ValidatorPort
    chunker: ChunkerPort
    indexer: IndexerPort
    publisher: PublisherPort
    audit: AuditPort

    def run(self, canonical_object_id: str, previous_sha256: str | None = None) -> IngestionResult:
        asset = self.registry.load_asset(canonical_object_id)
        snapshot = self.policy.snapshot()
        if not self.policy.authorize_asset(asset, snapshot):
            return IngestionResult(IngestionState.AUTHORIZED, "E_ACCESS_POLICY")
        payload = self.provider.fetch_exact(asset)
        if payload.source_asset_id != asset.source_asset_id:
            return IngestionResult(IngestionState.FETCHED, "E_FETCH_INTEGRITY")
        fp = FingerprintResult.from_bytes(payload.content, previous_sha256)
        if not fp.material_changed:
            self.audit.record("NO_CHANGE", asset.source_asset_id)
            return IngestionResult(IngestionState.NO_CHANGE, "N_NO_CHANGE")
        document = self.extractor.extract(payload)
        report = self.validator.validate(document)
        if not report.can_advance:
            return IngestionResult(IngestionState.VALIDATED, report.blocker_codes[0])
        batch = self.chunker.build_chunks(document)
        self.indexer.build_staging_index(batch)
        self.publisher.atomic_publish(batch)
        self.audit.record("PUBLISHED", asset.source_asset_id)
        return IngestionResult(IngestionState.AUDITED)
