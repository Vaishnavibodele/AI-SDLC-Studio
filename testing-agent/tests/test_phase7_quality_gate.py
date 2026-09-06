"""Phase 7 quality gate / release readiness tests.

Deterministic, mock-only: no browser, no external API, no ticketing system.
"""
from fastapi.testclient import TestClient

from app.analysis.result_intelligence import analyze_execution_report
from app.analysis.schemas import (
    Confidence,
    DefectAnalysis,
    DefectClassification,
    FailureType,
    FlakyTestAnalysis,
    Priority,
    ResultIntelligenceReport,
    Severity,
)
from app.execution.controller import ExecutionController
from app.main import app
from app.quality.gates import evaluate_defect_gate, evaluate_flaky_gate
from app.quality.quality_gate import evaluate_quality_gate
from app.quality.quality_score import compute_quality_score
from app.quality.schemas import GateStatus, QualityGatePolicy, ReleaseReadiness

COVERAGE_FULL = {
    "mapped_requirements": ["REQ-001", "REQ-002"],
    "uncovered_requirements": [],
    "coverage_percentage": 100.0,
    "source": "srs",
}


def _result(**overrides):
    base = {
        "test_case_id": "TC-001",
        "run_id": "RUN-1",
        "name": "case",
        "status": "PASS",
        "details": "HTTP 200",
        "module": "api",
        "duration": 0.1,
        "attempts": 1,
        "logs": [],
        "attempts_detail": [],
        "artifacts": [],
    }
    base.update(overrides)
    return base


def _report(results):
    statuses = [r["status"] for r in results]
    return {
        "run_id": "RUN-1",
        "results": results,
        "summary": {
            "total": len(results),
            "pass": statuses.count("PASS"),
            "fail": statuses.count("FAIL"),
            "error": statuses.count("ERROR"),
            "skipped": statuses.count("SKIPPED"),
        },
    }


def _defect(**overrides) -> DefectAnalysis:
    base = dict(
        test_case_id="TC-001",
        defect_detected=True,
        classification=DefectClassification.PRODUCT_DEFECT,
        severity=Severity.CRITICAL,
        priority=Priority.P1,
        title="Server error on checkout",
        description="Endpoint responded 500",
        evidence=["Expected status 200, got 500"],
        confidence=Confidence.HIGH,
        failure_type=FailureType.HTTP_STATUS_MISMATCH,
        run_id="RUN-1",
    )
    base.update(overrides)
    return DefectAnalysis(**base)


def test_all_tests_passing_is_ready_and_pass():
    exec_report = _report([_result(test_case_id="TC-001"), _result(test_case_id="TC-002")])
    analysis = analyze_execution_report(exec_report)

    report = evaluate_quality_gate(
        execution_report=exec_report,
        analysis=analysis,
        coverage=COVERAGE_FULL,
        risks=[
            {
                "risk_id": "RSK-1",
                "requirement_id": "REQ-001",
                "severity": "High",
                "likelihood": "Medium",
                "description": "d",
                "mitigation": "m",
                "source": "srs",
            }
        ],
        test_cases=[{"test_case_id": "TC-001", "requirement_id": "REQ-001", "risk_id": "RSK-1"}],
    )

    assert report.overall_status is GateStatus.PASS
    assert report.release_readiness is ReleaseReadiness.READY
    assert report.quality_score == 100.0
    assert report.blocking_issues == []
    assert report.run_id == "RUN-1"


def test_critical_product_defect_blocks_release():
    analysis = ResultIntelligenceReport(run_id="RUN-1", analyzed_count=2, failures_analyzed=1, defects=[_defect()])
    exec_report = _report([_result(test_case_id="TC-001", status="FAIL"), _result(test_case_id="TC-002")])

    report = evaluate_quality_gate(
        execution_report=exec_report, analysis=analysis, coverage=COVERAGE_FULL
    )

    assert report.defect_gate.status is GateStatus.FAIL
    assert report.overall_status is GateStatus.FAIL
    assert report.release_readiness is ReleaseReadiness.NOT_READY
    assert any("product_defect" in issue for issue in report.blocking_issues)


def test_product_defect_candidate_is_conditional_by_default_and_blocking_under_strict_policy():
    candidate = _defect(
        classification=DefectClassification.PRODUCT_DEFECT_CANDIDATE,
        severity=Severity.MEDIUM,
        priority=Priority.P3,
    )
    analysis = ResultIntelligenceReport(run_id="RUN-1", defects=[candidate])
    exec_report = _report([_result(test_case_id="TC-001", status="FAIL"), _result(test_case_id="TC-002")])

    default_report = evaluate_quality_gate(
        execution_report=exec_report, analysis=analysis, coverage=COVERAGE_FULL
    )
    assert default_report.defect_gate.status is GateStatus.CONDITIONAL
    assert default_report.defect_gate.blocking_issues == []

    strict = evaluate_quality_gate(
        execution_report=exec_report,
        analysis=analysis,
        coverage=COVERAGE_FULL,
        policy=QualityGatePolicy(allow_product_defect_candidates=False),
    )
    assert strict.defect_gate.status is GateStatus.FAIL
    assert strict.release_readiness is ReleaseReadiness.NOT_READY


