from vinc_agent import __version__
from vinc_agent.domain import IngestionState, StableCode


def test_package_imports() -> None:
    assert __version__ == "0.1.0"
    assert IngestionState.REQUESTED.value == "REQUESTED"
    assert StableCode.N_NO_CHANGE.value == "N_NO_CHANGE"
