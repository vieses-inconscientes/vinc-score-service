from vinc_agent.copilot import CopilotRequest, InternalCopilot
from vinc_agent.model_adapter import GuardedModelAdapter, ModelResponse
from vinc_agent.retrieval import CandidateFilter, ProvenanceBundle, ReadOnlyRetrievalService, RetrievalHit


class Policy:
    def filter_candidate_scope(self, request):
        return CandidateFilter(frozenset({"CAN_1"}), request.target_corpus, request.requester_scope, "policy")


class ReadModel:
    def __init__(self, hits=True): self.hits = hits
    def search_authorized(self, **kwargs):
        return [RetrievalHit("CHK_1", "CAN_1", "ASSET_1", "REV_1", .9, "evidencia", "sec:1")] if self.hits else []
    def resolve_current_provenance(self, chunk_id):
        return ProvenanceBundle("CAN_1", "ASSET_1", "REV_1", "sec:1", "https://example.invalid/can", "hash1")


class Provider:
    def __init__(self): self.calls = 0
    def generate(self, request):
        self.calls += 1
        return ModelResponse("resposta grounded", ("CHK_1",), "fake", "fake-v1", GuardedModelAdapter.bind_request_hash(request))


def make_copilot(hits=True):
    provider = Provider()
    retrieval = ReadOnlyRetrievalService(Policy(), ReadModel(hits))
    return InternalCopilot(retrieval, GuardedModelAdapter(provider)), provider


def test_alpha_answers_only_after_authorized_retrieval():
    copilot, provider = make_copilot(True)
    result = copilot.answer(CopilotRequest("q", "internal", "C"))
    assert result.answer.text == "resposta grounded"
    assert result.answer.citations[0].canonical_id == "CAN_1"
    assert provider.calls == 1


def test_alpha_abstains_without_authorized_hits_and_does_not_call_model():
    copilot, provider = make_copilot(False)
    result = copilot.answer(CopilotRequest("q", "internal", "C"))
    assert result.answer.abstained is True
    assert result.answer.insufficiency_reason == "ZERO_AUTHORIZED_HITS"
    assert provider.calls == 0


def test_trace_contains_only_hashes_ids_and_reason_not_corpus_text():
    copilot, _ = make_copilot(True)
    trace = copilot.answer(CopilotRequest("q", "internal", "C")).trace
    assert trace.evidence_chunk_ids == ("CHK_1",)
    assert trace.answer_hash is not None
    assert not hasattr(trace, "evidence_text")