def test_high_risk_failure_has_stronger_impact_than_low_risk_failure():
    risks = [
        {
            "risk_id": "RSK-HIGH",
            "requirement_id": "REQ-001",
            "severity": "High",
            "likelihood": "High",
            "description": "d",
            "mitigation": "m",
            "source": "srs",
        },
        {
            "risk_id": "RSK-LOW",
            "requirement_id": "REQ-002",
            "severity": "Low",
            "likelihood": "Low",
            "description": "d",
            "mitigation": "m",
            "source": "srs",
        },
    ]
    test_cases = [
        {"test_case_id": "TC-HIGH", "requirement_id": "REQ-001", "risk_id": "RSK-HIGH"},
        {"test_case_id": "TC-LOW", "requirement_id": "REQ-002", "risk_id": "RSK-LOW"},
    ]

    def build(failing_id):
        results = [
            _result(test_case_id="TC-HIGH", status="FAIL" if failing_id == "TC-HIGH" else "PASS"),
            _result(test_case_id="TC-LOW", status="FAIL" if failing_id == "TC-LOW" else "PASS"),
        ]
        exec_report = _report(results)
        return evaluate_quality_gate(
            execution_report=exec_report,
            analysis=analyze_execution_report(exec_report),
            coverage=COVERAGE_FULL,
            risks=risks,
            test_cases=test_cases,
        )

    high = build("TC-HIGH")
    low = build("TC-LOW")

    assert high.risk_gate.status is GateStatus.FAIL
    assert high.risk_gate.metrics["high_risk_failures"] == 1
    assert high.release_readiness is ReleaseReadiness.NOT_READY
    assert low.risk_gate.status is GateStatus.PASS
    assert high.quality_score < low.quality_score


def test_insufficient_coverage_fails_and_partial_coverage_is_conditional():
    exec_report = _report([_result(test_case_id="TC-001")])
    analysis = analyze_execution_report(exec_report)

    low = evaluate_quality_gate(
        execution_report=exec_report,
        analysis=analysis,
        coverage={"mapped_requirements": ["REQ-001"], "uncovered_requirements": ["REQ-002", "REQ-003"], "coverage_percentage": 33.3, "source": "srs"},
    )
    assert low.coverage_gate.status is GateStatus.FAIL
    assert low.release_readiness is ReleaseReadiness.NOT_READY

    partial = evaluate_quality_gate(
        execution_report=exec_report,
        analysis=analysis,
        coverage={"mapped_requirements": ["REQ-001"], "uncovered_requirements": ["REQ-002"], "coverage_percentage": 70.0, "source": "srs"},
    )
    assert partial.coverage_gate.status is GateStatus.CONDITIONAL
    assert partial.release_readiness is ReleaseReadiness.CONDITIONAL


def test_coverage_threshold_is_configurable():
    exec_report = _report([_result(test_case_id="TC-001")])
    analysis = analyze_execution_report(exec_report)
    coverage = {"mapped_requirements": ["REQ-001"], "uncovered_requirements": [], "coverage_percentage": 70.0, "source": "srs"}

    relaxed = evaluate_quality_gate(
        execution_report=exec_report,
        analysis=analysis,
        coverage=coverage,
        policy=QualityGatePolicy(min_coverage_percentage=60.0),
    )
    assert relaxed.coverage_gate.status is GateStatus.PASS


def test_flaky_tests_reduce_quality_without_becoming_defects():
    flaky = FlakyTestAnalysis(
        test_case_id="TC-FLAKY",
        flaky=True,
        confidence=Confidence.HIGH,
        reason="Inconsistent outcomes",
        observed_statuses=["PASS", "FAIL", "PASS"],
        run_id="RUN-1",
    )
    analysis = ResultIntelligenceReport(run_id="RUN-1", flaky_tests=[flaky], flaky_tests_detected=1)
    exec_report = _report([_result(test_case_id=f"TC-{i}") for i in range(10)])

    report = evaluate_quality_gate(
        execution_report=exec_report, analysis=analysis, coverage=COVERAGE_FULL
    )

    assert report.flaky_gate.status is GateStatus.CONDITIONAL
    assert report.defect_gate.status is GateStatus.PASS
    assert report.release_readiness is ReleaseReadiness.CONDITIONAL
    assert report.quality_score < 100.0


