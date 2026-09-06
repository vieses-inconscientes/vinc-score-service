from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Iterable, Mapping, Protocol

from .retrieval import ProvenanceBundle, RetrievalHit, RetrievalResult


@dataclass(frozen=True, slots=True)
class RetrievalEvalCase:
    case_id: str
    query_text: str
    expected_canonical_ids: frozenset[str]
    forbidden_canonical_ids: frozenset[str] = frozenset()
    allow_insufficient: bool = False

    def __post_init__(self) -> None:
        if not self.case_id or not self.query_text.strip():
            raise ValueError("case_id and query_text are required")
        if self.expected_canonical_ids & self.forbidden_canonical_ids:
            raise ValueError("expected and forbidden canonical IDs must be disjoint")
        if not self.expected_canonical_ids and not self.allow_insufficient:
            raise ValueError("cases without expected IDs must explicitly allow insufficiency")


@dataclass(frozen=True, slots=True)
class RetrievalEvalObservation:
    case_id: str
    hit_canonical_ids: tuple[str, ...]
    recall_at_k: float
    reciprocal_rank: float
    provenance_coverage: float
    forbidden_leak_count: int
    insufficiency_reason: str | None
    passed: bool


@dataclass(frozen=True, slots=True)
class RetrievalBenchmarkReport:
    observations: tuple[RetrievalEvalObservation, ...]
    macro_recall_at_k: float
    mean_reciprocal_rank: float
    provenance_coverage: float
    forbidden_leak_count: int
    failed_case_ids: tuple[str, ...]
    report_hash: str

    @property
    def passed(self) -> bool:
        return not self.failed_case_ids and self.forbidden_leak_count == 0 and self.provenance_coverage == 1.0


class ProvenanceResolver(Protocol):
    def resolve(self, hit: RetrievalHit) -> ProvenanceBundle | None: ...


class DeterministicRetrievalBenchmark:
    """R22 evaluation: deterministic retrieval/provenance checks without an LLM."""

    def __init__(self, *, minimum_recall_at_k: float = 1.0, minimum_mrr: float = 1.0) -> None:
        if not 0.0 <= minimum_recall_at_k <= 1.0 or not 0.0 <= minimum_mrr <= 1.0:
            raise ValueError("thresholds must be within [0, 1]")
        self._minimum_recall = minimum_recall_at_k
        self._minimum_mrr = minimum_mrr

    def evaluate(
        self,
        cases: Iterable[RetrievalEvalCase],
        results: Mapping[str, RetrievalResult],
        provenance: ProvenanceResolver,
    ) -> RetrievalBenchmarkReport:
        observations: list[RetrievalEvalObservation] = []
        total_provenance_hits = total_hits = 0
        total_rr = 0.0

        for case in cases:
            result = results.get(case.case_id)
            if result is None:
                observations.append(self._missing(case))
                continue

            ids = tuple(hit.canonical_id for hit in result.hits)
            expected = case.expected_canonical_ids
            found = expected.intersection(ids)
            recall = 1.0 if not expected and case.allow_insufficient else len(found) / len(expected)
            rr = self._reciprocal_rank(ids, expected)
            leaks = sum(1 for canonical_id in ids if canonical_id in case.forbidden_canonical_ids)

            provenance_ok = 0
            for hit in result.hits:
                bundle = provenance.resolve(hit)
                if (
                    bundle is not None
                    and bundle.canonical_id == hit.canonical_id
                    and bundle.asset_key == hit.asset_key
                    and bundle.source_revision_id == hit.source_revision_id
                    and bool(bundle.locator)
                    and bool(bundle.content_hash)
                ):
                    provenance_ok += 1

            coverage = 1.0 if not result.hits else provenance_ok / len(result.hits)
            insufficient_ok = (
                case.allow_insufficient
                and not expected
                and not result.hits
                and result.insufficiency_reason is not None
            )
            passed = (
                leaks == 0
                and coverage == 1.0
                and ((recall >= self._minimum_recall and rr >= self._minimum_mrr) or insufficient_ok)
            )

            observations.append(
                RetrievalEvalObservation(
                    case_id=case.case_id,
                    hit_canonical_ids=ids,
                    recall_at_k=recall,
                    reciprocal_rank=rr,
                    provenance_coverage=coverage,
                    forbidden_leak_count=leaks,
                    insufficiency_reason=result.insufficiency_reason,
                    passed=passed,
                )
            )
            total_rr += rr
            total_hits += len(result.hits)
            total_provenance_hits += provenance_ok

        count = len(observations)
        macro_recall = sum(obs.recall_at_k for obs in observations) / count if count else 0.0
        mrr = total_rr / count if count else 0.0
        provenance_coverage = 1.0 if total_hits == 0 else total_provenance_hits / total_hits
        leaks = sum(obs.forbidden_leak_count for obs in observations)
        failed = tuple(obs.case_id for obs in observations if not obs.passed)
        report_hash = self._hash(observations, macro_recall, mrr, provenance_coverage, leaks)
        return RetrievalBenchmarkReport(
            observations=tuple(observations),
            macro_recall_at_k=macro_recall,
            mean_reciprocal_rank=mrr,
            provenance_coverage=provenance_coverage,
            forbidden_leak_count=leaks,
            failed_case_ids=failed,
            report_hash=report_hash,
        )

    @staticmethod
    def _reciprocal_rank(ids: tuple[str, ...], expected: frozenset[str]) -> float:
        for rank, canonical_id in enumerate(ids, start=1):
            if canonical_id in expected:
                return 1.0 / rank
        return 1.0 if not expected else 0.0

    @staticmethod
    def _missing(case: RetrievalEvalCase) -> RetrievalEvalObservation:
        return RetrievalEvalObservation(case.case_id, (), 0.0, 0.0, 0.0, 0, "MISSING_RESULT", False)

    @staticmethod
    def _hash(
        observations: list[RetrievalEvalObservation],
        recall: float,
        mrr: float,
        provenance_coverage: float,
        leaks: int,
    ) -> str:
        rows = [
            f"{o.case_id}:{','.join(o.hit_canonical_ids)}:{o.recall_at_k:.6f}:{o.reciprocal_rank:.6f}:"
            f"{o.provenance_coverage:.6f}:{o.forbidden_leak_count}:{o.insufficiency_reason}:{o.passed}"
            for o in observations
        ]
        payload = "|".join(rows + [f"{recall:.6f}", f"{mrr:.6f}", f"{provenance_coverage:.6f}", str(leaks)])
        return sha256(payload.encode("utf-8")).hexdigest()
