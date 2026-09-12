from __future__ import annotations

from collections import deque

import pytest

from vinc_agent.operational_metadata import (
    CanonicalObjectProjection,
    CanonicalUrlProjection,
    CorpusMembershipProjection,
    OperationalMetadataBundle,
    OperationalMetadataError,
    OperationalMetadataProjector,
    RunRevisionCandidate,
    RunRevisionInitializer,
    SourceAssetProjection,
)


class FakeCursor:
    def __init__(self, scripted_rows=None):
        self.events = []
        self._scripted_rows = deque(scripted_rows or [])
        self._current = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, statement, params):
        self.events.append((statement, params))
        self._current = self._scripted_rows.popleft() if self._scripted_rows else ("ok",)

    def fetchone(self):
        return self._current


class FakeConnection:
    def __init__(self, scripted_rows=None):
        self.cursor_instance = FakeCursor(scripted_rows)
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def sample_bundle() -> OperationalMetadataBundle:
    return OperationalMetadataBundle(
        canonical_objects=(
            CanonicalObjectProjection(
                canonical_id="VINC-CAN-001",
                drive_file_id="drive-001",
                agent_index_authorized=True,
                domain="institucional",
                access_scope="PUBLICO",
            ),
        ),
        corpus_memberships=(
            CorpusMembershipProjection(
                membership_id="mem-001-public",
                canonical_id="VINC-CAN-001",
                target_corpus="CORPUS_PUBLICO",
                access_scope="PUBLICO",
                enabled=True,
            ),
        ),
        source_assets=(
            SourceAssetProjection(
                asset_key="asset-001",
                canonical_id="VINC-CAN-001",
                provider_file_id="drive-001",
                source_type="GOOGLE_DOC",
            ),
        ),
        canonical_urls=(
            CanonicalUrlProjection(
                url_key="url-001",
                url_order=1,
                slug="vinc-agent",
                canonical_url="https://viesesinconscientes.org/vinc-agent/",
                name="V'inC Agent",
            ),
        ),
    )


def test_projector_is_deterministic_transactional_and_never_publishes():
    connection = FakeConnection()
    projector = OperationalMetadataProjector(lambda: connection)

    projector.project(sample_bundle())

    statements = [statement for statement, _ in connection.cursor_instance.events]
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert [
        "canonical_objects" in statements[0],
        "corpus_memberships" in statements[1],
        "source_assets" in statements[2],
        "canonical_urls" in statements[3],
    ] == [True, True, True, True]
    assert all("ON CONFLICT" in statement for statement in statements)
    assert not any("PUBLISHED" in statement for statement in statements)
    assert not any("operational_current = TRUE" in statement for statement in statements)
    assert not any(statement.lstrip().startswith("DELETE") for statement in statements)


def test_projector_repeated_exact_bundle_emits_same_idempotent_projection():
    first = FakeConnection()
    second = FakeConnection()

    OperationalMetadataProjector(lambda: first).project(sample_bundle())
    OperationalMetadataProjector(lambda: second).project(sample_bundle())

    assert first.cursor_instance.events == second.cursor_instance.events
    assert first.commits == second.commits == 1


def test_projector_rejects_invalid_scope_corpus_pair_before_database_access():
    with pytest.raises(ValueError, match="invalid access_scope/target_corpus pair"):
        CorpusMembershipProjection(
            membership_id="bad",
            canonical_id="VINC-CAN-001",
            target_corpus="CORPUS_INTERNO",
            access_scope="PUBLICO",
            enabled=True,
        )


def test_projector_rejects_unbundled_foreign_canonical_id():
    with pytest.raises(ValueError, match="membership must reference"):
        OperationalMetadataBundle(
            canonical_objects=sample_bundle().canonical_objects,
            corpus_memberships=(
                CorpusMembershipProjection(
                    membership_id="mem-other",
                    canonical_id="VINC-CAN-999",
                    target_corpus="CORPUS_PUBLICO",
                    access_scope="PUBLICO",
                    enabled=True,
                ),
            ),
            source_assets=(),
            canonical_urls=(),
        )


def test_projector_fails_closed_and_rolls_back_on_identity_conflict():
    connection = FakeConnection(scripted_rows=[("co",), ("mem",), None])

    with pytest.raises(OperationalMetadataError, match="source asset identity conflict"):
        OperationalMetadataProjector(lambda: connection).project(sample_bundle())

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_run_revision_initializer_creates_only_invisible_started_candidate():
    connection = FakeConnection(scripted_rows=[("run",), ("revision",)])
    candidate = RunRevisionCandidate(
        run_id="00000000-0000-0000-0000-000000000033",
        source_revision_id="rev-33",
        asset_key="asset-001",
        material_fingerprint="fingerprint-33",
        provider_revision_hint="provider-rev-1",
    )

    RunRevisionInitializer(lambda: connection).initialize(candidate)

    statements = [statement for statement, _ in connection.cursor_instance.events]
    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert "'STARTED'" in statements[0]
    assert "FALSE" in statements[1]
    assert not any("PUBLISHED" in statement for statement in statements)
    assert not any("operational_current = TRUE" in statement for statement in statements)


def test_run_revision_initializer_is_idempotent_only_for_exact_existing_state():
    candidate = RunRevisionCandidate(
        run_id="00000000-0000-0000-0000-000000000033",
        source_revision_id="rev-33",
        asset_key="asset-001",
        material_fingerprint="fingerprint-33",
        provider_revision_hint=None,
    )
    connection = FakeConnection(
        scripted_rows=[
            None,
            ("STARTED", None, None),
            None,
            ("asset-001", candidate.run_id, "fingerprint-33", None, False),
        ]
    )

    RunRevisionInitializer(lambda: connection).initialize(candidate)

    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert len(connection.cursor_instance.events) == 4


def test_run_revision_initializer_rolls_back_on_existing_visibility_or_binding_drift():
    candidate = RunRevisionCandidate(
        run_id="00000000-0000-0000-0000-000000000033",
        source_revision_id="rev-33",
        asset_key="asset-001",
        material_fingerprint="fingerprint-33",
    )
    connection = FakeConnection(
        scripted_rows=[
            None,
            ("PUBLISHED", "PASS", "2026-09-12T00:00:00Z"),
        ]
    )

    with pytest.raises(OperationalMetadataError, match="not idempotent STARTED state"):
        RunRevisionInitializer(lambda: connection).initialize(candidate)

    assert connection.commits == 0
    assert connection.rollbacks == 1


def test_run_revision_candidate_requires_uuid_and_nonblank_identity():
    with pytest.raises(ValueError, match="UUID"):
        RunRevisionCandidate(
            run_id="not-a-uuid",
            source_revision_id="rev",
            asset_key="asset",
            material_fingerprint="fingerprint",
        )

    with pytest.raises(ValueError, match="identity fields"):
        RunRevisionCandidate(
            run_id="00000000-0000-0000-0000-000000000033",
            source_revision_id="",
            asset_key="asset",
            material_fingerprint="fingerprint",
        )
