from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Mapping, Sequence

from .domain import AssetRef, PolicySnapshot
from .external_contracts import AllowlistedRegistryReader


_TRUE = {"TRUE", "true", "1", "YES", "yes"}


def _is_true(value: str | None) -> bool:
    return (value or "").strip() in _TRUE


@dataclass(slots=True)
class CanonicalRegistryAdapter:
    """Translate only the live canonical registry row into an AssetRef.

    This adapter never searches by title, URL, family or similarity. The caller
    must provide the exact canonical_id and the registry reader must itself be
    allowlisted to REGISTRO_CANONICO.
    """

    registry: AllowlistedRegistryReader
    tab: str = "REGISTRO_CANONICO"

    def _rows(self) -> Sequence[Mapping[str, str]]:
        return self.registry.rows(self.tab)

    def load_row(self, canonical_object_id: str) -> Mapping[str, str]:
        matches = [
            row
            for row in self._rows()
            if row.get("canonical_id", "").strip() == canonical_object_id
        ]
        if len(matches) != 1:
            raise RuntimeError("E_REGISTRY_DENY")
        row = matches[0]
        if row.get("canonical_status", "").strip() != "CANONICO_VIGENTE":
            raise RuntimeError("E_ASSET_NOT_ALLOWLISTED")
        return row

    def load_asset(self, canonical_object_id: str) -> AssetRef:
        row = self.load_row(canonical_object_id)
        drive_file_id = row.get("drive_file_id", "").strip()
        if not drive_file_id:
            raise RuntimeError("E_REGISTRY_DENY")
        return AssetRef(
            canonical_object_id=canonical_object_id,
            source_asset_id=drive_file_id,
            provider="gdrive",
        )


@dataclass(slots=True)
class CanonicalPolicyAdapter:
    """Build an immutable run policy from the same canonical registry snapshot."""

    registry: CanonicalRegistryAdapter

    @staticmethod
    def _row_is_authorized(row: Mapping[str, str]) -> bool:
        if not _is_true(row.get("agent_index_authorized")):
            return False
        if not _is_true(row.get("agent_access_scope")):
            return False
        if row.get("ingestion_mode", "").strip() == "NONE":
            return False
        if row.get("target_corpus", "").strip() == "FORA_DO_CORPUS_AGENT":
            return False
        return True

    def snapshot(self) -> PolicySnapshot:
        rows = self.registry._rows()
        allowed = frozenset(
            row.get("drive_file_id", "").strip()
            for row in rows
            if self._row_is_authorized(row) and row.get("drive_file_id", "").strip()
        )
        material = "\n".join(sorted(allowed)).encode("utf-8")
        return PolicySnapshot(policy_hash=sha256(material).hexdigest(), allowed_asset_ids=allowed)

    def authorize_asset(self, asset: AssetRef, snapshot: PolicySnapshot) -> bool:
        row = self.registry.load_row(asset.canonical_object_id)
        return self._row_is_authorized(row) and snapshot.allows(asset)
