import pytest

from vinc_agent.model_adapter import (
    EvidenceExcerpt,
    GuardedModelAdapter,
    ModelPolicyError,
    ModelRequest,
    ModelResponse,
)


def evidence() -> EvidenceExcerpt:
    return EvidenceExcerpt(
        chunk_id="CHK_1",
        canonical_id="VINC-CAN-001",
        source_revision_id="REV_1",
        locator="section:principios",
        text="Conteúdo canônico autorizado.",
        content_hash="abc123",
    )


class FakeProvider:
    def __init__(self, cited=("CHK_1",), request_hash=None):
        self.cited = cited
        self.request_hash = request_hash
        self.calls = 0

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        return ModelResponse(
            text="Resposta grounded.",
            cited_chunk_ids=tuple(self.cited),
            provider="fake",
            model="fake-v1",
            request_hash=self.request_hash or GuardedModelAdapter.bind_request_hash(request),
        )


def test_requires_evidence_before_model_call():
    with pytest.raises(ModelPolicyError):
        ModelRequest("pergunta", "interno", "CORPUS_INTERNO", ())


def test_accepts_only_citations_inside_authorized_bundle():
    request = ModelRequest("pergunta", "interno", "CORPUS_INTERNO", (evidence(),))
    provider = FakeProvider(cited=("CHK_1",))
    response = GuardedModelAdapter(provider).generate(request)
    assert response.cited_chunk_ids == ("CHK_1",)
    assert provider.calls == 1


def test_rejects_uncited_generation():
    request = ModelRequest("pergunta", "interno", "CORPUS_INTERNO", (evidence(),))
    with pytest.raises(ModelPolicyError):
        GuardedModelAdapter(FakeProvider(cited=())).generate(request)


def test_rejects_citation_not_in_authorized_bundle():
    request = ModelRequest("pergunta", "interno", "CORPUS_INTERNO", (evidence(),))
    with pytest.raises(ModelPolicyError):
        GuardedModelAdapter(FakeProvider(cited=("CHK_HIST",))).generate(request)


def test_rejects_response_bound_to_different_request():
    request = ModelRequest("pergunta", "interno", "CORPUS_INTERNO", (evidence(),))
    with pytest.raises(ModelPolicyError):
        GuardedModelAdapter(FakeProvider(request_hash="wrong")).generate(request)
