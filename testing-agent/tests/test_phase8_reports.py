"""Phase 8 report generation and export tests.

Deterministic, mock-only: no browser, no external API.
"""
import json
from fastapi.testclient import TestClient

from app.main import app
from app.reports.report_generator import ReportGenerator, generate_report
from app.reports.schemas import (
    AnalysisReportSection,
    ExportFormat,
    PhaseStatus,
    PhaseSummary,
    QualityGateReportSection,
    TestExecutionReportSection,
    TestReport,
    TraceabilityReportSection,
)


def _minimal_report() -> TestReport:
    return ReportGenerator().generate(project_id="test-project")


def _full_report() -> TestReport:
    return ReportGenerator().generate(
        project_id="full-project",
        requirements=[{"id": "REQ-001", "description": "Login", "category": "Functional", "source": "srs"}],
        risks=[{"risk_id": "RSK-001", "description": "Auth bypass", "severity": "High", "likelihood": "Medium", "mitigation": "Test", "source": "srs"}],
        coverage={"mapped_requirements": ["REQ-001"], "uncovered_requirements": [], "coverage_percentage": 100.0, "source": "srs"},
        test_cases=[{"test_case_id": "TC-001", "title": "Login test", "test_type": "unit", "test_category": "positive", "requirement_id": "REQ-001", "design_component": "auth", "code_target": "login()", "description": "Test login", "expected_result": "Success", "priority": "High", "source": "srs"}],
        test_scenarios=[{"scenario_id": "SCN-001", "title": "User login flow", "description": "Full login", "flow_steps": ["Open page", "Enter creds", "Submit"], "requirement_ids": ["REQ-001"], "related_test_case_ids": ["TC-001"], "source": "srs"}],
        generated_test_data=[{"data_id": "TD-001", "category": "valid", "description": "Valid creds", "linked_test_case_ids": ["TC-001"], "fields": [{"name": "user", "value": "admin", "description": "Admin user"}], "source": "srs"}],
        traceability={"entries": [{"requirement_id": "REQ-001", "scenario_id": "SCN-001", "test_case_id": "TC-001"}], "uncovered_requirements": [], "orphaned_test_cases": [], "orphaned_test_data": []},
        execution_results=[{"test_case_id": "TC-001", "status": "PASS", "duration": 0.5}],
        execution_summary={"total": 1, "pass": 1, "fail": 0, "error": 0, "skipped": 0},
        execution_status="completed",
        failure_analyses=[],
        root_cause_analyses=[],
        defect_analyses=[],
        flaky_analyses=[],
        quality_gate_report={"overall_status": "PASS", "gates": [{"gate": "execution", "status": "PASS"}]},
        quality_score=100.0,
        release_readiness="READY",
    )


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestReportSchemas:
    def test_export_format_enum(self):
        assert ExportFormat.JSON == "json"
        assert ExportFormat.HTML == "html"
        assert ExportFormat.CSV == "csv"

    def test_phase_status_enum(self):
        assert PhaseStatus.PASSED == "passed"
        assert PhaseStatus.FAILED == "failed"
        assert PhaseStatus.PARTIAL == "partial"
        assert PhaseStatus.SKIPPED == "skipped"

    def test_phase_summary_defaults(self):
        ps = PhaseSummary(phase_number=1, phase_name="Test", status=PhaseStatus.PASSED, summary="Done")
        assert ps.metrics == {}

    def test_execution_section_defaults(self):
        ex = TestExecutionReportSection()
        assert ex.total_tests == 0
        assert ex.pass_rate == 0.0

    def test_analysis_section_defaults(self):
        an = AnalysisReportSection()
        assert an.total_failures == 0
        assert an.failure_types == {}

    def test_quality_section_defaults(self):
        qg = QualityGateReportSection()
        assert qg.overall_status == "NOT_EVALUATED"

    def test_traceability_section_defaults(self):
        tr = TraceabilityReportSection()
        assert tr.total_entries == 0


# ---------------------------------------------------------------------------
# ReportGenerator tests
# ---------------------------------------------------------------------------

