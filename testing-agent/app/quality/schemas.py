"""Phase 7 - Quality Gate & Release Readiness schemas.

These models are *additive*. They consume Phase 2 testing intelligence, the
Phase 5 execution report and the Phase 6 `ResultIntelligenceReport` without
redefining or mutating any of them.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GateStatus(str, Enum):
    """Outcome of a single quality gate."""

    PASS = "PASS"
    CONDITIONAL = "CONDITIONAL"
    FAIL = "FAIL"
    NOT_EVALUATED = "NOT_EVALUATED"


class ReleaseReadiness(str, Enum):
    """Aggregated release recommendation."""

    READY = "READY"
    CONDITIONAL = "CONDITIONAL"
    NOT_READY = "NOT_READY"


class QualityGatePolicy(BaseModel):
    """Configurable thresholds. Defaults are conservative, never hard-coded
    inside the gate logic itself."""

    __test__ = False

    min_coverage_percentage: float = Field(
        80.0, ge=0.0, le=100.0, description="Requirement coverage required for a PASS coverage gate"
    )
    conditional_coverage_percentage: float = Field(
        60.0, ge=0.0, le=100.0, description="Coverage below the minimum but at/above this yields CONDITIONAL"
    )
    require_coverage_evidence: bool = Field(
        False, description="When true, missing coverage evidence is a blocking issue instead of a warning"
    )
    max_failure_rate: float = Field(
        0.0, ge=0.0, le=1.0, description="Failure rate (fail+error over executed) allowed for a PASS execution gate"
    )
    conditional_failure_rate: float = Field(
        0.10, ge=0.0, le=1.0, description="Failure rate at/below which the execution gate is CONDITIONAL instead of FAIL"
    )
    max_skipped_ratio: float = Field(
        0.50, ge=0.0, le=1.0, description="Skipped ratio above which a warning is raised"
    )
    max_flaky_ratio: float = Field(
        0.25, ge=0.0, le=1.0, description="Flaky ratio above which the flaky gate FAILs instead of CONDITIONAL"
    )
    allow_product_defect_candidates: bool = Field(
        True,
        description="When true, non critical/high product defect candidates are CONDITIONAL rather than blocking",
    )
    min_quality_score_ready: float = Field(
        85.0, ge=0.0, le=100.0, description="Quality score required for READY"
    )
    min_quality_score_conditional: float = Field(
        60.0, ge=0.0, le=100.0, description="Quality score below which the release is NOT_READY"
    )


class GateResult(BaseModel):
    """Result of one gate. Metrics only ever contain observed evidence."""

    __test__ = False

    name: str
    status: GateStatus = GateStatus.NOT_EVALUATED
    summary: str
    metrics: Dict[str, Any] = Field(default_factory=dict)
    blocking_issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)


class QualityScore(BaseModel):
    """Deterministic weighted score. `components` documents every contribution."""

    __test__ = False

    score: float = Field(0.0, ge=0.0, le=100.0)
    components: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="component -> {weight, value, points, evaluated, detail}",
    )
    evaluated_weight: float = Field(0.0, description="Sum of weights of components with available evidence")


class QualityGateReport(BaseModel):
    """Aggregated Phase 7 report."""

    __test__ = False

    run_id: Optional[str] = None
    overall_status: GateStatus = GateStatus.NOT_EVALUATED
    release_readiness: ReleaseReadiness = ReleaseReadiness.NOT_READY
    quality_score: float = Field(0.0, ge=0.0, le=100.0)
    score_breakdown: QualityScore = Field(default_factory=QualityScore)
    execution_gate: GateResult
    coverage_gate: GateResult
    risk_gate: GateResult
    defect_gate: GateResult
    flaky_gate: GateResult
    blocking_issues: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    evidence: List[str] = Field(default_factory=list)
    policy: QualityGatePolicy = Field(default_factory=QualityGatePolicy)

    @property
    def gates(self) -> List[GateResult]:
        return [
            self.execution_gate,
            self.coverage_gate,
            self.risk_gate,
            self.defect_gate,
            self.flaky_gate,
        ]
