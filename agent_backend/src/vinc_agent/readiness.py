from __future__ import annotations

from dataclasses import dataclass


REQUIRED_INTERNAL_BETA_CHECKS = frozenset(
    {
        "canonical_registry",
        "retrieval_eval",
        "copilot_security",
        "test_suite",
        "runtime_config",
        "model_provider",
        "persistence",
        "deployment_target",
    }
)


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    check_id: str
    passed: bool
    evidence: str


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    ready: bool
    missing: tuple[str, ...]
    failed: tuple[str, ...]


class InternalBetaReadiness:
    """R30: fail-closed deployment gate. No provider/target is chosen here."""

    @staticmethod
    def evaluate(checks: tuple[ReadinessCheck, ...]) -> ReadinessReport:
        by_id = {check.check_id: check for check in checks}
        if len(by_id) != len(checks):
            raise ValueError("duplicate readiness check ids")
        missing = tuple(sorted(REQUIRED_INTERNAL_BETA_CHECKS - by_id.keys()))
        failed = tuple(
            sorted(
                check_id
                for check_id in REQUIRED_INTERNAL_BETA_CHECKS & by_id.keys()
                if not by_id[check_id].passed
            )
        )
        return ReadinessReport(not missing and not failed, missing, failed)
