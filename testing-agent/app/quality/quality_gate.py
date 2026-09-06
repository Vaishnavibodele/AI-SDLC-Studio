"""Phase 7 Quality Gate & Release Readiness layer.

    Phase 2 intelligence (coverage, risks)
    + Phase 5 execution report
    + Phase 6 ResultIntelligenceReport
            -> execution / coverage / risk / defect / flaky gates
            -> deterministic quality score
            -> QualityGateReport (overall status + release readiness)

The layer is deterministic, side-effect free and makes no LLM or network call.
It never mutates the reports it consumes.
"""
import logging
from typing import Any, Dict, Iterable, List, Optional

from app.analysis.schemas import ResultIntelligenceReport
from app.quality.gates import (
    evaluate_coverage_gate,
    evaluate_defect_gate,
    evaluate_execution_gate,
    evaluate_flaky_gate,
    evaluate_risk_gate,
)
from app.quality.quality_score import compute_quality_score
from app.quality.schemas import (
    GateResult,
    GateStatus,
    QualityGatePolicy,
    QualityGateReport,
    ReleaseReadiness,
)

logger = logging.getLogger(__name__)


def _dedupe(values: Iterable[str]) -> List[str]:
    seen: Dict[str, None] = {}
    for value in values:
        if value and value not in seen:
            seen[value] = None
    return list(seen)


def _overall_status(gates: List[GateResult]) -> GateStatus:
    statuses = {g.status for g in gates}
    if GateStatus.FAIL in statuses:
        return GateStatus.FAIL
    if GateStatus.CONDITIONAL in statuses or GateStatus.NOT_EVALUATED in statuses:
        return GateStatus.CONDITIONAL
    return GateStatus.PASS


def _release_readiness(
    overall: GateStatus,
    blocking_issues: List[str],
    score: float,
    policy: QualityGatePolicy,
) -> ReleaseReadiness:
    if overall is GateStatus.FAIL or blocking_issues:
        return ReleaseReadiness.NOT_READY
    if score < policy.min_quality_score_conditional:
        return ReleaseReadiness.NOT_READY
    if overall is GateStatus.CONDITIONAL or score < policy.min_quality_score_ready:
        return ReleaseReadiness.CONDITIONAL
    return ReleaseReadiness.READY


class QualityGate:
    """Single deterministic Phase 7 evaluation layer."""

    def evaluate(
        self,
        execution_report: Optional[Dict[str, Any]] = None,
        analysis: Optional[ResultIntelligenceReport] = None,
        coverage: Any = None,
        risks: Optional[Iterable[Any]] = None,
        test_cases: Optional[Iterable[Any]] = None,
        traceability: Any = None,
        policy: Optional[QualityGatePolicy] = None,
    ) -> QualityGateReport:
        policy = policy or QualityGatePolicy()
        report = execution_report or {}
        results = [r for r in (report.get("results") or []) if isinstance(r, dict)]
        summary = report.get("summary") or {}
        run_id = report.get("run_id") or (analysis.run_id if analysis else None)
        total = int(summary.get("total", len(results)) or 0)

        execution_gate = evaluate_execution_gate(summary or {"total": len(results)}, policy)
        coverage_gate = evaluate_coverage_gate(coverage, policy)
        risk_gate = evaluate_risk_gate(results, risks, test_cases, policy, traceability=traceability)
        defect_gate = evaluate_defect_gate(analysis.defects if analysis else [], policy)
        flaky_gate = evaluate_flaky_gate(analysis.flaky_tests if analysis else [], total, policy)

        # Without execution evidence the Phase 6 derived gates have nothing to
        # judge, so they must not report a PASS that would inflate the score.
        if execution_gate.status is GateStatus.NOT_EVALUATED:
            for gate in (defect_gate, flaky_gate):
                if gate.status is GateStatus.PASS:
                    gate.status = GateStatus.NOT_EVALUATED
                    gate.summary = "No execution evidence available"
                    gate.warnings.append(
                        f"{gate.name} gate could not be evaluated without execution evidence"
                    )

        gates = [execution_gate, coverage_gate, risk_gate, defect_gate, flaky_gate]

        breakdown = compute_quality_score(
            execution_gate, coverage_gate, risk_gate, defect_gate, flaky_gate, policy
        )

        blocking_issues = _dedupe(i for g in gates for i in g.blocking_issues)
        warnings = _dedupe(w for g in gates for w in g.warnings)
        recommendations = _dedupe(r for g in gates for r in g.recommendations)
        evidence = _dedupe(f"{g.name}: {g.summary}" for g in gates)

        overall = _overall_status(gates)
        readiness = _release_readiness(overall, blocking_issues, breakdown.score, policy)

        return QualityGateReport(
            run_id=run_id,
            overall_status=overall,
            release_readiness=readiness,
            quality_score=breakdown.score,
            score_breakdown=breakdown,
            execution_gate=execution_gate,
            coverage_gate=coverage_gate,
            risk_gate=risk_gate,
            defect_gate=defect_gate,
            flaky_gate=flaky_gate,
            blocking_issues=blocking_issues,
            warnings=warnings,
            recommendations=recommendations,
            evidence=evidence,
            policy=policy,
        )


quality_gate = QualityGate()


def evaluate_quality_gate(
    execution_report: Optional[Dict[str, Any]] = None,
    analysis: Optional[ResultIntelligenceReport] = None,
    coverage: Any = None,
    risks: Optional[Iterable[Any]] = None,
    test_cases: Optional[Iterable[Any]] = None,
    traceability: Any = None,
    policy: Optional[QualityGatePolicy] = None,
) -> QualityGateReport:
    """Module level helper mirroring `QualityGate.evaluate`."""
    return quality_gate.evaluate(
        execution_report=execution_report,
        analysis=analysis,
        coverage=coverage,
        risks=risks,
        test_cases=test_cases,
        traceability=traceability,
        policy=policy,
    )
