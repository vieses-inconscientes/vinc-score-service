from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Mapping, Sequence

from .domain import AssetRef, PolicySnapshot
from .external_contracts import AllowlistedRegistryReader
from .retrieval import CandidateFilter, RetrievalRequest


_TRUE = {"TRUE", "true", "1", "YES", "yes"}
_AGENT_CORPORA = frozenset({"CORPUS_PUBLICO", "CORPUS_INTERNO"})
_VALID_SCOPE_CORPUS_PAIRS = frozenset(
    {
        ("PUBLICO", "CORPUS_PUBLICO"),
        ("INTERNO", "CORPUS_INTERNO"),
    }
)


def _is_true(value: str | None) -> bool:
    return (value or "").strip() in _TRUE


def _tokens(value: str | None) -> frozenset[str]:
    return frozenset(part.strip() for part in (value or "").split("|") if part.strip())


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
    """Build immutable policies from the live canonical registry schema."""

    registry: CanonicalRegistryAdapter

    @staticmethod
    def _row_is_agent_authorized(row: Mapping[str, str]) -> bool:
        if not _is_true(row.get("agent_index_authorized")):
            return False
        if not _tokens(row.get("agent_access_scope")):
            return False
        if row.get("ingestion_mode", "").strip() == "NONE":
            return False
        if not (_tokens(row.get("target_corpus")) & _AGENT_CORPORA):
            return False
        return True

    @classmethod
    def _row_is_authorized_for(
        cls,
        row: Mapping[str, str],
        *,
        requester_scope: str,
        target_corpus: str,
    ) -> bool:
        if not cls._row_is_agent_authorized(row):
            return False
        if (requester_scope, target_corpus) not in _VALID_SCOPE_CORPUS_PAIRS:
            return False
        if requester_scope not in _tokens(row.get("agent_access_scope")):
            return False
        if target_corpus not in _tokens(row.get("target_corpus")):
            return False
        if target_corpus == "CORPUS_PUBLICO" and row.get("sensitivity", "").strip() != "PUBLICO":
            return False
        return True

    def snapshot(self) -> PolicySnapshot:
        rows = self.registry._rows()
        allowed = frozenset(
            row.get("drive_file_id", "").strip()
            for row in rows
            if self._row_is_agent_authorized(row) and row.get("drive_file_id", "").strip()
        )
        material = "\n".join(sorted(allowed)).encode("utf-8")
        return PolicySnapshot(policy_hash=sha256(material).hexdigest(), allowed_asset_ids=allowed)

    @classmethod
    def _scoped_rows(
        cls,
        rows: Sequence[Mapping[str, str]],
        *,
        requester_scope: str,
        target_corpus: str,
    ) -> tuple[Mapping[str, str], ...]:
        return tuple(
            row
            for row in rows
            if row.get("canonical_id", "").strip()
            and row.get("drive_file_id", "").strip()
            and cls._row_is_authorized_for(
                row, requester_scope=requester_scope, target_corpus=target_corpus
            )
        )

    @staticmethod
    def _scoped_policy_hash(
        requester_scope: str,
        target_corpus: str,
        rows: Sequence[Mapping[str, str]],
    ) -> str:
        bindings = sorted(
            f"{row.get('canonical_id', '').strip()}={row.get('drive_file_id', '').strip()}"
            for row in rows
        )
        material = "\n".join(
            (f"scope={requester_scope}", f"corpus={target_corpus}", *bindings)
        ).encode("utf-8")
        return sha256(material).hexdigest()

    def snapshot_for(self, requester_scope: str, target_corpus: str) -> PolicySnapshot:
        scope = requester_scope.strip()
        corpus = target_corpus.strip()
        if not scope or not corpus:
            raise ValueError("requester_scope and target_corpus are required")
        eligible = self._scoped_rows(
            self.registry._rows(), requester_scope=scope, target_corpus=corpus
        )
        return PolicySnapshot(
            policy_hash=self._scoped_policy_hash(scope, corpus, eligible),
            allowed_asset_ids=frozenset(row.get("drive_file_id", "").strip() for row in eligible),
            requester_scope=scope,
            target_corpus=corpus,
        )

    def filter_candidate_scope(self, request: RetrievalRequest) -> CandidateFilter:
        scope = request.requester_scope.strip()
        corpus = request.target_corpus.strip()
        eligible = self._scoped_rows(
            self.registry._rows(), requester_scope=scope, target_corpus=corpus
        )
        return CandidateFilter(
            allowed_canonical_ids=frozenset(
                row.get("canonical_id", "").strip() for row in eligible
            ),
            target_corpus=corpus,
            requester_scope=scope,
            policy_hash=self._scoped_policy_hash(scope, corpus, eligible),
        )

    def authorize_asset(self, asset: AssetRef, snapshot: PolicySnapshot) -> bool:
        row = self.registry.load_row(asset.canonical_object_id)
        if snapshot.is_scope_bound:
            authorized = self._row_is_authorized_for(
                row,
                requester_scope=snapshot.requester_scope or "",
                target_corpus=snapshot.target_corpus or "",
            )
        else:
            authorized = self._row_is_agent_authorized(row)
        return authorized and snapshot.allows(asset)