def test_flaky_gate_fails_above_configured_ratio():
    flaky = [
        FlakyTestAnalysis(test_case_id=f"TC-{i}", flaky=True, reason="Inconsistent outcomes", observed_statuses=["PASS", "FAIL"])
        for i in range(3)
    ]
    gate = evaluate_flaky_gate(flaky, total_tests=4, policy=QualityGatePolicy())
    assert gate.status is GateStatus.FAIL
    assert gate.blocking_issues


def test_flaky_gate_is_safe_without_history():
    not_flaky = FlakyTestAnalysis(test_case_id="TC-001", flaky=False, reason="insufficient_history")
    gate = evaluate_flaky_gate([not_flaky], total_tests=1, policy=QualityGatePolicy())
    assert gate.status is GateStatus.PASS
    assert gate.metrics["flaky_tests"] == 0


def test_environment_issue_is_not_a_product_defect_block():
    exec_report = _report(
        [
            _result(
                test_case_id="TC-ENV",
                status="ERROR",
                module="ui",
                details="net::ERR_NAME_NOT_RESOLVED while loading http://example.local/",
            )
        ]
    )
    analysis = analyze_execution_report(exec_report)

    report = evaluate_quality_gate(
        execution_report=exec_report, analysis=analysis, coverage=COVERAGE_FULL
    )

    assert analysis.defects[0].classification is DefectClassification.ENVIRONMENT_ISSUE
    assert report.defect_gate.status is GateStatus.PASS
    assert report.defect_gate.metrics["product_defects"] == 0
    assert any("environment issue" in w for w in report.warnings)
    # The execution gate still reflects the failure itself
    assert report.execution_gate.status is GateStatus.FAIL


def test_test_configuration_issue_is_not_a_product_defect():
    exec_report = _report(
        [
            _result(
                test_case_id="TC-CFG",
                status="FAIL",
                module="unit",
                details="ERROR: file or directory not found: tests/test_generated.py::test_x",
            )
        ]
    )
    analysis = analyze_execution_report(exec_report)
    gate = evaluate_defect_gate(analysis.defects, QualityGatePolicy())

    assert analysis.defects[0].classification is DefectClassification.TEST_CONFIGURATION_ISSUE
    assert gate.status is GateStatus.PASS
    assert gate.metrics["non_product_findings"] == {"test_configuration_issue": 1}


def test_insufficient_evidence_is_handled_safely():
    report = evaluate_quality_gate(execution_report=None, analysis=None)

    assert report.execution_gate.status is GateStatus.NOT_EVALUATED
    assert report.coverage_gate.status is GateStatus.NOT_EVALUATED
    assert report.risk_gate.status is GateStatus.NOT_EVALUATED
    assert report.overall_status is GateStatus.CONDITIONAL
    assert report.release_readiness is ReleaseReadiness.NOT_READY
    assert report.quality_score == 0.0
    assert report.score_breakdown.components["coverage"]["evaluated"] is False


def test_missing_coverage_evidence_can_be_made_blocking():
    exec_report = _report([_result(test_case_id="TC-001")])
    analysis = analyze_execution_report(exec_report)

    report = evaluate_quality_gate(
        execution_report=exec_report,
        analysis=analysis,
        coverage=None,
        policy=QualityGatePolicy(require_coverage_evidence=True),
    )
    assert report.coverage_gate.status is GateStatus.FAIL
    assert report.release_readiness is ReleaseReadiness.NOT_READY


def test_quality_score_weighting_is_deterministic_and_documented():
    exec_report = _report([_result(test_case_id="TC-001"), _result(test_case_id="TC-002", status="FAIL", details="Expected status 200, got 500")])
    analysis = analyze_execution_report(exec_report)
    policy = QualityGatePolicy()

    first = evaluate_quality_gate(execution_report=exec_report, analysis=analysis, coverage=COVERAGE_FULL, policy=policy)
    second = evaluate_quality_gate(execution_report=exec_report, analysis=analysis, coverage=COVERAGE_FULL, policy=policy)
    assert first.quality_score == second.quality_score

    breakdown = compute_quality_score(
        first.execution_gate, first.coverage_gate, first.risk_gate, first.defect_gate, first.flaky_gate, policy
    )
    assert breakdown.score == first.quality_score
    # risk is not evaluated here, so its weight is excluded from the total
    assert breakdown.evaluated_weight == 40.0 + 20.0 + 20.0 + 8.0
    assert breakdown.components["pass_rate"]["value"] == 0.5
    assert breakdown.components["coverage"]["value"] == 1.0
    assert breakdown.components["defects"]["value"] == 0.5
    assert breakdown.components["risk"]["evaluated"] is False
    expected = round(((40.0 * 0.5) + 20.0 + (20.0 * 0.5) + 8.0) / 88.0 * 100.0, 2)
    assert breakdown.score == expected


