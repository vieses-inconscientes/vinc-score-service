from vinc_agent import (
    AssetRef,
    Chunk,
    ChunkBatch,
    FingerprintResult,
    IngestionState,
    NormalizedDocument,
    PolicySnapshot,
    ProviderPayload,
    ValidationReport,
)


def test_asset_and_policy_contracts() -> None:
    asset = AssetRef("OBJ-001", "ASSET-001")
    policy = PolicySnapshot("policy-sha", frozenset({"ASSET-001"}))
    assert policy.allows(asset)


def test_payload_fingerprint_is_deterministic() -> None:
    payload = ProviderPayload("ASSET-001", b"canonical")
    first = FingerprintResult.from_bytes(payload.content)
    second = FingerprintResult.from_bytes(payload.content, first.sha256_hex)
    assert len(first.sha256_hex) == 64
    assert second.material_changed is False


def test_document_validation_and_chunk_contracts() -> None:
    doc = NormalizedDocument("ASSET-001", "Title", "Canonical text")
    report = ValidationReport()
    chunk = Chunk("CH-001", doc.source_asset_id, 0, doc.text, "hash")
    batch = ChunkBatch((chunk,))
    assert report.can_advance
    assert batch.chunks[0].ordinal == 0
    assert IngestionState.AUDITED.value == "AUDITED"