class TestReportGenerator:
    def test_minimal_report_has_all_fields(self):
        report = _minimal_report()
        assert report.project_id == "test-project"
        assert report.report_id.startswith("RPT-")
        assert len(report.phases) == 8
        assert report.phases[0].phase_name == "Input Validation & Context Loading"
        assert report.phases[7].phase_name == "Report Generation"
        assert report.executive_summary
        assert isinstance(report.recommendations, list)
        assert isinstance(report.raw_data, dict)

    def test_full_report_execution_metrics(self):
        report = _full_report()
        assert report.execution.total_tests == 1
        assert report.execution.passed == 1
        assert report.execution.pass_rate == 100.0
        assert report.execution.failed_test_ids == []
        assert report.execution.error_test_ids == []

    def test_full_report_analysis_metrics(self):
        report = _full_report()
        assert report.analysis.total_failures == 0
        assert report.analysis.product_defects == 0

    def test_full_report_quality_gate(self):
        report = _full_report()
        assert report.quality_gate.overall_status == "PASS"
        assert report.quality_gate.release_readiness == "READY"
        assert report.quality_gate.quality_score == 100.0

    def test_full_report_traceability(self):
        report = _full_report()
        assert report.traceability.total_entries == 1
        assert report.traceability.coverage_percentage == 100.0

    def test_full_report_recommendations(self):
        report = _full_report()
        assert "All quality gates passed. Consider releasing." in report.recommendations

    def test_executive_summary_contains_project_id(self):
        report = _full_report()
        assert "full-project" in report.executive_summary

    def test_phase_summaries_cover_all_8_phases(self):
        report = _full_report()
        phase_numbers = [p.phase_number for p in report.phases]
        assert phase_numbers == [1, 2, 3, 4, 5, 6, 7, 8]

    def test_raw_data_includes_all_inputs(self):
        report = _full_report()
        assert "requirements" in report.raw_data
        assert "risks" in report.raw_data
        assert "test_cases" in report.raw_data
        assert "quality_gate_report" in report.raw_data


# ---------------------------------------------------------------------------
# Export tests
# ---------------------------------------------------------------------------

class TestReportExport:
    def test_json_export_is_valid_json(self):
        report = _full_report()
        content = ReportGenerator().export(report, ExportFormat.JSON)
        parsed = json.loads(content)
        assert parsed["project_id"] == "full-project"

    def test_json_export_matches_model(self):
        report = _full_report()
        content = ReportGenerator().export_json(report)
        parsed = json.loads(content)
        assert parsed["report_id"] == report.report_id

    def test_html_export_contains_title(self):
        report = _full_report()
        content = ReportGenerator().export(report, ExportFormat.HTML)
        assert "<!DOCTYPE html>" in content
        assert "full-project" in content
        assert "<h1>Test Report" in content

    def test_html_export_contains_tables(self):
        report = _full_report()
        content = ReportGenerator().export(report, ExportFormat.HTML)
        assert "<table>" in content

    def test_csv_export_contains_sections(self):
        report = _full_report()
        content = ReportGenerator().export(report, ExportFormat.CSV)
        assert "Section" in content
        assert "Phase" in content
        assert "Execution" in content
        assert "QualityGate" in content

    def test_export_bytes_returns_bytes(self):
        report = _full_report()
        content = ReportGenerator().export_bytes(report, ExportFormat.JSON)
        assert isinstance(content, bytes)

    def test_unsupported_format_raises(self):
        report = _minimal_report()
        try:
            ReportGenerator().export(report, "xml")
            assert False, "Should have raised ValueError"
        except (ValueError, KeyError):
            pass


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------

