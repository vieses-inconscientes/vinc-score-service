from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from uuid import UUID


_VALID_SCOPE_CORPUS_PAIRS = frozenset(
    {
        ("PUBLICO", "CORPUS_PUBLICO"),
        ("INTERNO", "CORPUS_INTERNO"),
    }
)
_VALID_SOURCE_TYPES = frozenset({"GOOGLE_DOC", "HTML", "SHEET_STRUCTURED"})


class OperationalMetadataError(RuntimeError):
    """Fail-closed error raised when operational metadata cannot be projected exactly."""


@dataclass(frozen=True, slots=True)
class CanonicalObjectProjection:
    canonical_id: str
    drive_file_id: str | None
    agent_index_authorized: bool
    domain: str
    access_scope: str
    canonical_status: str = "CANONICO_VIGENTE"

    def __post_init__(self) -> None:
        if not self.canonical_id.strip():
            raise ValueError("canonical_id is required")
        if self.canonical_status != "CANONICO_VIGENTE":
            raise ValueError("only CANONICO_VIGENTE objects may be projected")
        if self.drive_file_id is not None and not self.drive_file_id.strip():
            raise ValueError("drive_file_id cannot be blank")
        if self.agent_index_authorized and self.drive_file_id is None:
            raise ValueError("authorized canonical object requires drive_file_id")
        if not self.domain.strip() or not self.access_scope.strip():
            raise ValueError("domain and access_scope are required")


@dataclass(frozen=True, slots=True)
class CorpusMembershipProjection:
    membership_id: str
    canonical_id: str
    target_corpus: str
    access_scope: str
    enabled: bool

    def __post_init__(self) -> None:
        required = (self.membership_id, self.canonical_id, self.target_corpus, self.access_scope)
        if any(not value.strip() for value in required):
            raise ValueError("membership identity fields are required")
        if (self.access_scope, self.target_corpus) not in _VALID_SCOPE_CORPUS_PAIRS:
            raise ValueError("invalid access_scope/target_corpus pair")


@dataclass(frozen=True, slots=True)
class SourceAssetProjection:
    asset_key: str
    canonical_id: str
    provider_file_id: str
    source_type: str
    provider: str = "gdrive"

    def __post_init__(self) -> None:
        required = (
            self.asset_key,
            self.canonical_id,
            self.provider,
            self.provider_file_id,
            self.source_type,
        )
        if any(not value.strip() for value in required):
            raise ValueError("source asset identity fields are required")
        if self.provider != "gdrive":
            raise ValueError("only gdrive source assets are authorized")
        if self.source_type not in _VALID_SOURCE_TYPES:
            raise ValueError("unsupported source_type")


@dataclass(frozen=True, slots=True)
class CanonicalUrlProjection:
    url_key: str
    url_order: int
    slug: str
    canonical_url: str
    name: str

    def __post_init__(self) -> None:
        required = (self.url_key, self.slug, self.canonical_url, self.name)
        if any(not value.strip() for value in required):
            raise ValueError("canonical URL fields are required")
        if not 1 <= self.url_order <= 116:
            raise ValueError("url_order must be between 1 and 116")
        if not self.canonical_url.startswith("https://"):
            raise ValueError("canonical_url must be absolute HTTPS")


@dataclass(frozen=True, slots=True)
class OperationalMetadataBundle:
    canonical_objects: tuple[CanonicalObjectProjection, ...]
    corpus_memberships: tuple[CorpusMembershipProjection, ...]
    source_assets: tuple[SourceAssetProjection, ...]
    canonical_urls: tuple[CanonicalUrlProjection, ...]

    def __post_init__(self) -> None:
        canonical_ids = tuple(item.canonical_id for item in self.canonical_objects)
        membership_ids = tuple(item.membership_id for item in self.corpus_memberships)
        asset_keys = tuple(item.asset_key for item in self.source_assets)
        url_keys = tuple(item.url_key for item in self.canonical_urls)
        url_orders = tuple(item.url_order for item in self.canonical_urls)
        canonical_urls = tuple(item.canonical_url for item in self.canonical_urls)

        for label, values in (
            ("canonical_id", canonical_ids),
            ("membership_id", membership_ids),
            ("asset_key", asset_keys),
            ("url_key", url_keys),
            ("url_order", url_orders),
            ("canonical_url", canonical_urls),
        ):
            if len(set(values)) != len(values):
                raise ValueError(f"duplicate {label} in metadata bundle")

        canonical_set = set(canonical_ids)
        if any(item.canonical_id not in canonical_set for item in self.corpus_memberships):
            raise ValueError("every membership must reference a bundled canonical object")
        if any(item.canonical_id not in canonical_set for item in self.source_assets):
            raise ValueError("every source asset must reference a bundled canonical object")


