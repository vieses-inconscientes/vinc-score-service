from dataclasses import FrozenInstanceError

import pytest

from vinc_agent.domain import AssetRef, IngestionState, StableCode


def test_asset_ref_is_immutable() -> None:
    asset = AssetRef(
        canonical_id="VINC-CAN-001",
        asset_key="AST_test",
        provider="gdrive",
        provider_file_id="file-1",
        source_type="google_doc",
    )
    with pytest.raises(FrozenInstanceError):
        asset.canonical_id = "OTHER"  # type: ignore[misc]


def test_state_and_code_enums_are_closed_values() -> None:
    assert IngestionState.NO_CHANGE.value == "NO_CHANGE"
    assert StableCode.E_REGISTRY_DENY.value == "E_REGISTRY_DENY"
