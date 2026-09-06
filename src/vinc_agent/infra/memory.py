"""In-memory adapters used only for deterministic tests and local orchestration."""

import hashlib
from dataclasses import dataclass, field

from vinc_agent.domain import (
    AssetRef,
    Chunk,
    ChunkBatch,
    FingerprintResult,
    IngestionResult,
    NormalizedDocument,
    PolicySnapshot,
    ProviderPayload,
    Section,
    ValidationGateResult,
    ValidationReport,
)


@dataclass(slots=True)
class MemoryRegistry:
    assets: dict[tuple[str, str], AssetRef]

    def get_asset(self, canonical_id: str, provider_file_id: str) -> AssetRef:
        return self.assets[(canonical_id, provider_file_id)]


class AllowPolicy:
    def authorize_asset(self, asset: AssetRef, snapshot: PolicySnapshot) -> bool:
        return asset.asset_key in snapshot.allowed_scopes or "*" in snapshot.allowed_scopes


@dataclass(slots=True)
class MemoryDrive:
    payloads: dict[str, ProviderPayload]

    def fetch_exact(self, asset: AssetRef) -> ProviderPayload:
        payload = self.payloads[asset.provider_file_id]
        payload.assert_matches(asset)
        return payload


class Sha256Fingerprint:
    def compute(self, payload: ProviderPayload, profile: str) -> FingerprintResult:
        raw = hashlib.sha256(payload.content).hexdigest()
        normalized = hashlib.sha256(payload.content.strip()).hexdigest()
        material = hashlib.sha256((profile + ":" + normalized).encode()).hexdigest()
        return FingerprintResult(raw, normalized, material, payload.provider_revision_hint, profile)


class PlainTextExtractor:
    def extract(self, asset: AssetRef, payload: ProviderPayload, profile: str) -> NormalizedDocument:
        text = payload.content.decode("utf-8").strip()
        revision = hashlib.sha256(payload.content).hexdigest()
        section = Section("s000", ("root",), f"{profile}:root", text)
        return NormalizedDocument(asset.canonical_id, asset.asset_key, revision, text, (section,))


class PassValidator:
    def validate(self, stage_payload: object, gate_set: tuple[str, ...]) -> ValidationReport:
        gates = tuple(ValidationGateResult(gate, True, True) for gate in gate_set)
        digest = hashlib.sha256("|".join(gate_set).encode()).hexdigest()
        return ValidationReport("memory-v1", gates, digest)


class DeterministicChunker:
    def build_chunks(self, normalized_document: NormalizedDocument, profile: str) -> ChunkBatch:
        text = normalized_document.text
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        chunk = Chunk(
            chunk_id=f"{normalized_document.asset_key}:0000:{text_hash[:12]}",
            section_id=normalized_document.sections[0].section_id,
            source_revision_id=normalized_document.source_revision_id,
            asset_key=normalized_document.asset_key,
            canonical_id=normalized_document.canonical_id,
            chunk_ordinal=0,
            chunk_text=text,
            chunk_text_sha256=text_hash,
            token_count=max(1, len(text.split())),
            access_scope="internal",
            sensitivity="public",
            instruction_authority="source-only",
            source_locator=normalized_document.sections[0].source_locator,
        )
        batch_hash = hashlib.sha256((profile + ":" + text_hash).encode()).hexdigest()
        return ChunkBatch(normalized_document.source_revision_id, normalized_document.sections, (chunk,), batch_hash)


@dataclass(slots=True)
class MemoryIndexer:
    staged: list[ChunkBatch] = field(default_factory=list)

    def build_staging_index(self, chunks: ChunkBatch, config: object) -> object:
        self.staged.append(chunks)
        return {"batch_hash": chunks.batch_hash, "chunk_count": len(chunks.chunks)}


@dataclass(slots=True)
class MemoryPublisher:
    publications: list[object] = field(default_factory=list)

    def atomic_publish(self, request: object) -> object:
        self.publications.append(request)
        return {"published": True, "request": request}


@dataclass(slots=True)
class MemoryAudit:
    results: list[IngestionResult] = field(default_factory=list)

    def finalize_run(self, result: IngestionResult) -> object:
        self.results.append(result)
        return {"audited": True, "state": result.state.value}
