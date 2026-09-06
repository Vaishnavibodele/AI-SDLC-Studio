"""Phase 7 gate evaluators.

Every gate is a pure function over evidence that already exists in the system:

* execution gate -> Phase 5 execution report
* coverage gate  -> Phase 2 `CoverageInfo`
* risk gate      -> Phase 2 `RiskInfo` + Phase 3 test cases/traceability + Phase 5 statuses
* defect gate    -> Phase 6 `DefectAnalysis`
* flaky gate     -> Phase 6 `FlakyTestAnalysis`

No gate invents evidence: when the backing evidence is absent the gate is
reported as `NOT_EVALUATED` rather than silently passing.
"""
from typing import Any, Dict, Iterable, List, Optional, Sequence

from app.analysis.schemas import DefectAnalysis, DefectClassification, FlakyTestAnalysis, Severity
from app.quality.schemas import GateResult, GateStatus, QualityGatePolicy

FAILED_STATUSES = {"FAIL", "ERROR"}
PRODUCT_CLASSIFICATIONS = {
    DefectClassification.PRODUCT_DEFECT,
    DefectClassification.PRODUCT_DEFECT_CANDIDATE,
}
BLOCKING_SEVERITIES = {Severity.CRITICAL, Severity.HIGH}


def _as_dict(obj: Any) -> Dict[str, Any]:
    """Accept pydantic models or plain dicts coming from TestingState."""
    if obj is None:
        return {}
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return dict(obj)
    return {}


def _as_dicts(items: Optional[Iterable[Any]]) -> List[Dict[str, Any]]:
    return [d for d in (_as_dict(i) for i in (items or [])) if d]


# ---------------------------------------------------------------- execution


def evaluate_execution_gate(
    summary: Optional[Dict[str, Any]],
    policy: QualityGatePolicy,
) -> GateResult:
    """Gate on raw Phase 5 execution counts."""
    summary = summary or {}
    total = int(summary.get("total", 0) or 0)
    passed = int(summary.get("pass", summary.get("passed", 0)) or 0)
    failed = int(summary.get("fail", summary.get("failed", 0)) or 0)
    errors = int(summary.get("error", summary.get("errors", 0)) or 0)
    skipped = int(summary.get("skipped", 0) or 0)

    executed = max(total - skipped, 0)
    failure_rate = (failed + errors) / executed if executed else 0.0
    pass_rate = passed / executed if executed else 0.0

    metrics = {
        "total": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "executed": executed,
        "failure_rate": round(failure_rate, 4),
        "pass_rate": round(pass_rate, 4),
    }

    if total == 0:
        return GateResult(
            name="execution",
            status=GateStatus.NOT_EVALUATED,
            summary="No tests were executed",
            metrics=metrics,
            warnings=["No execution evidence available; execution gate could not be evaluated"],
            recommendations=["Generate and execute test cases before requesting a release decision"],
        )

    if executed == 0:
        return GateResult(
            name="execution",
            status=GateStatus.NOT_EVALUATED,
            summary=f"All {total} test(s) were skipped",
            metrics=metrics,
            warnings=["Every test was skipped; no pass/fail evidence exists"],
            recommendations=["Provision the missing dependencies/environment so tests actually run"],
        )

    warnings: List[str] = []
    if skipped and total and skipped / total > policy.max_skipped_ratio:
        warnings.append(
            f"{skipped}/{total} tests were skipped (> {policy.max_skipped_ratio:.0%} of the suite)"
        )

    blocking: List[str] = []
    recommendations: List[str] = []
    if failure_rate <= policy.max_failure_rate:
        status = GateStatus.PASS
        gate_summary = f"{passed}/{executed} executed tests passed"
    elif failure_rate <= policy.conditional_failure_rate:
        status = GateStatus.CONDITIONAL
        gate_summary = f"{failed + errors}/{executed} executed tests failed ({failure_rate:.1%})"
        warnings.append(gate_summary)
        recommendations.append("Triage the failing tests before release")
    else:
        status = GateStatus.FAIL
        gate_summary = f"{failed + errors}/{executed} executed tests failed ({failure_rate:.1%})"
        blocking.append(
            f"Execution failure rate {failure_rate:.1%} exceeds the configured "
            f"{policy.conditional_failure_rate:.1%} limit"
        )
        recommendations.append("Fix the failing tests or the product defects behind them")

    return GateResult(
        name="execution",
        status=status,
        summary=gate_summary,
        metrics=metrics,
        blocking_issues=blocking,
        warnings=warnings,
        recommendations=recommendations,
        evidence=[f"summary: {metrics}"],
    )


