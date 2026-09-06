import pytest

from vinc_agent.runtime_selection import (
    AUTHORIZED_INTERNAL_BETA_RUNTIME,
    InternalBetaRuntimeSelection,
    RuntimeSelectionError,
)


def test_authorized_selection_is_fixed_and_internal():
    runtime = AUTHORIZED_INTERNAL_BETA_RUNTIME
    assert runtime.model_id == "gpt-5.6-terra"
    assert runtime.deployment_region == "southamerica-east1"
    assert runtime.public_access is False
    assert runtime.model_external_tools_allowed is False


def test_rejects_unapproved_model_substitution():
    with pytest.raises(RuntimeSelectionError):
        InternalBetaRuntimeSelection(model_id="gpt-5.6-luna")


def test_rejects_public_access_at_r30():
    with pytest.raises(RuntimeSelectionError):
        InternalBetaRuntimeSelection(public_access=True)


def test_rejects_model_tool_egress():
    with pytest.raises(RuntimeSelectionError):
        InternalBetaRuntimeSelection(model_external_tools_allowed=True)


def test_selection_hash_is_deterministic():
    assert InternalBetaRuntimeSelection().selection_hash == InternalBetaRuntimeSelection().selection_hash
