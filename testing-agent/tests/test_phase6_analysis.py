"""Phase 6 result intelligence tests.

All tests are deterministic and rely on mocked Phase 5 execution reports; no
browser, network, or external service is required.
"""
from fastapi.testclient import TestClient

from app.analysis import defect_analyzer, failure_analyzer, flaky_test_analyzer, root_cause_analyzer
from app.analysis.result_intelligence import analyze_execution_report
from app.analysis.schemas import (
    INSUFFICIENT_EVIDENCE_SUMMARY,
    INSUFFICIENT_HISTORY_REASON,
    UNKNOWN_ROOT_CAUSE,
    Confidence,
    DefectClassification,
    FailureType,
    RootCauseCategory,
)
from app.execution.controller import ExecutionController
from app.main import app


def _result(**overrides):
    base = {
        "test_case_id": "TC-001",
        "run_id": "RUN-1",
        "name": "case",
        "status": "FAIL",
        "details": "",
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
    return {"run_id": "RUN-1", "results": results, "summary": {"total": len(results)}}


def test_pass_and_skipped_results_are_ignored_by_failure_analysis():
    results = [
        _result(test_case_id="TC-P", status="PASS", details="HTTP 200"),
        _result(test_case_id="TC-S", status="SKIPPED", details="httpx not installed"),
    ]
    assert failure_analyzer.analyze_results(results) == []


def test_fail_creates_failure_analysis():
    analyses = failure_analyzer.analyze_results(
        [_result(status="FAIL", details="AssertionError: expected value 5")]
    )
    assert len(analyses) == 1
    assert analyses[0].status == "FAIL"
    assert analyses[0].failure_type is FailureType.ASSERTION_FAILURE
    assert analyses[0].evidence == ["AssertionError: expected value 5"]


def test_error_creates_root_cause_analysis():
    analyses = failure_analyzer.analyze_results(
        [_result(status="ERROR", module="unit", details="Timeout: pytest run exceeded 300s")]
    )
    root_causes = root_cause_analyzer.analyze_failures(analyses)
    assert len(root_causes) == 1
    assert root_causes[0].failure_type is FailureType.TIMEOUT
    assert root_causes[0].category is RootCauseCategory.ENVIRONMENT
    assert root_causes[0].probable_root_cause != UNKNOWN_ROOT_CAUSE


def test_http_status_mismatch_is_classified():
    analysis = failure_analyzer.analyze_result(_result(details="Expected status 200, got 500"))
    assert analysis.failure_type is FailureType.HTTP_STATUS_MISMATCH
    assert analysis.expected_behavior == "HTTP 200"
    assert analysis.observed_behavior == "HTTP 500"
    assert analysis.confidence is Confidence.HIGH


def test_err_name_not_resolved_is_classified_as_browser_network_error():
    analysis = failure_analyzer.analyze_result(
        _result(
            status="ERROR",
            module="ui",
            details="WebDriverException: unknown error: net::ERR_NAME_NOT_RESOLVED",
        )
    )
    assert analysis.failure_type is FailureType.BROWSER_NETWORK_ERROR

    root_cause = root_cause_analyzer.analyze_failure(analysis)
    assert "resolved" in root_cause.probable_root_cause.lower()
    assert root_cause.category is RootCauseCategory.ENVIRONMENT
    assert root_cause.confidence is Confidence.HIGH


def test_invalid_pytest_target_is_classified():
    analysis = failure_analyzer.analyze_result(
        _result(
            status="FAIL",
            module="unit",
            details="ERROR: file or directory not found: tests/test_generated.py::test_x",
        )
    )
    assert analysis.failure_type is FailureType.INVALID_PYTEST_TARGET

    defect = defect_analyzer.analyze_failure(analysis)
    assert defect.classification is DefectClassification.TEST_CONFIGURATION_ISSUE
    assert defect.defect_detected is False


def test_environment_failure_is_not_a_product_defect():
    analysis = failure_analyzer.analyze_result(
        _result(
            status="ERROR",
            module="ui",
            details="net::ERR_NAME_NOT_RESOLVED while loading http://example.local/",
        )
    )
    defect = defect_analyzer.analyze_failure(analysis)
    assert defect.classification is DefectClassification.ENVIRONMENT_ISSUE
    assert defect.defect_detected is False


def test_product_defect_candidate_is_identified():
    analysis = failure_analyzer.analyze_result(_result(details="Expected status 200, got 500"))
    defect = defect_analyzer.analyze_failure(analysis)
    assert defect.classification is DefectClassification.PRODUCT_DEFECT_CANDIDATE
    assert defect.defect_detected is True
    assert defect.recommendations


def test_test_defect_is_distinguishable_from_product_defect():
    selector_analysis = failure_analyzer.analyze_result(
        _result(
            status="ERROR",
            module="ui",
            details="NoSuchElementException: Unable to locate element: #submit-btn",
        )
    )
    server_analysis = failure_analyzer.analyze_result(
        _result(test_case_id="TC-002", details="Expected status 201, got 500")
    )

    selector_defect = defect_analyzer.analyze_failure(selector_analysis)
    server_defect = defect_analyzer.analyze_failure(server_analysis)

    assert selector_defect.classification is DefectClassification.TEST_DEFECT
    assert selector_defect.defect_detected is False
    assert server_defect.classification is DefectClassification.PRODUCT_DEFECT_CANDIDATE
    assert server_defect.defect_detected is True


def test_test_data_issue_is_classified_for_rejected_payloads():
    analysis = failure_analyzer.analyze_result(_result(details="Expected status 201, got 422"))
    defect = defect_analyzer.analyze_failure(analysis)
    assert defect.classification is DefectClassification.TEST_DATA_ISSUE
    assert defect.defect_detected is False


def test_flaky_detection_requires_real_history():
    single = _result(status="FAIL", attempts=1, attempts_detail=[{"status": "FAIL"}])
    analysis = flaky_test_analyzer.analyze_result(single)
    assert analysis.flaky is False
    assert analysis.reason == INSUFFICIENT_HISTORY_REASON
    assert analysis.observed_statuses == ["FAIL"]


def test_repeated_inconsistent_results_are_potentially_flaky():
    result = _result(
        status="PASS",
        attempts=3,
        attempts_detail=[{"status": "PASS"}, {"status": "FAIL"}, {"status": "PASS"}],
    )
    analysis = flaky_test_analyzer.analyze_result(result)
    assert analysis.flaky is True
    assert analysis.observed_statuses == ["PASS", "FAIL", "PASS"]
    assert analysis.confidence is Confidence.HIGH


def test_flaky_detection_uses_supplied_history():
    history = [_report([_result(status="PASS", attempts_detail=[{"status": "PASS"}])])]
    current = _result(status="FAIL", attempts_detail=[{"status": "FAIL"}])
    analysis = flaky_test_analyzer.analyze_result(current, history=history)
    assert analysis.flaky is True
    assert analysis.observed_statuses == ["PASS", "FAIL"]


def test_insufficient_evidence_is_handled_safely():
    analysis = failure_analyzer.analyze_result(_result(status="FAIL", details=None))
    assert analysis.failure_type is FailureType.UNKNOWN
    assert analysis.failure_summary == INSUFFICIENT_EVIDENCE_SUMMARY

    root_cause = root_cause_analyzer.analyze_failure(analysis)
    assert root_cause.probable_root_cause == UNKNOWN_ROOT_CAUSE
    assert root_cause.confidence is Confidence.LOW

    defect = defect_analyzer.analyze_failure(analysis, root_cause)
    assert defect.classification is DefectClassification.UNKNOWN
    assert defect.defect_detected is False


def test_result_intelligence_report_aggregation():
    results = [
        _result(test_case_id="TC-P", status="PASS", details="HTTP 200"),
        _result(test_case_id="TC-F", status="FAIL", details="Expected status 200, got 500"),
        _result(
            test_case_id="TC-E",
            status="ERROR",
            module="ui",
            details="net::ERR_NAME_NOT_RESOLVED",
        ),
        _result(
            test_case_id="TC-FLAKY",
            status="PASS",
            attempts=3,
            attempts_detail=[{"status": "FAIL"}, {"status": "ERROR"}, {"status": "PASS"}],
        ),
    ]

    report = analyze_execution_report(_report(results))

    assert report.run_id == "RUN-1"
    assert report.analyzed_count == 4
    assert report.failures_analyzed == 2
    assert report.defects_detected == 1
    assert report.flaky_tests_detected == 1
    assert {f.test_case_id for f in report.failures} == {"TC-F", "TC-E"}
    assert len(report.root_causes) == 2
    assert len(report.defects) == 2
    assert report.flaky_tests[0].test_case_id == "TC-FLAKY"


def test_analysis_never_changes_execution_statuses():
    payload = _report([_result(status="FAIL", details="Expected status 200, got 500")])
    analyze_execution_report(payload)
    assert payload["results"][0]["status"] == "FAIL"


def test_execute_endpoint_returns_analysis(monkeypatch):
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
            _result(test_case_id="TC-OK", run_id="RUN-API", status="PASS", details="HTTP 200"),
            _result(
                test_case_id="TC-BAD",
                run_id="RUN-API",
                status="FAIL",
                details="Expected status 200, got 500",
            ),
        ],
        "summary": {"total": 2, "pass": 1, "fail": 1, "error": 0, "skipped": 0},
    }

    monkeypatch.setattr(ExecutionController, "execute_test_suite", lambda self, cases: fake_report)

    client = TestClient(app)
    payload = {
        "project_id": "phase6-demo",
        "srs": {"title": "SRS", "requirements": ["Users can log in"]},
        "sdd": {"architecture": "Monolith", "components": ["auth"]},
        "source_code": {"repository": "github.com/org/repo", "language": "Python"},
    }
    response = client.post("/testing/execute", json=payload)
    assert response.status_code == 200

    body = response.json()
    # Backwards compatibility: existing Phase 4/5 execution fields are preserved
    assert body["execution_status"] == "completed"
    assert body["execution_summary"]["total"] == 2
    assert len(body["results"]) == 2
    assert body["run_id"] == "RUN-API"

    analysis = body["analysis"]
    assert analysis["run_id"] == "RUN-API"
    assert analysis["analyzed_count"] == 2
    assert analysis["failures_analyzed"] == 1
    assert analysis["defects_detected"] == 1
    assert analysis["flaky_tests_detected"] == 0
    assert analysis["failures"][0]["test_case_id"] == "TC-BAD"
    assert analysis["failures"][0]["failure_type"] == "http_status_mismatch"
    assert analysis["root_causes"][0]["category"] == "application_code"
    assert analysis["defects"][0]["classification"] == "product_defect_candidate"
    assert analysis["flaky_tests"] == []