# ----------------------------------------------------------------- coverage


def evaluate_coverage_gate(
    coverage: Any,
    policy: QualityGatePolicy,
) -> GateResult:
    """Gate on the Phase 2 requirement coverage information."""
    data = _as_dict(coverage)
    percentage = data.get("coverage_percentage")

    if percentage is None:
        result = GateResult(
            name="coverage",
            status=GateStatus.NOT_EVALUATED,
            summary="No requirement coverage evidence available",
            metrics={"coverage_percentage": None},
            recommendations=["Run the Phase 2 coverage analyzer to obtain requirement coverage"],
        )
        message = "Requirement coverage evidence is unavailable"
        if policy.require_coverage_evidence:
            result.status = GateStatus.FAIL
            result.blocking_issues.append(message)
        else:
            result.warnings.append(message)
        return result

    percentage = float(percentage)
    mapped = list(data.get("mapped_requirements") or [])
    uncovered = list(data.get("uncovered_requirements") or [])
    metrics = {
        "coverage_percentage": percentage,
        "min_coverage_percentage": policy.min_coverage_percentage,
        "covered_requirements": len(mapped),
        "uncovered_requirements": len(uncovered),
        "uncovered_requirement_ids": uncovered,
    }

    if percentage >= policy.min_coverage_percentage:
        return GateResult(
            name="coverage",
            status=GateStatus.PASS,
            summary=f"Requirement coverage {percentage:.1f}% meets the {policy.min_coverage_percentage:.1f}% threshold",
            metrics=metrics,
            evidence=[f"coverage_percentage={percentage}", f"uncovered={uncovered}"],
        )

    shortfall = (
        f"Requirement coverage {percentage:.1f}% is below the configured "
        f"{policy.min_coverage_percentage:.1f}% threshold"
    )
    if percentage >= policy.conditional_coverage_percentage:
        return GateResult(
            name="coverage",
            status=GateStatus.CONDITIONAL,
            summary=shortfall,
            metrics=metrics,
            warnings=[shortfall],
            recommendations=[f"Add coverage for {len(uncovered)} uncovered requirement(s)"],
            evidence=[f"coverage_percentage={percentage}", f"uncovered={uncovered}"],
        )

    return GateResult(
        name="coverage",
        status=GateStatus.FAIL,
        summary=shortfall,
        metrics=metrics,
        blocking_issues=[shortfall],
        recommendations=[f"Add coverage for {len(uncovered)} uncovered requirement(s)"],
        evidence=[f"coverage_percentage={percentage}", f"uncovered={uncovered}"],
    )


# --------------------------------------------------------------------- risk