@dataclass(frozen=True, slots=True)
class RunRevisionCandidate:
    run_id: str
    source_revision_id: str
    asset_key: str
    material_fingerprint: str
    provider_revision_hint: str | None = None

    def __post_init__(self) -> None:
        try:
            UUID(self.run_id)
        except (ValueError, AttributeError) as exc:
            raise ValueError("run_id must be a UUID") from exc
        required = (self.source_revision_id, self.asset_key, self.material_fingerprint)
        if any(not value.strip() for value in required):
            raise ValueError("revision candidate identity fields are required")
        if self.provider_revision_hint is not None and not self.provider_revision_hint.strip():
            raise ValueError("provider_revision_hint cannot be blank")


class OperationalMetadataProjector:
    """Deterministic Registry/Manifest/URL -> PostgreSQL operational projection.

    This adapter projects only explicitly supplied, already-authorized metadata.
    It never discovers sources, mutates governance records, publishes corpus rows,
    creates revisions, changes operational visibility, or repairs missing semantics.
    """

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect

    def project(self, bundle: OperationalMetadataBundle) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                for item in sorted(bundle.canonical_objects, key=lambda row: row.canonical_id):
                    cursor.execute(_UPSERT_CANONICAL_OBJECT, {
                        "canonical_id": item.canonical_id,
                        "drive_file_id": item.drive_file_id,
                        "canonical_status": item.canonical_status,
                        "agent_index_authorized": item.agent_index_authorized,
                        "domain": item.domain,
                        "access_scope": item.access_scope,
                    })
                    self._require_returning(cursor, "canonical object projection conflict")

                for item in sorted(bundle.corpus_memberships, key=lambda row: row.membership_id):
                    cursor.execute(_UPSERT_CORPUS_MEMBERSHIP, {
                        "membership_id": item.membership_id,
                        "canonical_id": item.canonical_id,
                        "target_corpus": item.target_corpus,
                        "access_scope": item.access_scope,
                        "enabled": item.enabled,
                    })
                    self._require_returning(cursor, "corpus membership identity conflict")

                for item in sorted(bundle.source_assets, key=lambda row: row.asset_key):
                    cursor.execute(_UPSERT_SOURCE_ASSET, {
                        "asset_key": item.asset_key,
                        "canonical_id": item.canonical_id,
                        "provider": item.provider,
                        "provider_file_id": item.provider_file_id,
                        "source_type": item.source_type,
                    })
                    self._require_returning(cursor, "source asset identity conflict")

                for item in sorted(bundle.canonical_urls, key=lambda row: row.url_order):
                    cursor.execute(_UPSERT_CANONICAL_URL, {
                        "url_key": item.url_key,
                        "url_order": item.url_order,
                        "slug": item.slug,
                        "canonical_url": item.canonical_url,
                        "name": item.name,
                    })
                    self._require_returning(cursor, "canonical URL identity conflict")
            connection.commit()
        except Exception:
            connection.rollback()
            raise

    @staticmethod
    def _require_returning(cursor: Any, message: str) -> None:
        if cursor.fetchone() is None:
            raise OperationalMetadataError(message)


class RunRevisionInitializer:
    """Create the invisible pre-publish run/revision binding required by R19/R20.

    Repeated initialization of the same exact candidate is allowed. Any existing
    run or revision with incompatible state/binding fails closed. This adapter
    never sets operational_current=TRUE and never marks a run PUBLISHED.
    """

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect

    def initialize(self, candidate: RunRevisionCandidate) -> None:
        connection = self._connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(_INSERT_RUN, {"run_id": candidate.run_id})
                inserted_run = cursor.fetchone()
                if inserted_run is None:
                    cursor.execute(_READ_RUN, {"run_id": candidate.run_id})
                    existing_run = cursor.fetchone()
                    if existing_run != ("STARTED", None, None):
                        raise OperationalMetadataError("existing ingestion run is not idempotent STARTED state")

                cursor.execute(_INSERT_REVISION, {
                    "source_revision_id": candidate.source_revision_id,
                    "asset_key": candidate.asset_key,
                    "run_id": candidate.run_id,
                    "material_fingerprint": candidate.material_fingerprint,
                    "provider_revision_hint": candidate.provider_revision_hint,
                })
                inserted_revision = cursor.fetchone()
                if inserted_revision is None:
                    cursor.execute(_READ_REVISION, {"source_revision_id": candidate.source_revision_id})
                    existing_revision = cursor.fetchone()
                    expected = (
                        candidate.asset_key,
                        candidate.run_id,
                        candidate.material_fingerprint,
                        candidate.provider_revision_hint,
                        False,
                    )
                    if existing_revision != expected:
                        raise OperationalMetadataError("existing source revision binding is not idempotent")
            connection.commit()
        except Exception:
            connection.rollback()
            raise


