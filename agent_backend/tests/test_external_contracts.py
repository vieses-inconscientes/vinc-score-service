from vinc_agent.domain import AssetRef
from vinc_agent.external_contracts import AllowlistedRegistryReader, ExactDriveProvider, RegistryConfig


class FakeDrive:
    def fetch_by_id(self, file_id: str) -> bytes:
        return f"payload:{file_id}".encode()


class FakeSheets:
    def read_rows(self, spreadsheet_id: str, tab: str):
        return [{"spreadsheet_id": spreadsheet_id, "tab": tab}]


def test_exact_drive_provider_uses_only_requested_id():
    asset = AssetRef("OBJ-1", "FILE-1")
    payload = ExactDriveProvider(FakeDrive()).fetch_exact(asset)
    assert payload.source_asset_id == "FILE-1"
    assert payload.content == b"payload:FILE-1"


def test_registry_reader_denies_non_allowlisted_tab():
    reader = AllowlistedRegistryReader(FakeSheets(), RegistryConfig("SHEET-1", frozenset({"REGISTRO_CANONICO"})))
    try:
        reader.rows("HISTORICO")
    except PermissionError:
        pass
    else:
        raise AssertionError("non-allowlisted tab must be denied")
