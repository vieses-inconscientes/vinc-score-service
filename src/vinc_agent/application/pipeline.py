"""Deterministic P01-P10 ingestion orchestration with no network or database assumptions."""

from dataclasses import dataclass
from uuid import uuid4

from vinc_agent.application.ports import (
    AuditPort,
    ChunkerPort,
    DrivePort,
    ExtractorPort,
    FingerprintPort,
    IndexerPort,
    PolicyPort,
    PublisherPort,
    RegistryPort,
    ValidatorPort,
)
from vinc_agent.domain import IngestionResult, IngestionState, PolicySnapshot, StableCode


@dataclass(slots=True)
class PipelinePorts:
    registry: RegistryPort
    policy: PolicyPort
    drive: DrivePort
    fingerprint: FingerprintPort
    extractor: ExtractorPort
    validator: ValidatorPort
    chunker: ChunkerPort
    indexer: IndexerPort
    publisher: PublisherPort
    audit: AuditPort


class InMemoryIngestionPipeline:
    def __init__(self, ports: PipelinePorts) -> None:
        self.ports = ports

    def run(
        self,
        *,
        canonical_id: str,
        provider_file_id: str,
        policy_snapshot: PolicySnapshot,
        extraction_profile: str = "default",
        fingerprint_profile: str = "sha256-v1",
        chunk_profile: str = "default",
    ) -> IngestionResult:
        run_id = str(uuid4())

        asset = self.ports.registry.get_asset(canonical_id, provider_file_id)
        if not self.ports.policy.authorize_asset(asset, policy_snapshot):
            result = IngestionResult(run_id, IngestionState.FAILED_AUTHORIZATION, StableCode.E_ACCESS_POLICY)
            self.ports.audit.finalize_run(result)
            return result

        payload = self.ports.drive.fetch_exact(asset)
        payload.assert_matches(asset)

        fingerprint = self.ports.fingerprint.compute(payload, fingerprint_profile)
        if fingerprint.material_fingerprint == policy_snapshot.policy_hash:
            result = IngestionResult(run_id, IngestionState.NO_CHANGE, StableCode.N_NO_CHANGE)
            self.ports.audit.finalize_run(result)
            return result

        normalized = self.ports.extractor.extract(asset, payload, extraction_profile)
        extraction_report = self.ports.validator.validate(normalized, ("content-boundary", "extraction-complete"))
        if extraction_report.blocker_count:
            result = IngestionResult(run_id, IngestionState.FAILED_VALIDATION, StableCode.E_CONTENT_BOUNDARY)
            self.ports.audit.finalize_run(result)
            return result

        chunks = self.ports.chunker.build_chunks(normalized, chunk_profile)
        chunk_report = self.ports.validator.validate(chunks, ("chunk-contract",))
        if chunk_report.blocker_count:
            result = IngestionResult(run_id, IngestionState.FAILED_CHUNKING, StableCode.E_CHUNK_CONTRACT)
            self.ports.audit.finalize_run(result)
            return result

        staging = self.ports.indexer.build_staging_index(chunks, {"mode": "in-memory"})
        publication = self.ports.publisher.atomic_publish(staging)
        result = IngestionResult(
            run_id=run_id,
            state=IngestionState.PUBLISHED,
            details={
                "asset_key": asset.asset_key,
                "source_revision_id": chunks.source_revision_id,
                "publication": str(publication),
            },
        )
        self.ports.audit.finalize_run(result)
        return IngestionResult(
            run_id=run_id,
            state=IngestionState.AUDITED,
            details=result.details,
        )
