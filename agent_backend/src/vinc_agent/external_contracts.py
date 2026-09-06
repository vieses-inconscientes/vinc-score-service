from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

from .domain import AssetRef, ProviderPayload


class SheetsReader(Protocol):
    def read_rows(self, spreadsheet_id: str, tab: str) -> Sequence[Mapping[str, str]]: ...


class DriveReader(Protocol):
    def fetch_by_id(self, file_id: str) -> bytes: ...


@dataclass(frozen=True, slots=True)
class RegistryConfig:
    spreadsheet_id: str
    allowed_tabs: frozenset[str]

    def require_tab(self, tab: str) -> None:
        if tab not in self.allowed_tabs:
            raise PermissionError("tab is not allowlisted")


@dataclass(slots=True)
class ExactDriveProvider:
    reader: DriveReader

    def fetch_exact(self, asset: AssetRef) -> ProviderPayload:
        if asset.provider != "gdrive":
            raise PermissionError("provider denied")
        content = self.reader.fetch_by_id(asset.source_asset_id)
        payload = ProviderPayload(source_asset_id=asset.source_asset_id, content=content)
        if payload.source_asset_id != asset.source_asset_id:
            raise RuntimeError("E_FETCH_INTEGRITY")
        return payload


@dataclass(slots=True)
class AllowlistedRegistryReader:
    reader: SheetsReader
    config: RegistryConfig

    def rows(self, tab: str) -> Sequence[Mapping[str, str]]:
        self.config.require_tab(tab)
        rows = self.reader.read_rows(self.config.spreadsheet_id, tab)
        if not rows:
            raise RuntimeError("E_REGISTRY_DENY")
        return rows
