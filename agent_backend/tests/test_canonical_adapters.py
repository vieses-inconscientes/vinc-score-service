from vinc_agent.canonical_adapters import CanonicalPolicyAdapter, CanonicalRegistryAdapter
from vinc_agent.external_contracts import AllowlistedRegistryReader, RegistryConfig


ROWS = [
    {
        "canonical_id": "VINC-CAN-001",
        "canonical_status": "CANONICO_VIGENTE",
        "drive_file_id": "DOC-CARTA",
        "agent_index_authorized": "TRUE",
        "agent_access_scope": "TRUE",
        "ingestion_mode": "FULL_TEXT",
        "target_corpus": "CORPUS_PUBLICO|CORPUS_INTERNO",
    },
    {
        "canonical_id": "VINC-CAN-005",
        "canonical_status": "CANONICO_VIGENTE",
        "drive_file_id": "SHEET-RESP",
        "agent_index_authorized": "TRUE",
        "agent_access_scope": "FALSE",
        "ingestion_mode": "NONE",
        "target_corpus": "FORA_DO_CORPUS_AGENT",
    },
    {
        "canonical_id": "VINC-CAN-008",
        "canonical_status": "CANONICO_VIGENTE",
        "drive_file_id": "DOC-HIST",
        "agent_index_authorized": "TRUE",
        "agent_access_scope": "FALSE",
        "ingestion_mode": "NONE",
        "target_corpus": "FORA_DO_CORPUS_AGENT",
    },
]


class SnapshotSheets:
    def read_rows(self, spreadsheet_id: str, tab: str):
        assert spreadsheet_id == "REGISTRY-ID"
        assert tab == "REGISTRO_CANONICO"
        return ROWS


def adapters():
    bounded = AllowlistedRegistryReader(
        SnapshotSheets(),
        RegistryConfig("REGISTRY-ID", frozenset({"REGISTRO_CANONICO"})),
    )
    registry = CanonicalRegistryAdapter(bounded)
    return registry, CanonicalPolicyAdapter(registry)


def test_authorizes_only_explicit_agent_corpus():
    registry, policy = adapters()
    asset = registry.load_asset("VINC-CAN-001")
    snapshot = policy.snapshot()
    assert policy.authorize_asset(asset, snapshot)
    assert snapshot.allowed_asset_ids == frozenset({"DOC-CARTA"})


def test_restricted_research_data_is_not_promoted_by_canonicity():
    registry, policy = adapters()
    asset = registry.load_asset("VINC-CAN-005")
    assert not policy.authorize_asset(asset, policy.snapshot())


def test_historical_canonical_document_remains_outside_agent():
    registry, policy = adapters()
    asset = registry.load_asset("VINC-CAN-008")
    assert not policy.authorize_asset(asset, policy.snapshot())


def test_no_title_or_similarity_fallback():
    registry, _ = adapters()
    try:
        registry.load_asset("Carta Fundacional")
    except RuntimeError as exc:
        assert str(exc) == "E_REGISTRY_DENY"
    else:
        raise AssertionError("lookup must require exact canonical_id")
