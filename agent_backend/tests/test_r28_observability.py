from vinc_agent.copilot import CopilotRequest
from vinc_agent.observability import CopilotMetrics
from test_r25_r26_copilot import make_copilot


def test_answered_metric_contains_only_hashes_counts_and_ids_derived_state():
    copilot, _ = make_copilot(True)
    result = copilot.answer(CopilotRequest("conteudo sensivel", "internal", "C"))
    event = CopilotMetrics.from_trace(result.trace, abstained=result.answer.abstained)
    assert event.outcome == "ANSWERED"
    assert event.evidence_count == 1
    assert event.answer_hash is not None
    assert not hasattr(event, "query_text")
    assert not hasattr(event, "answer_text")
    assert not hasattr(event, "evidence_text")


def test_abstention_metric_preserves_reason_without_model_text():
    copilot, _ = make_copilot(False)
    result = copilot.answer(CopilotRequest("q", "internal", "C"))
    event = CopilotMetrics.from_trace(result.trace, abstained=result.answer.abstained)
    assert event.outcome == "ABSTAINED"
    assert event.answer_hash is None
    assert event.abstention_reason == "ZERO_AUTHORIZED_HITS"