def _requirement_severity(risks: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    order = {"low": 0, "medium": 1, "high": 2}
    severities: Dict[str, str] = {}
    for risk in risks:
        req = risk.get("requirement_id")
        sev = str(risk.get("severity") or "").lower()
        if not req or sev not in order:
            continue
        current = severities.get(req)
        if current is None or order[sev] > order[current]:
            severities[req] = sev
    return severities


def _risk_severity(risks: Sequence[Dict[str, Any]]) -> Dict[str, str]:
    return {
        r["risk_id"]: str(r.get("severity") or "").lower()
        for r in risks
        if r.get("risk_id")
    }


def evaluate_risk_gate(
    results: Optional[Sequence[Dict[str, Any]]],
    risks: Optional[Iterable[Any]],
    test_cases: Optional[Iterable[Any]],
    policy: QualityGatePolicy,
    traceability: Any = None,
) -> GateResult:
    """Weight failures by the Phase 2 risk severity of the requirement they cover."""
    risk_dicts = _as_dicts(risks)
    case_dicts = _as_dicts(test_cases)

    if not risk_dicts:
        return GateResult(
            name="risk",
            status=GateStatus.NOT_EVALUATED,
            summary="No risk information available",
            metrics={"high_risk_requirements": 0, "medium_risk_requirements": 0},
            warnings=["No Phase 2 risk evidence available; risk gate could not be evaluated"],
        )

    by_requirement = _requirement_severity(risk_dicts)
    by_risk_id = _risk_severity(risk_dicts)

    # test_case_id -> risk severity, via the test case itself or the traceability map
    case_severity: Dict[str, str] = {}
    entries = list(_as_dict(traceability).get("entries") or [])
    for source in (case_dicts, entries):
        for item in source:
            tcid = item.get("test_case_id")
            if not tcid:
                continue
            sev = by_risk_id.get(item.get("risk_id")) or by_requirement.get(item.get("requirement_id"))
            if sev and case_severity.get(tcid) != "high":
                case_severity[tcid] = sev

    failed_ids = [
        str(r.get("test_case_id"))
        for r in (results or [])
        if str(r.get("status", "")).upper() in FAILED_STATUSES
    ]

    high_failures = [t for t in failed_ids if case_severity.get(t) == "high"]
    medium_failures = [t for t in failed_ids if case_severity.get(t) == "medium"]
    unmapped_failures = [t for t in failed_ids if t not in case_severity]

    metrics = {
        "high_risk_requirements": sum(1 for s in by_requirement.values() if s == "high"),
        "medium_risk_requirements": sum(1 for s in by_requirement.values() if s == "medium"),
        "high_risk_failures": len(high_failures),
        "medium_risk_failures": len(medium_failures),
        "unresolved_high_risk_failures": high_failures,
        "failures_without_risk_mapping": len(unmapped_failures),
    }

    warnings: List[str] = []
    if unmapped_failures:
        warnings.append(
            f"{len(unmapped_failures)} failing test(s) could not be mapped to a risk; treated as unweighted"
        )

    if high_failures:
        issue = f"{len(high_failures)} failing test(s) cover high-risk requirements: {', '.join(sorted(high_failures))}"
        return GateResult(
            name="risk",
            status=GateStatus.FAIL,
            summary=issue,
            metrics=metrics,
            blocking_issues=[issue],
            warnings=warnings,
            recommendations=["Resolve the high-risk failures before release"],
            evidence=[f"high_risk_failures={sorted(high_failures)}"],
        )

    if medium_failures:
        issue = f"{len(medium_failures)} failing test(s) cover medium-risk requirements"
        return GateResult(
            name="risk",
            status=GateStatus.CONDITIONAL,
            summary=issue,
            metrics=metrics,
            warnings=warnings + [issue],
            recommendations=["Review the medium-risk failures and their mitigations"],
            evidence=[f"medium_risk_failures={sorted(medium_failures)}"],
        )

    return GateResult(
        name="risk",
        status=GateStatus.PASS,
        summary="No failing test is linked to a high or medium risk requirement",
        metrics=metrics,
        warnings=warnings,
    )


# ------------------------------------------------------------------- defect


def evaluate_defect_gate(
    defects: Optional[Sequence[DefectAnalysis]],
    policy: QualityGatePolicy,
) -> GateResult:
    """Only product defects / candidates can block; the other Phase 6
    classifications are surfaced as warnings."""
    defects = list(defects or [])

    product = [d for d in defects if d.classification in PRODUCT_CLASSIFICATIONS]
    confirmed = [d for d in product if d.classification is DefectClassification.PRODUCT_DEFECT]
    candidates = [d for d in product if d.classification is DefectClassification.PRODUCT_DEFECT_CANDIDATE]
    blocking_severity = [d for d in product if d.severity in BLOCKING_SEVERITIES]

    non_product: Dict[str, int] = {}
    for d in defects:
        if d.classification not in PRODUCT_CLASSIFICATIONS:
            non_product[d.classification.value] = non_product.get(d.classification.value, 0) + 1

    metrics = {
        "total_analyses": len(defects),
        "product_defects": len(confirmed),
        "product_defect_candidates": len(candidates),
        "critical_or_high_product_defects": len(blocking_severity),
        "non_product_findings": non_product,
    }
    warnings = [f"{count} {name.replace('_', ' ')} finding(s) (not product defects)" for name, count in sorted(non_product.items())]
    evidence = [f"{d.test_case_id}: {d.classification.value}/{d.severity.value} - {d.title}" for d in defects]

    if not product:
        return GateResult(
            name="defect",
            status=GateStatus.PASS,
            summary="No product defects or candidates detected",
            metrics=metrics,
            warnings=warnings,
            evidence=evidence,
        )

    recommendations = sorted({r for d in product for r in d.recommendations})

    if confirmed or blocking_severity:
        issues = [
            f"{d.classification.value} ({d.severity.value}) on {d.test_case_id}: {d.title}"
            for d in (confirmed or blocking_severity)
        ]
        return GateResult(
            name="defect",
            status=GateStatus.FAIL,
            summary=f"{len(confirmed or blocking_severity)} blocking product defect finding(s)",
            metrics=metrics,
            blocking_issues=issues,
            warnings=warnings,
            recommendations=recommendations,
            evidence=evidence,
        )

    issue = f"{len(candidates)} product defect candidate(s) require triage"
    result = GateResult(
        name="defect",
        status=GateStatus.CONDITIONAL if policy.allow_product_defect_candidates else GateStatus.FAIL,
        summary=issue,
        metrics=metrics,
        warnings=warnings,
        recommendations=recommendations,
        evidence=evidence,
    )
    if policy.allow_product_defect_candidates:
        result.warnings.append(issue)
    else:
        result.blocking_issues.append(issue)
    return result


# -------------------------------------------------------------------- flaky


def evaluate_flaky_gate(
    flaky_tests: Optional[Sequence[FlakyTestAnalysis]],
    total_tests: int,
    policy: QualityGatePolicy,
) -> GateResult:
    """Flaky tests reduce confidence but are never treated as product defects."""
    flaky = [f for f in (flaky_tests or []) if f.flaky]
    ratio = (len(flaky) / total_tests) if total_tests else 0.0
    metrics = {
        "flaky_tests": len(flaky),
        "total_tests": total_tests,
        "flaky_ratio": round(ratio, 4),
        "max_flaky_ratio": policy.max_flaky_ratio,
        "flaky_test_ids": [f.test_case_id for f in flaky],
    }
    evidence = [f"{f.test_case_id}: {f.observed_statuses} ({f.reason})" for f in flaky]

    if not flaky:
        return GateResult(
            name="flaky",
            status=GateStatus.PASS,
            summary="No flaky tests observed in the available execution history",
            metrics=metrics,
        )

    issue = f"{len(flaky)} flaky test(s) observed ({ratio:.1%} of the suite)"
    recommendations = ["Stabilise the flaky tests; they are not counted as product defects"]

    if ratio > policy.max_flaky_ratio:
        return GateResult(
            name="flaky",
            status=GateStatus.FAIL,
            summary=issue,
            metrics=metrics,
            blocking_issues=[
                f"Flaky ratio {ratio:.1%} exceeds the configured {policy.max_flaky_ratio:.1%} limit"
            ],
            recommendations=recommendations,
            evidence=evidence,
        )

    return GateResult(
        name="flaky",
        status=GateStatus.CONDITIONAL,
        summary=issue,
        metrics=metrics,
        warnings=[issue],
        recommendations=recommendations,
        evidence=evidence,
    )
