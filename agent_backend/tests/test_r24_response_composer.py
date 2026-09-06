import pytest

from vinc_agent.model_adapter import GuardedModelAdapter, ModelResponse
from vinc_agent.response_composer import CompositionPolicyError, GroundedResponseComposer
from vinc_agent.retrieval import ProvenanceBundle, RetrievalHit, RetrievalResult


def hit():
    return RetrievalHit("CHK_1", "CAN_1", "ASSET_1", "REV_1", .9, "evidencia", "sec:1")


def prov():
    return ProvenanceBundle("CAN_1", "ASSET_1", "REV_1", "sec:1", "https://example.invalid/can", "hash1")


def test_builds_closed_context_from_hits_and_provenance():
    c = GroundedResponseComposer().build_context(query_text="q", requester_scope="internal", target_corpus="C", retrieval=RetrievalResult((hit(),), "qh", "fh"), provenance_by_chunk={"CHK_1": prov()})
    assert c.evidence[0].canonical_id == "CAN_1"


def test_rejects_insufficient_retrieval():
    with pytest.raises(CompositionPolicyError):
        GroundedResponseComposer().build_context(query_text="q", requester_scope="internal", target_corpus="C", retrieval=RetrievalResult((), "qh", "fh", "ZERO_AUTHORIZED_HITS"), provenance_by_chunk={})


def test_rejects_provenance_mismatch():
    bad = ProvenanceBundle("OTHER", "ASSET_1", "REV_1", "sec:1", None, "hash1")
    with pytest.raises(CompositionPolicyError):
        GroundedResponseComposer().build_context(query_text="q", requester_scope="internal", target_corpus="C", retrieval=RetrievalResult((hit(),), "qh", "fh"), provenance_by_chunk={"CHK_1": bad})


def test_composition_emits_reproducible_citation():
    composer = GroundedResponseComposer()
    ctx = composer.build_context(query_text="q", requester_scope="internal", target_corpus="C", retrieval=RetrievalResult((hit(),), "qh", "fh"), provenance_by_chunk={"CHK_1": prov()})
    req = composer.to_model_request(ctx)
    response = ModelResponse("resposta", ("CHK_1",), "fake", "m", GuardedModelAdapter.bind_request_hash(req))
    answer = composer.compose(context=ctx, response=response, provenance_by_chunk={"CHK_1": prov()})
    assert answer.citations[0].source_revision_id == "REV_1"
