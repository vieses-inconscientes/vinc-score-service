from __future__ import annotations

from vinc_agent.retrieval import ProvenanceBundle, RetrievalHit, RetrievalResult
from vinc_agent.retrieval_eval import DeterministicRetrievalBenchmark, RetrievalEvalCase


def hit(canonical_id: str, chunk_id: str = "CHK_1") -> RetrievalHit:
    return RetrievalHit(chunk_id, canonical_id, "asset", "rev", 0.9, "text", "p:1")


def result(*hits: RetrievalHit, insufficient: str | None = None) -> RetrievalResult:
    return RetrievalResult(tuple(hits), "query-hash", "filter-hash", insufficient)


class Resolver:
    def __init__(self, broken: bool = False) -> None:
        self.broken = broken

    def resolve(self, retrieval_hit: RetrievalHit) -> ProvenanceBundle | None:
        if self.broken:
            return None
        return ProvenanceBundle(
            retrieval_hit.canonical_id,
            retrieval_hit.asset_key,
            retrieval_hit.source_revision_id,
            retrieval_hit.locator,
            None,
            "content-hash",
        )


def test_happy_path_and_explicit_insufficiency_pass() -> None:
    cases = [
        RetrievalEvalCase(
            "Q01",
            "carta fundacional",
            frozenset({"VINC-CAN-001"}),
            frozenset({"VINC-CAN-008"}),
        ),
        RetrievalEvalCase("Q02", "fora do corpus", frozenset(), allow_insufficient=True),
    ]
    report = DeterministicRetrievalBenchmark().evaluate(
        cases,
        {
            "Q01": result(hit("VINC-CAN-001")),
            "Q02": result(insufficient="ZERO_AUTHORIZED_HITS"),
        },
        Resolver(),
    )
    assert report.passed
    assert report.forbidden_leak_count == 0
    assert report.provenance_coverage == 1.0


def test_forbidden_canonical_leak_fails() -> None:
    case = RetrievalEvalCase(
        "Q01",
        "carta",
        frozenset({"VINC-CAN-001"}),
        frozenset({"VINC-CAN-008"}),
    )
    report = DeterministicRetrievalBenchmark().evaluate(
        [case],
        {"Q01": result(hit("VINC-CAN-001"), hit("VINC-CAN-008", "CHK_2"))},
        Resolver(),
    )
    assert not report.passed
    assert report.forbidden_leak_count == 1


def test_broken_provenance_fails() -> None:
    case = RetrievalEvalCase("Q01", "carta", frozenset({"VINC-CAN-001"}))
    report = DeterministicRetrievalBenchmark().evaluate(
        [case], {"Q01": result(hit("VINC-CAN-001"))}, Resolver(broken=True)
    )
    assert not report.passed
    assert report.provenance_coverage == 0.0


def test_expected_hit_below_required_rank_fails() -> None:
    case = RetrievalEvalCase("Q01", "carta", frozenset({"VINC-CAN-001"}))
    report = DeterministicRetrievalBenchmark(minimum_mrr=1.0).evaluate(
        [case],
        {"Q01": result(hit("VINC-CAN-009"), hit("VINC-CAN-001", "CHK_2"))},
        Resolver(),
    )
    assert not report.passed
    assert report.mean_reciprocal_rank == 0.5


def test_report_hash_is_deterministic() -> None:
    case = RetrievalEvalCase("Q01", "carta", frozenset({"VINC-CAN-001"}))
    inputs = {"Q01": result(hit("VINC-CAN-001"))}
    benchmark = DeterministicRetrievalBenchmark()
    first = benchmark.evaluate([case], inputs, Resolver())
    second = benchmark.evaluate([case], inputs, Resolver())
    assert first.report_hash == second.report_hash
