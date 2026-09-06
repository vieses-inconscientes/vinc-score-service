from vinc_agent.application.pipeline import InMemoryIngestionPipeline, PipelinePorts
from vinc_agent.domain import AssetRef, IngestionState, PolicySnapshot, ProviderPayload, StableCode
from vinc_agent.infra.memory import (
    AllowPolicy,
    DeterministicChunker,
    MemoryAudit,
    MemoryDrive,
    MemoryIndexer,
    MemoryPublisher,
    MemoryRegistry,
    PassValidator,
    PlainTextExtractor,
    Sha256Fingerprint,
)


def build_fixture() -> tuple[AssetRef, ProviderPayload, PipelinePorts, MemoryIndexer, MemoryPublisher, MemoryAudit]:
    asset = AssetRef("CAN-001", "asset-001", "gdrive", "file-001", "text", "text/plain")
    payload = ProviderPayload("file-001", "text/plain", b"conteudo canonico de teste")
    indexer = MemoryIndexer()
    publisher = MemoryPublisher()
    audit = MemoryAudit()
    ports = PipelinePorts(
        registry=MemoryRegistry({("CAN-001", "file-001"): asset}),
        policy=AllowPolicy(),
        drive=MemoryDrive({"file-001": payload}),
        fingerprint=Sha256Fingerprint(),
        extractor=PlainTextExtractor(),
        validator=PassValidator(),
        chunker=DeterministicChunker(),
        indexer=indexer,
        publisher=publisher,
        audit=audit,
    )
    return asset, payload, ports, indexer, publisher, audit


def test_pipeline_runs_without_network_or_database() -> None:
    _, _, ports, indexer, publisher, audit = build_fixture()
    policy = PolicySnapshot("pol-001", "0" * 64, "corpus-test", frozenset({"asset-001"}), "public")

    result = InMemoryIngestionPipeline(ports).run(
        canonical_id="CAN-001",
        provider_file_id="file-001",
        policy_snapshot=policy,
    )

    assert result.state is IngestionState.AUDITED
    assert len(indexer.staged) == 1
    assert len(publisher.publications) == 1
    assert audit.results[-1].state is IngestionState.PUBLISHED


def test_pipeline_short_circuits_on_material_no_change() -> None:
    _, payload, ports, indexer, publisher, audit = build_fixture()
    material = Sha256Fingerprint().compute(payload, "sha256-v1").material_fingerprint
    policy = PolicySnapshot("pol-002", material, "corpus-test", frozenset({"asset-001"}), "public")

    result = InMemoryIngestionPipeline(ports).run(
        canonical_id="CAN-001",
        provider_file_id="file-001",
        policy_snapshot=policy,
    )

    assert result.state is IngestionState.NO_CHANGE
    assert result.code is StableCode.N_NO_CHANGE
    assert not indexer.staged
    assert not publisher.publications
    assert audit.results[-1].state is IngestionState.NO_CHANGE
