from vinc_agent.canonical_adapters import CanonicalPolicyAdapter, CanonicalRegistryAdapter
from vinc_agent.external_contracts import AllowlistedRegistryReader, RegistryConfig
from vinc_agent.retrieval import RetrievalRequest


ROWS = [
    {"canonical_id": "VINC-CAN-001", "canonical_status": "CANONICO_VIGENTE", "drive_file_id": "DOC-CARTA", "agent_index_authorized": "TRUE", "agent_access_scope": "PUBLICO|INTERNO", "sensitivity": "PUBLICO", "ingestion_mode": "FULL_TEXT", "target_corpus": "CORPUS_PUBLICO|CORPUS_INTERNO"},
    {"canonical_id": "VINC-CAN-002", "canonical_status": "CANONICO_VIGENTE", "drive_file_id": "SHEET-URLS", "agent_index_authorized": "TRUE", "agent_access_scope": "INTERNO", "sensitivity": "INTERNO", "ingestion_mode": "STRUCTURED_TABLE", "target_corpus": "CORPUS_INTERNO"},
    {"canonical_id": "VINC-CAN-003", "canonical_status": "CANONICO_VIGENTE", "drive_file_id": "SHEET-GLOSSARIO", "agent_index_authorized": "TRUE", "agent_access_scope": "PUBLICO|INTERNO", "sensitivity": "PUBLICO", "ingestion_mode": "STRUCTURED_TABLE", "target_corpus": "CORPUS_PUBLICO|CORPUS_INTERNO"},
    {"canonical_id": "VINC-CAN-004", "canonical_status": "CANONICO_VIGENTE", "drive_file_id": "FOLDER-GOLDEN", "agent_index_authorized": "TRUE", "agent_access_scope": "PUBLICO|INTERNO", "sensitivity": "PUBLICO", "ingestion_mode": "EXPAND_COLLECTION_HTML", "target_corpus": "CORPUS_PUBLICO|CORPUS_INTERNO"},
    {"canonical_id": "VINC-CAN-005", "canonical_status": "CANONICO_VIGENTE", "drive_file_id": "SHEET-RESP", "agent_index_authorized": "FALSE", "agent_access_scope": "RESTRITO_PESQUISA", "sensitivity": "DADOS_DE_PESQUISA_RESTRITOS", "ingestion_mode": "NONE", "target_corpus": "FORA_DO_CORPUS_AGENT"},
    {"canonical_id": "VINC-CAN-006", "canonical_status": "CANONICO_VIGENTE", "drive_file_id": "FOLDER-NEXO", "agent_index_authorized": "FALSE", "agent_access_scope": "INTERNO_FUTURO", "sensitivity": "INTERNO", "ingestion_mode": "NONE", "target_corpus": "FORA_DO_CORPUS_TEXTUAL_V0.1"},
    {"canonical_id": "VINC-CAN-007", "canonical_status": "CANONICO_VIGENTE", "drive_file_id": "DOC-ELEMENTOR", "agent_index_authorized": "TRUE", "agent_access_scope": "INTERNO", "sensitivity": "INTERNO", "ingestion_mode": "FULL_TEXT", "target_corpus": "CORPUS_INTERNO"},
    {"canonical_id": "VINC-CAN-008", "canonical_status": "CANONICO_VIGENTE", "drive_file_id": "DOC-HIST", "agent_index_authorized": "FALSE", "agent_access_scope": "FORA_DO_AGENT", "sensitivity": "HISTORICO_INSTITUCIONAL", "ingestion_mode": "NONE", "target_corpus": "FORA_DO_CORPUS_AGENT"},
    {"canonical_id": "VINC-CAN-009", "canonical_status": "CANONICO_VIGENTE", "drive_file_id": "DOC-VISUAL", "agent_index_authorized": "TRUE", "agent_access_scope": "INTERNO", "sensitivity": "INTERNO", "ingestion_mode": "FULL_TEXT", "target_corpus": "CORPUS_INTERNO"},
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


def test_generic_snapshot_understands_live_scope_schema():
    _, policy = adapters()
    snapshot = policy.snapshot()
    assert snapshot.allowed_asset_ids == frozenset(
        {"DOC-CARTA", "SHEET-URLS", "SHEET-GLOSSARIO", "FOLDER-GOLDEN", "DOC-ELEMENTOR", "DOC-VISUAL"}
    )
    assert not snapshot.is_scope_bound


def test_public_snapshot_is_bound_and_allows_only_explicit_public_corpus():
    registry, policy = adapters()
    snapshot = policy.snapshot_for("PUBLICO", "CORPUS_PUBLICO")
    assert snapshot.requester_scope == "PUBLICO"
    assert snapshot.target_corpus == "CORPUS_PUBLICO"
    assert snapshot.allowed_asset_ids == frozenset({"DOC-CARTA", "SHEET-GLOSSARIO", "FOLDER-GOLDEN"})

    allowed_ids = {"VINC-CAN-001", "VINC-CAN-003", "VINC-CAN-004"}
    for row in ROWS:
        asset = registry.load_asset(row["canonical_id"])
        assert policy.authorize_asset(asset, snapshot) is (row["canonical_id"] in allowed_ids)


def test_public_policy_hash_is_scope_and_corpus_bound():
    _, policy = adapters()
    public = policy.snapshot_for("PUBLICO", "CORPUS_PUBLICO")
    internal = policy.snapshot_for("INTERNO", "CORPUS_INTERNO")
    assert public.policy_hash != internal.policy_hash
    assert internal.allowed_asset_ids == frozenset(
        {"DOC-CARTA", "SHEET-URLS", "SHEET-GLOSSARIO", "FOLDER-GOLDEN", "DOC-ELEMENTOR", "DOC-VISUAL"}
    )


def test_cross_scope_corpus_pairs_fail_closed_even_when_row_has_both_tokens():
    registry, policy = adapters()
    for scope, corpus in (
        ("PUBLICO", "CORPUS_INTERNO"),
        ("INTERNO", "CORPUS_PUBLICO"),
    ):
        snapshot = policy.snapshot_for(scope, corpus)
        candidate_filter = policy.filter_candidate_scope(RetrievalRequest("vieses", scope, corpus))
        assert snapshot.allowed_asset_ids == frozenset()
        assert candidate_filter.allowed_canonical_ids == frozenset()
        assert not policy.authorize_asset(registry.load_asset("VINC-CAN-001"), snapshot)


def test_public_retrieval_filter_uses_same_scoped_canonical_policy():
    _, policy = adapters()
    request = RetrievalRequest("vieses", "PUBLICO", "CORPUS_PUBLICO")
    candidate_filter = policy.filter_candidate_scope(request)
    snapshot = policy.snapshot_for("PUBLICO", "CORPUS_PUBLICO")

    assert candidate_filter.allowed_canonical_ids == frozenset(
        {"VINC-CAN-001", "VINC-CAN-003", "VINC-CAN-004"}
    )
    assert candidate_filter.requester_scope == "PUBLICO"
    assert candidate_filter.target_corpus == "CORPUS_PUBLICO"
    assert candidate_filter.policy_hash == snapshot.policy_hash


def test_restricted_and_historical_sources_never_enter_agent_snapshot():
    registry, policy = adapters()
    generic = policy.snapshot()
    for canonical_id in ("VINC-CAN-005", "VINC-CAN-006", "VINC-CAN-008"):
        assert not policy.authorize_asset(registry.load_asset(canonical_id), generic)


def test_no_title_or_similarity_fallback():
    registry, _ = adapters()
    try:
        registry.load_asset("Carta Fundacional")
    except RuntimeError as exc:
        assert str(exc) == "E_REGISTRY_DENY"
    else:
        raise AssertionError("lookup must require exact canonical_id")
