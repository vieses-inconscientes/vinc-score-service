import pytest

from vinc_agent.sync import CanonicalSyncState, IncrementalSyncPlanner, PublishedSyncState, SyncAction


def current(**kw):
    data = dict(canonical_id="CAN_1", status="CANONICO_VIGENTE", agent_index_authorized=True, target_corpus="CORPUS_INTERNO", material_fingerprint="fp2")
    data.update(kw)
    return CanonicalSyncState(**data)


def published(**kw):
    data = dict(canonical_id="CAN_1", target_corpus="CORPUS_INTERNO", material_fingerprint="fp1")
    data.update(kw)
    return PublishedSyncState(**data)


def test_new_authorized_canonical_is_planned_for_ingest():
    assert IncrementalSyncPlanner.decide(current(), None).action is SyncAction.INGEST


def test_unchanged_fingerprint_is_no_change():
    d = IncrementalSyncPlanner.decide(current(material_fingerprint="fp1"), published())
    assert d.action is SyncAction.NO_CHANGE


def test_material_change_is_ingest():
    assert IncrementalSyncPlanner.decide(current(), published()).action is SyncAction.INGEST


def test_active_or_historical_content_is_never_promoted():
    for status in ("ATIVO", "HISTORICO", "SUBSTITUIDO"):
        d = IncrementalSyncPlanner.decide(current(status=status), None)
        assert d.action is SyncAction.EXCLUDE


def test_revoked_authorization_withdraws_existing_published_revision():
    d = IncrementalSyncPlanner.decide(current(agent_index_authorized=False), published())
    assert d.action is SyncAction.WITHDRAW


def test_exact_canonical_id_is_required_for_published_comparison():
    with pytest.raises(ValueError):
        IncrementalSyncPlanner.decide(current(), published(canonical_id="CAN_OTHER"))
