from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


class RuntimeSelectionError(ValueError):
    """Raised when the internal-beta runtime diverges from the authorized selection."""


@dataclass(frozen=True, slots=True)
class InternalBetaRuntimeSelection:
    model_provider: str = "openai"
    model_api: str = "responses"
    model_id: str = "gpt-5.6-terra"
    model_external_tools_allowed: bool = False
    deployment_platform: str = "gcp-cloud-run"
    deployment_region: str = "southamerica-east1"
    deployment_service: str = "vinc-agent-internal-beta"
    database_service: str = "gcp-cloud-sql-postgresql"
    secret_store: str = "gcp-secret-manager"
    public_access: bool = False

    def __post_init__(self) -> None:
        expected = {
            "model_provider": "openai",
            "model_api": "responses",
            "model_id": "gpt-5.6-terra",
            "deployment_platform": "gcp-cloud-run",
            "deployment_region": "southamerica-east1",
            "database_service": "gcp-cloud-sql-postgresql",
            "secret_store": "gcp-secret-manager",
        }
        for field_name, expected_value in expected.items():
            if getattr(self, field_name) != expected_value:
                raise RuntimeSelectionError(f"unauthorized {field_name}")
        if self.model_external_tools_allowed:
            raise RuntimeSelectionError("model external tools remain forbidden")
        if self.public_access:
            raise RuntimeSelectionError("R30 is internal beta only")
        if not self.deployment_service.strip():
            raise RuntimeSelectionError("deployment service is required")

    @property
    def selection_hash(self) -> str:
        payload = "|".join(
            [
                self.model_provider,
                self.model_api,
                self.model_id,
                str(self.model_external_tools_allowed),
                self.deployment_platform,
                self.deployment_region,
                self.deployment_service,
                self.database_service,
                self.secret_store,
                str(self.public_access),
            ]
        )
        return sha256(payload.encode("utf-8")).hexdigest()


AUTHORIZED_INTERNAL_BETA_RUNTIME = InternalBetaRuntimeSelection()
