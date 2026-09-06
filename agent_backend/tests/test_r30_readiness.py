import pytest

from vinc_agent.readiness import InternalBetaReadiness, ReadinessCheck, REQUIRED_INTERNAL_BETA_CHECKS


def checks(value=True):
    return tuple(ReadinessCheck(check_id, value, "evidence") for check_id in sorted(REQUIRED_INTERNAL_BETA_CHECKS))


def test_internal_beta_is_ready_only_when_all_required_checks_pass():
    report = InternalBetaReadiness.evaluate(checks())
    assert report.ready is True
    assert report.missing == ()
    assert report.failed == ()


def test_missing_external_runtime_decisions_block_readiness():
    partial = tuple(c for c in checks() if c.check_id not in {"model_provider", "deployment_target"})
    report = InternalBetaReadiness.evaluate(partial)
    assert report.ready is False
    assert report.missing == ("deployment_target", "model_provider")


def test_failed_required_check_blocks_readiness():
    values = list(checks())
    values[0] = ReadinessCheck(values[0].check_id, False, "failed")
    report = InternalBetaReadiness.evaluate(tuple(values))
    assert report.ready is False
    assert len(report.failed) == 1


def test_duplicate_check_ids_are_rejected():
    with pytest.raises(ValueError):
        InternalBetaReadiness.evaluate((ReadinessCheck("test_suite", True, "a"), ReadinessCheck("test_suite", True, "b")))
