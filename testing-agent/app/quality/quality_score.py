"""Phase 7 deterministic quality score.

The score is a weighted average of five components, each normalised to 0.0-1.0
and derived exclusively from the gate metrics (no LLM, no randomness):

    component        weight   value
    ---------------  ------   ---------------------------------------------
    pass_rate          40     passed / executed          (executed = total - skipped)
    coverage           20     min(coverage_pct / min_coverage_threshold, 1)
    defects            20     1 - (0.50 * critical/high product findings
                                   + 0.25 * other product candidates)
    risk               12     1 - (0.50 * high-risk failures
                                   + 0.20 * medium-risk failures)
    flaky               8     1 - min(1, 2 * flaky_ratio)

Every component value is clamped to [0, 1]. Components whose backing gate is
NOT_EVALUATED are excluded and the remaining weights are renormalised, so a
missing input never silently inflates or deflates the score. When nothing at
all can be evaluated the score is 0.0 with `evaluated_weight == 0`.
"""
from typing import Dict

from app.quality.schemas import GateResult, GateStatus, QualityGatePolicy, QualityScore

PASS_RATE_WEIGHT = 40.0
COVERAGE_WEIGHT = 20.0
DEFECT_WEIGHT = 20.0
RISK_WEIGHT = 12.0
FLAKY_WEIGHT = 8.0

CRITICAL_DEFECT_PENALTY = 0.50
CANDIDATE_DEFECT_PENALTY = 0.25
HIGH_RISK_FAILURE_PENALTY = 0.50
MEDIUM_RISK_FAILURE_PENALTY = 0.20
FLAKY_RATIO_MULTIPLIER = 2.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def compute_quality_score(
    execution_gate: GateResult,
    coverage_gate: GateResult,
    risk_gate: GateResult,
    defect_gate: GateResult,
    flaky_gate: GateResult,
    policy: QualityGatePolicy,
) -> QualityScore:
    """Combine the gate metrics into a documented weighted score."""
    components: Dict[str, Dict] = {}

    def add(name: str, weight: float, gate: GateResult, value: float, detail: str) -> None:
        evaluated = gate.status is not GateStatus.NOT_EVALUATED
        value = _clamp(value) if evaluated else 0.0
        components[name] = {
            "weight": weight,
            "value": round(value, 4),
            "points": round(weight * value, 4) if evaluated else 0.0,
            "evaluated": evaluated,
            "detail": detail,
        }

    exec_metrics = execution_gate.metrics
    add(
        "pass_rate",
        PASS_RATE_WEIGHT,
        execution_gate,
        float(exec_metrics.get("pass_rate", 0.0) or 0.0),
        "passed / executed tests",
    )

    coverage_pct = coverage_gate.metrics.get("coverage_percentage")
    threshold = policy.min_coverage_percentage or 100.0
    add(
        "coverage",
        COVERAGE_WEIGHT,
        coverage_gate,
        (float(coverage_pct) / threshold) if coverage_pct is not None else 0.0,
        f"coverage vs {threshold:.1f}% threshold",
    )

    dm = defect_gate.metrics
    blocking = float(dm.get("critical_or_high_product_defects", 0) or 0)
    candidates = float(dm.get("product_defect_candidates", 0) or 0)
    other_candidates = max(candidates - blocking, 0.0)
    add(
        "defects",
        DEFECT_WEIGHT,
        defect_gate,
        1.0 - (CRITICAL_DEFECT_PENALTY * blocking + CANDIDATE_DEFECT_PENALTY * other_candidates),
        "penalised by product defect findings only",
    )

    rm = risk_gate.metrics
    add(
        "risk",
        RISK_WEIGHT,
        risk_gate,
        1.0
        - (
            HIGH_RISK_FAILURE_PENALTY * float(rm.get("high_risk_failures", 0) or 0)
            + MEDIUM_RISK_FAILURE_PENALTY * float(rm.get("medium_risk_failures", 0) or 0)
        ),
        "penalised by risk-weighted failures",
    )

    fm = flaky_gate.metrics
    add(
        "flaky",
        FLAKY_WEIGHT,
        flaky_gate,
        1.0 - FLAKY_RATIO_MULTIPLIER * float(fm.get("flaky_ratio", 0.0) or 0.0),
        "penalised by the observed flaky ratio",
    )

    evaluated_weight = sum(c["weight"] for c in components.values() if c["evaluated"])
    earned = sum(c["points"] for c in components.values() if c["evaluated"])
    score = round((earned / evaluated_weight) * 100.0, 2) if evaluated_weight else 0.0

    return QualityScore(score=score, components=components, evaluated_weight=evaluated_weight)