class TestReportAPIIntegration:
    def test_execute_endpoint_returns_report_field(self, monkeypatch):
        from app.execution.controller import ExecutionController
        fake_report = {
            "run_id": "RUN-RPT",
            "started_at": "2024-01-01T00:00:00Z",
            "completed_at": "2024-01-01T00:00:01Z",
            "duration": 1.0,
            "platform": "test",
            "python_version": "3.10",
            "max_retries": 0,
            "max_workers": 1,
            "results": [{"test_case_id": "TC-1", "status": "PASS", "duration": 0.1, "attempts": 1, "logs": [], "attempts_detail": [], "artifacts": []}],
            "summary": {"total": 1, "pass": 1, "fail": 0, "error": 0, "skipped": 0},
        }
        monkeypatch.setattr(ExecutionController, "execute_test_suite", lambda self, cases: fake_report)

        client = TestClient(app)
        payload = {
            "project_id": "rpt-test",
            "srs": {"title": "SRS", "requirements": ["Login"]},
            "sdd": {"architecture": "Mono", "components": ["auth"]},
            "source_code": {"repo": "github.com/x/y", "language": "Python"},
        }
        resp = client.post("/testing/execute", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["report"] is not None
        assert body["report"]["project_id"] == "rpt-test"
        assert body["report"]["report_id"].startswith("RPT-")
        assert len(body["report"]["phases"]) == 8

    def test_report_generate_endpoint(self):
        client = TestClient(app)
        payload = {
            "project_id": "rpt-gen",
            "srs": {"title": "SRS", "requirements": ["Login"]},
            "sdd": {"architecture": "Mono", "components": ["auth"]},
            "source_code": {"repo": "github.com/x/y", "language": "Python"},
        }
        resp = client.post("/testing/report/generate", json=payload)
        assert resp.status_code == 200
        body = resp.json()
        assert body["project_id"] == "rpt-gen"
        assert body["report"] is not None
        assert body["report"]["report_id"].startswith("RPT-")

    def test_report_export_json_endpoint(self):
        client = TestClient(app)
        payload = {
            "project_id": "rpt-exp",
            "srs": {"title": "SRS", "requirements": ["Login"]},
            "sdd": {"architecture": "Mono", "components": ["auth"]},
            "source_code": {"repo": "github.com/x/y", "language": "Python"},
        }
        resp = client.post("/testing/report/export?fmt=json", json=payload)
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/json"
        body = resp.json()
        assert body["project_id"] == "rpt-exp"

    def test_report_export_html_endpoint(self):
        client = TestClient(app)
        payload = {
            "project_id": "rpt-html",
            "srs": {"title": "SRS", "requirements": ["Login"]},
            "sdd": {"architecture": "Mono", "components": ["auth"]},
            "source_code": {"repo": "github.com/x/y", "language": "Python"},
        }
        resp = client.post("/testing/report/export?fmt=html", json=payload)
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
        assert "rpt-html" in resp.text

    def test_report_export_csv_endpoint(self):
        client = TestClient(app)
        payload = {
            "project_id": "rpt-csv",
            "srs": {"title": "SRS", "requirements": ["Login"]},
            "sdd": {"architecture": "Mono", "components": ["auth"]},
            "source_code": {"repo": "github.com/x/y", "language": "Python"},
        }
        resp = client.post("/testing/report/export?fmt=csv", json=payload)
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]
        assert "Phase" in resp.text

    def test_report_export_pdf_endpoint(self):
        client = TestClient(app)
        payload = {
            "project_id": "rpt-pdf",
            "srs": {"title": "SRS", "requirements": ["Login"]},
            "sdd": {"architecture": "Mono", "components": ["auth"]},
            "source_code": {"repo": "github.com/x/y", "language": "Python"},
        }
        resp = client.post("/testing/report/export?fmt=pdf", json=payload)
        assert resp.status_code == 200
        assert "application/pdf" in resp.headers["content-type"]
        assert resp.content.startswith(b"%PDF")

    def test_report_export_docx_endpoint(self):
        client = TestClient(app)
        payload = {
            "project_id": "rpt-docx",
            "srs": {"title": "SRS", "requirements": ["Login"]},
            "sdd": {"architecture": "Mono", "components": ["auth"]},
            "source_code": {"repo": "github.com/x/y", "language": "Python"},
        }
        resp = client.post("/testing/report/export?fmt=docx", json=payload)
        assert resp.status_code == 200
        assert "officedocument.wordprocessingml" in resp.headers["content-type"]
        assert len(resp.content) > 100

    def test_report_export_unsupported_format(self):
        client = TestClient(app)
        payload = {
            "project_id": "rpt-bad",
            "srs": {"title": "SRS", "requirements": ["Login"]},
            "sdd": {"architecture": "Mono", "components": ["auth"]},
            "source_code": {"repo": "github.com/x/y", "language": "Python"},
        }
        resp = client.post("/testing/report/export?fmt=xml", json=payload)
        assert resp.status_code == 400