_UPSERT_CANONICAL_OBJECT = """
INSERT INTO canonical_objects
    (canonical_id, drive_file_id, canonical_status, agent_index_authorized, domain, access_scope)
VALUES
    (%(canonical_id)s, %(drive_file_id)s, %(canonical_status)s,
     %(agent_index_authorized)s, %(domain)s, %(access_scope)s)
ON CONFLICT (canonical_id) DO UPDATE SET
    drive_file_id = EXCLUDED.drive_file_id,
    canonical_status = EXCLUDED.canonical_status,
    agent_index_authorized = EXCLUDED.agent_index_authorized,
    domain = EXCLUDED.domain,
    access_scope = EXCLUDED.access_scope
RETURNING canonical_id
""".strip()

_UPSERT_CORPUS_MEMBERSHIP = """
INSERT INTO corpus_memberships
    (membership_id, canonical_id, target_corpus, access_scope, enabled)
VALUES
    (%(membership_id)s, %(canonical_id)s, %(target_corpus)s, %(access_scope)s, %(enabled)s)
ON CONFLICT (membership_id) DO UPDATE SET
    enabled = EXCLUDED.enabled
WHERE corpus_memberships.canonical_id = EXCLUDED.canonical_id
  AND corpus_memberships.target_corpus = EXCLUDED.target_corpus
  AND corpus_memberships.access_scope = EXCLUDED.access_scope
RETURNING membership_id
""".strip()

_UPSERT_SOURCE_ASSET = """
INSERT INTO source_assets
    (asset_key, canonical_id, provider, provider_file_id, source_type)
VALUES
    (%(asset_key)s, %(canonical_id)s, %(provider)s, %(provider_file_id)s, %(source_type)s)
ON CONFLICT (asset_key) DO UPDATE SET
    source_type = EXCLUDED.source_type
WHERE source_assets.canonical_id = EXCLUDED.canonical_id
  AND source_assets.provider = EXCLUDED.provider
  AND source_assets.provider_file_id = EXCLUDED.provider_file_id
RETURNING asset_key
""".strip()

_UPSERT_CANONICAL_URL = """
INSERT INTO canonical_urls
    (url_key, url_order, slug, canonical_url, name)
VALUES
    (%(url_key)s, %(url_order)s, %(slug)s, %(canonical_url)s, %(name)s)
ON CONFLICT (url_key) DO UPDATE SET
    slug = EXCLUDED.slug,
    canonical_url = EXCLUDED.canonical_url,
    name = EXCLUDED.name
WHERE canonical_urls.url_order = EXCLUDED.url_order
RETURNING url_key
""".strip()

_INSERT_RUN = """
INSERT INTO ingestion_runs (run_id, status, validation_gate)
VALUES (%(run_id)s, 'STARTED', NULL)
ON CONFLICT (run_id) DO NOTHING
RETURNING run_id
""".strip()

_READ_RUN = """
SELECT status, validation_gate, finished_at
FROM ingestion_runs
WHERE run_id = %(run_id)s
""".strip()

_INSERT_REVISION = """
INSERT INTO source_revisions
    (source_revision_id, asset_key, run_id, material_fingerprint,
     provider_revision_hint, operational_current)
VALUES
    (%(source_revision_id)s, %(asset_key)s, %(run_id)s, %(material_fingerprint)s,
     %(provider_revision_hint)s, FALSE)
ON CONFLICT (source_revision_id) DO NOTHING
RETURNING source_revision_id
""".strip()

_READ_REVISION = """
SELECT asset_key, run_id::text, material_fingerprint, provider_revision_hint, operational_current
FROM source_revisions
WHERE source_revision_id = %(source_revision_id)s
""".strip()