def test_release_readiness_aggregation_orders_decisions():
    passing = _report([_result(test_case_id="TC-001")])
    ready = evaluate_quality_gate(
        execution_report=passing,
        analysis=analyze_execution_report(passing),
        coverage=COVERAGE_FULL,
        risks=[
            {
                "risk_id": "RSK-1",
                "requirement_id": "REQ-001",
                "severity": "High",
                "likelihood": "Medium",
                "description": "d",
                "mitigation": "m",
                "source": "srs",
            }
        ],
        test_cases=[{"test_case_id": "TC-001", "requirement_id": "REQ-001", "risk_id": "RSK-1"}],
    )
    conditional_report = _report([_result(test_case_id="TC-001"), _result(test_case_id="TC-002")])
    conditional = evaluate_quality_gate(
        execution_report=conditional_report,
        analysis=analyze_execution_report(conditional_report),
        coverage={"mapped_requirements": [], "uncovered_requirements": ["REQ-9"], "coverage_percentage": 65.0, "source": "srs"},
    )
    failing = _report([_result(test_case_id="TC-001", status="FAIL", details="Expected status 200, got 500")])
    not_ready = evaluate_quality_gate(
        execution_report=failing, analysis=analyze_execution_report(failing), coverage=COVERAGE_FULL
    )

    assert (ready.release_readiness, conditional.release_readiness, not_ready.release_readiness) == (
        ReleaseReadiness.READY,
        ReleaseReadiness.CONDITIONAL,
        ReleaseReadiness.NOT_READY,
    )
    assert not_ready.recommendations
    assert not_ready.evidence


def test_execute_endpoint_returns_quality_gate_and_preserves_phase_1_6_fields(monkeypatch):
    fake_report = {
        "run_id": "RUN-API",
        "started_at": "2024-01-01T00:00:00Z",
        "completed_at": "2024-01-01T00:00:01Z",
        "duration": 1.0,
        "platform": "test",
        "python_version": "3.10",
        "max_retries": 0,
        "max_workers": 1,
        "results": [
            _result(test_case_id="TC-OK", run_id="RUN-API"),
            _result(test_case_id="TC-BAD", run_id="RUN-API", status="FAIL", details="Expected status 200, got 500"),
        ],
        "summary": {"total": 2, "pass": 1, "fail": 1, "error": 0, "skipped": 0},
    }
    monkeypatch.setattr(ExecutionController, "execute_test_suite", lambda self, cases: fake_report)

    client = TestClient(app)
    payload = {
        "project_id": "phase7-demo",
        "srs": {"title": "SRS", "requirements": ["Users can log in"]},
        "sdd": {"architecture": "Monolith", "components": ["auth"]},
        "source_code": {"repository": "github.com/org/repo", "language": "Python"},
    }
    response = client.post("/testing/execute", json=payload)
    assert response.status_code == 200
    body = response.json()

    # Phase 4/5/6 response contract is untouched
    assert body["execution_status"] == "completed"
    assert body["execution_summary"] == {"total": 2, "passed": 1, "failed": 1, "errors": 0, "skipped": 0}
    assert len(body["results"]) == 2
    assert body["run_id"] == "RUN-API"
    assert body["analysis"]["failures_analyzed"] == 1

    gate = body["quality_gate"]
    assert gate["run_id"] == "RUN-API"
    assert set(
        ["overall_status", "release_readiness", "quality_score", "execution_gate", "coverage_gate",
         "risk_gate", "defect_gate", "flaky_gate", "blocking_issues", "warnings", "recommendations", "evidence"]
    ).issubset(gate.keys())
    assert gate["overall_status"] in {"PASS", "CONDITIONAL", "FAIL"}
    assert gate["release_readiness"] in {"READY", "CONDITIONAL", "NOT_READY"}
    assert gate["execution_gate"]["metrics"]["failed"] == 1
    assert gate["defect_gate"]["metrics"]["product_defect_candidates"] == 1
    assert gate["release_readiness"] == "NOT_READY"


def test_execute_endpoint_without_test_cases_still_returns_a_gate(monkeypatch):
    monkeypatch.setattr(ExecutionController, "execute_test_suite", lambda self, cases: {"results": [], "summary": {}})

    client = TestClient(app)
    payload = {
        "project_id": "phase7-empty",
        "srs": {"title": "SRS", "requirements": ["Users can log in"]},
        "sdd": {"architecture": "Monolith", "components": ["auth"]},
        "source_code": {"repository": "github.com/org/repo", "language": "Python"},
    }
    response = client.post("/testing/execute", json=payload)
    assert response.status_code == 200
    gate = response.json()["quality_gate"]
    assert gate is not None
    assert gate["release_readiness"] in {"READY", "CONDITIONAL", "NOT_READY"}
