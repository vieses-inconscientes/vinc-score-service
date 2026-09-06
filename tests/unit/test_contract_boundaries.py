import hashlib

import pytest

from vinc_agent.domain import AssetRef, NormalizedDocument, ProviderPayload, Section, StableCode


def test_provider_payload_matches_asset_identity_and_mime() -> None:
    asset = AssetRef(
        canonical_id="CAN-001",
        asset_key="asset-001",
        provider="gdrive",
        provider_file_id="file-123",
        source_type="html",
        expected_mime="text/html",
    )
    payload = ProviderPayload(provider_file_id="file-123", mime="text/html", content=b"<p>ok</p>")
    payload.assert_matches(asset)


def test_provider_payload_rejects_wrong_provider_id() -> None:
    asset = AssetRef("CAN-001", "asset-001", "gdrive", "file-123", "html", "text/html")
    payload = ProviderPayload(provider_file_id="file-other", mime="text/html", content=b"x")
    with pytest.raises(ValueError, match=StableCode.E_FETCH_INTEGRITY.value):
        payload.assert_matches(asset)


def test_normalized_document_rejects_content_boundary_violation() -> None:
    section = Section("s1", ("Título",), "body[1]", "conteúdo")
    with pytest.raises(ValueError, match=StableCode.E_CONTENT_BOUNDARY.value):
        NormalizedDocument(
            canonical_id="CAN-001",
            asset_key="asset-001",
            source_revision_id=hashlib.sha256(b"revision").hexdigest(),
            text="conteúdo",
            sections=(section,),
            runtime_instruction_present=True,
        )
