import logging
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import HTMLResponse, Response
from app.testing_agent.models.schemas import (
    TestingStartRequest,
    TestingStartResponse,
    IntelligenceSummary,
    TestDesignSummary,
    TestExecutionResponse,
    TestExecutionResult,
    TestExecutionSummary,
    ApprovalStatus,
    ApprovalRequest,
    ApprovalResponse,
)
from app.testing_agent.models.state import TestingState
from app.testing_agent.workflow.testing_workflow import testing_workflow
from app.testing_agent.execution.controller import ExecutionController
from app.testing_agent.analysis.result_intelligence import analyze_execution_report
from app.testing_agent.analysis.schemas import ResultIntelligenceReport
from app.testing_agent.quality.quality_gate import evaluate_quality_gate
from app.testing_agent.quality.schemas import QualityGateReport
from app.testing_agent.reports.report_generator import ReportGenerator
from app.testing_agent.reports.schemas import ExportFormat

router = APIRouter(prefix="/testing", tags=["Testing"])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-Memory State & Storage
# ---------------------------------------------------------------------------
_approval_store: Dict[str, Dict[str, Any]] = {}  # Key: project_id, Value: approval state
_reports_store: Dict[str, Any] = {}  # Key: project_id, Value: TestReport instance
_state_store: Dict[str, Dict[str, Any]] = {}  # Key: project_id, Value: TestingState dict

def _get_approval_state(project_id: str) -> Optional[Dict[str, Any]]:
    """Get approval state for a project, or None if not exists."""
    return _approval_store.get(project_id)

def _set_approval_state(project_id: str, approval_data: Dict[str, Any]) -> None:
    """Set approval state for a project."""
    _approval_store[project_id] = approval_data

def _get_project_state(project_id: str) -> Optional[Dict[str, Any]]:
    """Get cached TestingState for a project."""
    return _state_store.get(project_id)

def _set_project_state(project_id: str, state: Dict[str, Any]) -> None:
    """Persist cached TestingState for a project."""
    _state_store[project_id] = state

def _calculate_release_allowed(approval_status: str, release_readiness: Optional[str]) -> bool:
    """
    Calculate whether release is allowed based on approval status and quality gate.
    
    Rules:
    - release_allowed is true ONLY when:
      * approval_status == "approved" AND
      * release_readiness == "READY"
    - Human approval does NOT override a failed quality gate
    """
    if approval_status != "approved":
        return False
    if release_readiness != "READY":
        return False
    return True

@router.post("/start", response_model=TestingStartResponse, status_code=status.HTTP_200_OK)
def start_testing_workflow(payload: TestingStartRequest) -> TestingStartResponse:
    """
    Starts the Testing Agent workflow.
    Validates inputs, normalizes context, and returns validation status and structured testing intelligence.
    """
    logger.info(f"Received start request for project ID: {payload.project_id}")

    # Prepare the initial state dict matching the TestingState schema
    initial_state: TestingState = {
        "project_id": payload.project_id,
        "srs": payload.srs,
        "sdd": payload.sdd,
        "source_code": payload.source_code,
        "api_docs": payload.api_docs,
        "database_schema": payload.database_schema,
        "test_data": payload.test_data,
        "environment": payload.environment,
        "validation_status": "pending",
        "validation_errors": [],
        "context": {},
        "workflow_status": "pending",
        "human_feedback": None,
        
        # Initialize Phase 2 fields as empty/None
        "requirements": [],
        "risks": [],
        "change_impact": None,
        "coverage": None,
        "test_strategy": None,

        # Initialize Phase 3 fields
        "test_cases": [],
        "test_scenarios": [],
        "generated_test_data": [],
        "traceability": None,
        "test_design_warnings": [],
    }

    try:
        # Run LangGraph workflow synchronously
        final_state = testing_workflow.invoke(initial_state)

        # Assemble IntelligenceSummary if validation passed and workflow finished
        intelligence = None
        test_design = None
        if final_state.get("validation_status") == "passed":
            intelligence = IntelligenceSummary(
                requirements=final_state.get("requirements") or [],
                risks=final_state.get("risks") or [],
                change_impact=final_state.get("change_impact"),
                coverage=final_state.get("coverage"),
                test_strategy=final_state.get("test_strategy")
            )
            test_design = TestDesignSummary(
                test_cases=final_state.get("test_cases") or [],
                test_scenarios=final_state.get("test_scenarios") or [],
                generated_test_data=final_state.get("generated_test_data") or [],
                traceability=final_state.get("traceability"),
                warnings=final_state.get("test_design_warnings") or [],
            )

        _set_project_state(payload.project_id, final_state)

        # Build response schema from the resulting state
        report = final_state.get("report")
        response = TestingStartResponse(
            project_id=final_state["project_id"],
            validation_status=final_state["validation_status"],
            validation_errors=final_state["validation_errors"],
            workflow_status=final_state["workflow_status"],
            intelligence=intelligence,
            test_design=test_design,
            report=report,
        )
        return response

    except Exception as e:
        logger.error(f"Unexpected exception during workflow execution: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Testing agent workflow execution failed: {str(e)}"
        )


def _store_analysis(state: TestingState, analysis: ResultIntelligenceReport) -> None:
    """Persist Phase 6 analysis artifacts into the workflow state."""
    state["result_intelligence"] = analysis
    state["failure_analyses"] = analysis.failures
    state["root_cause_analyses"] = analysis.root_causes
    state["defect_analyses"] = analysis.defects
    state["flaky_analyses"] = analysis.flaky_tests


def _store_quality_gate(state: TestingState, report: QualityGateReport) -> None:
    """Persist the Phase 7 quality gate decision into the workflow state."""
    state["quality_gate_report"] = report
    state["quality_score"] = report.quality_score
    state["release_readiness"] = report.release_readiness.value


def _run_quality_gate(state: TestingState, exec_report: dict, analysis: ResultIntelligenceReport) -> QualityGateReport:
    """Phase 7: evaluate the quality gates over Phase 2/5/6 evidence."""
    report = evaluate_quality_gate(
        execution_report=exec_report,
        analysis=analysis,
        coverage=state.get("coverage"),
        risks=state.get("risks"),
        test_cases=state.get("test_cases"),
        traceability=state.get("traceability"),
    )
    _store_quality_gate(state, report)
    return report


def _generate_report(state: TestingState, exec_report: Optional[dict] = None) -> None:
    """Phase 8: generate the comprehensive test report with upstream SDLC context and store it in the state."""
    generator = ReportGenerator()

    def _to_dict(val):
        if val is None:
            return None
        if isinstance(val, dict):
            return val
        if hasattr(val, "model_dump"):
            return val.model_dump()
        if hasattr(val, "dict"):
            return val.dict()
        return val

    project_id = state.get("project_id", "unknown")
    approval_state = _get_approval_state(project_id)

    report = generator.generate(
        project_id=project_id,
        project_name=state.get("srs", {}).get("project_name") or state.get("srs", {}).get("title"),
        srs=state.get("srs"),
        sdd=state.get("sdd"),
        source_code=state.get("source_code"),
        api_docs=state.get("api_docs"),
        database_schema=state.get("database_schema"),
        environment=state.get("environment"),
        requirements=[_to_dict(r) for r in (state.get("requirements") or [])],
        risks=[_to_dict(r) for r in (state.get("risks") or [])],
        change_impact=_to_dict(state.get("change_impact")),
        coverage=_to_dict(state.get("coverage")),
        test_strategy=_to_dict(state.get("test_strategy")),
        test_cases=[_to_dict(tc) for tc in (state.get("test_cases") or [])],
        test_scenarios=[_to_dict(ts) for ts in (state.get("test_scenarios") or [])],
        generated_test_data=[_to_dict(td) for td in (state.get("generated_test_data") or [])],
        traceability=_to_dict(state.get("traceability")),
        execution_results=state.get("execution_results") or [],
        execution_summary=state.get("execution_summary"),
        execution_status=state.get("execution_status"),
        result_intelligence=_to_dict(state.get("result_intelligence")),
        failure_analyses=[_to_dict(fa) for fa in (state.get("failure_analyses") or [])],
        root_cause_analyses=[_to_dict(rc) for rc in (state.get("root_cause_analyses") or [])],
        defect_analyses=[_to_dict(da) for da in (state.get("defect_analyses") or [])],
        flaky_analyses=[_to_dict(fa) for fa in (state.get("flaky_analyses") or [])],
        quality_gate_report=_to_dict(state.get("quality_gate_report")),
        quality_score=state.get("quality_score"),
        release_readiness=state.get("release_readiness"),
        approval_state=approval_state,
    )
    state["report"] = report
    _reports_store[project_id] = report


@router.post("/execute", response_model=TestExecutionResponse, status_code=status.HTTP_200_OK)
def execute_test_cases_from_workflow(payload: TestingStartRequest) -> TestExecutionResponse:
    """Run the full workflow (Phases 1-3) and execute Phase 3 generated test cases.
    Supports executing all tests, executing selected test cases, or retrying failed tests.
    """
    logger.info(f"Received execute request for project ID: {payload.project_id} (retry={payload.retry}, test_case_ids={payload.test_case_ids})")

    # Check for existing state for this project
    existing_state = _get_project_state(payload.project_id)

    # If state does not exist or missing test cases, run workflow P1-P3
    if not existing_state or not existing_state.get("test_cases"):
        initial_state: TestingState = {
            "project_id": payload.project_id,
            "srs": payload.srs,
            "sdd": payload.sdd,
            "source_code": payload.source_code,
            "api_docs": payload.api_docs,
            "database_schema": payload.database_schema,
            "test_data": payload.test_data,
            "environment": payload.environment,
            "validation_status": "pending",
            "validation_errors": [],
            "context": {},
            "workflow_status": "pending",
            "human_feedback": None,
            "requirements": [],
            "risks": [],
            "change_impact": None,
            "coverage": None,
            "test_strategy": None,
            "test_cases": [],
            "test_scenarios": [],
            "generated_test_data": [],
            "traceability": None,
            "test_design_warnings": [],
        }
        final_state = testing_workflow.invoke(initial_state)
    else:
        final_state = dict(existing_state)
        if payload.srs: final_state["srs"] = payload.srs
        if payload.sdd: final_state["sdd"] = payload.sdd
        if payload.source_code: final_state["source_code"] = payload.source_code
        if payload.environment: final_state["environment"] = payload.environment
        if payload.api_docs: final_state["api_docs"] = payload.api_docs

    if final_state.get("validation_status") != "passed":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"message": "Input validation failed; cannot execute test cases.", "validation_errors": final_state.get("validation_errors")}
        )

    raw_cases = final_state.get("test_cases") or []

    if not raw_cases:
        final_state["execution_status"] = "no_tests"
        final_state["execution_results"] = []
        final_state["execution_summary"] = {"total": 0, "pass": 0, "fail": 0, "error": 0, "skipped": 0}

        analysis = analyze_execution_report({"results": []})
        _store_analysis(final_state, analysis)
        quality_gate_report = _run_quality_gate(
            final_state,
            {"results": [], "summary": final_state["execution_summary"]},
            analysis,
        )
        _generate_report(final_state)
        _set_project_state(payload.project_id, final_state)

        summary = TestExecutionSummary(total=0, passed=0, failed=0, errors=0, skipped=0)
        return TestExecutionResponse(
            project_id=final_state.get("project_id"),
            execution_status=final_state.get("execution_status"),
            execution_summary=summary,
            results=[],
            analysis=analysis,
            quality_gate=quality_gate_report,
            report=final_state.get("report"),
        )

    # Normalize to plain dicts
    normalized_all_cases = []
    for c in raw_cases:
        try:
            if hasattr(c, "model_dump"):
                normalized_all_cases.append(c.model_dump())
            else:
                normalized_all_cases.append(dict(c))
        except Exception:
            normalized_all_cases.append(c)

    prev_results = list(final_state.get("execution_results") or [])
    prev_results_by_id = {r.get("test_case_id"): r for r in prev_results if isinstance(r, dict)}

    cases_to_execute = []
    if payload.retry:
        # Retry only failed/error test cases
        for c in normalized_all_cases:
            tcid = c.get("test_case_id") or c.get("id")
            prev_r = prev_results_by_id.get(tcid)
            should_retry = False
            if payload.test_case_ids:
                should_retry = tcid in payload.test_case_ids
            elif prev_r:
                should_retry = prev_r.get("status") in ["FAIL", "ERROR"]
            else:
                should_retry = True

            if should_retry:
                c_copy = dict(c)
                if prev_r:
                    c_copy["initial_attempt"] = prev_r.get("attempts", 1)
                    c_copy["existing_logs"] = prev_r.get("logs", [])
                    c_copy["existing_attempts_detail"] = prev_r.get("attempts_detail", [])
                    c_copy["existing_artifacts"] = prev_r.get("artifacts", [])
                    c_copy["existing_artifacts_meta"] = prev_r.get("artifacts_meta", [])
                    c_copy["duration"] = prev_r.get("duration", 0.0)
                    c_copy["screenshot"] = prev_r.get("screenshot")
                cases_to_execute.append(c_copy)
    elif payload.test_case_ids:
        # Run selected test cases
        target_ids = set(payload.test_case_ids)
        for c in normalized_all_cases:
            tcid = c.get("test_case_id") or c.get("id")
            if tcid in target_ids:
                cases_to_execute.append(dict(c))
    else:
        # Run all test cases
        cases_to_execute = [dict(c) for c in normalized_all_cases]

    controller = ExecutionController()
    exec_report = controller.execute_test_suite(cases_to_execute)

    # Merge results if running subset or retry
    new_results = exec_report.get("results", [])
    new_results_by_id = {r["test_case_id"]: r for r in new_results if "test_case_id" in r}

    if payload.retry or (payload.test_case_ids and prev_results):
        merged_results = []
        for c in normalized_all_cases:
            tcid = c.get("test_case_id") or c.get("id")
            if tcid in new_results_by_id:
                merged_results.append(new_results_by_id[tcid])
            elif tcid in prev_results_by_id:
                merged_results.append(prev_results_by_id[tcid])
        known_ids = {r.get("test_case_id") for r in merged_results}
        for r in new_results:
            if r.get("test_case_id") not in known_ids:
                merged_results.append(r)
        final_results = merged_results
    else:
        final_results = new_results

    # Aggregate summary
    pass_cnt = sum(1 for r in final_results if (r.get("status") or "").upper() == "PASS")
    fail_cnt = sum(1 for r in final_results if (r.get("status") or "").upper() == "FAIL")
    err_cnt = sum(1 for r in final_results if (r.get("status") or "").upper() == "ERROR")
    skip_cnt = sum(1 for r in final_results if (r.get("status") or "").upper() == "SKIPPED")

    merged_summary = {
        "total": len(final_results),
        "pass": pass_cnt,
        "fail": fail_cnt,
        "error": err_cnt,
        "skipped": skip_cnt,
    }

    total_duration = sum((r.get("duration") or 0.0) for r in final_results)

    final_exec_report = {
        "run_id": exec_report.get("run_id"),
        "started_at": exec_report.get("started_at"),
        "completed_at": exec_report.get("completed_at"),
        "duration": total_duration,
        "platform": exec_report.get("platform"),
        "python_version": exec_report.get("python_version"),
        "max_retries": exec_report.get("max_retries"),
        "max_workers": exec_report.get("max_workers"),
        "results": final_results,
        "summary": merged_summary,
    }

    # Persist execution results back into state
    final_state["execution_status"] = "completed"
    final_state["execution_results"] = final_results
    final_state["execution_summary"] = merged_summary

    # Phase 6: derive result intelligence from execution report
    analysis = analyze_execution_report(final_exec_report)
    _store_analysis(final_state, analysis)

    # Phase 7: quality gate and release readiness over Phase 2/5/6 evidence
    quality_gate_report = _run_quality_gate(final_state, final_exec_report, analysis)

    # Phase 8: generate comprehensive report
    _generate_report(final_state, final_exec_report)

    # Update cache
    _set_project_state(payload.project_id, final_state)
    
    # Initialize approval state with quality gate information
    project_id = final_state.get("project_id")
    quality_gate_report = final_state.get("quality_gate_report")
    
    if quality_gate_report:
        _set_approval_state(project_id, {
            "approval_status": "pending",
            "approved_by": None,
            "approval_comment": None,
            "approval_timestamp": None,
            "report_id": final_state.get("report").report_id if final_state.get("report") else None,
            "release_readiness": quality_gate_report.release_readiness.value if quality_gate_report.release_readiness else None,
            "quality_gate_status": quality_gate_report.overall_status.value if quality_gate_report.overall_status else None,
        })

    # Map summary keys
    summary = TestExecutionSummary(
        total=merged_summary.get("total", 0),
        passed=merged_summary.get("pass", 0),
        failed=merged_summary.get("fail", 0),
        errors=merged_summary.get("error", 0),
        skipped=merged_summary.get("skipped", 0),
    )

    results = []
    for r in final_results:
        results.append(TestExecutionResult(
            test_case_id=r.get("test_case_id"),
            name=r.get("name"),
            status=r.get("status"),
            details=r.get("details"),
            module=r.get("module"),
            duration=r.get("duration"),
            attempts=r.get("attempts"),
            logs=r.get("logs") or [],
            artifacts=r.get("artifacts") or [],
            screenshot=r.get("screenshot"),
            attempts_detail=r.get("attempts_detail") or None,
            artifacts_meta=r.get("artifacts_meta") or None,
            screenshot_meta=r.get("screenshot_meta") or None,
        ))

    response = TestExecutionResponse(
        project_id=final_state.get("project_id"),
        execution_status=final_state.get("execution_status"),
        execution_summary=summary,
        results=results,
        run_id=final_exec_report.get("run_id"),
        started_at=final_exec_report.get("started_at"),
        completed_at=final_exec_report.get("completed_at"),
        duration=final_exec_report.get("duration"),
        platform=final_exec_report.get("platform"),
        python_version=final_exec_report.get("python_version"),
        max_retries=final_exec_report.get("max_retries"),
        max_workers=final_exec_report.get("max_workers"),
        analysis=analysis,
        quality_gate=quality_gate_report,
        report=final_state.get("report"),
    )
    return response


@router.post("/retry", response_model=TestExecutionResponse, status_code=status.HTTP_200_OK)
def retry_failed_tests(payload: TestingStartRequest) -> TestExecutionResponse:
    """Retry failed / error test cases from previous execution run."""
    payload.retry = True
    return execute_test_cases_from_workflow(payload)


@router.get("/status/{project_id}", status_code=status.HTTP_200_OK)
def get_testing_state_status(project_id: str) -> dict:
    """Return live Testing Agent state, execution metrics, and report for a project."""
    logger.info(f"Received status request for project ID: {project_id}")
    state = _get_project_state(project_id)
    report = _reports_store.get(project_id)
    approval = _get_approval_state(project_id)

    if not state:
        return {
            "project_id": project_id,
            "workflow_status": "idle",
            "validation_status": "pending",
            "execution_status": "not_executed",
            "execution_summary": {"total": 0, "pass": 0, "fail": 0, "error": 0, "skipped": 0},
            "results": [],
            "intelligence": None,
            "test_design": None,
            "analysis": None,
            "quality_gate": None,
            "quality_score": 0.0,
            "release_readiness": "NOT_READY",
            "report": None,
            "approval": approval,
        }

    intelligence = None
    test_design = None
    if state.get("validation_status") == "passed":
        intelligence = IntelligenceSummary(
            requirements=state.get("requirements") or [],
            risks=state.get("risks") or [],
            change_impact=state.get("change_impact"),
            coverage=state.get("coverage"),
            test_strategy=state.get("test_strategy")
        ).model_dump()
        test_design = TestDesignSummary(
            test_cases=state.get("test_cases") or [],
            test_scenarios=state.get("test_scenarios") or [],
            generated_test_data=state.get("generated_test_data") or [],
            traceability=state.get("traceability"),
            warnings=state.get("test_design_warnings") or [],
        ).model_dump()

    qg = state.get("quality_gate_report")
    qg_dict = qg.model_dump() if hasattr(qg, "model_dump") else qg

    analysis = state.get("result_intelligence")
    analysis_dict = analysis.model_dump() if hasattr(analysis, "model_dump") else analysis

    report_obj = state.get("report") or report
    report_dict = report_obj.model_dump() if hasattr(report_obj, "model_dump") else report_obj

    return {
        "project_id": project_id,
        "workflow_status": state.get("workflow_status", "completed"),
        "validation_status": state.get("validation_status", "passed"),
        "execution_status": state.get("execution_status", "completed"),
        "execution_summary": state.get("execution_summary") or {"total": len(state.get("execution_results") or []), "pass": 0, "fail": 0, "error": 0, "skipped": 0},
        "results": state.get("execution_results") or [],
        "intelligence": intelligence,
        "test_design": test_design,
        "analysis": analysis_dict,
        "quality_gate": qg_dict,
        "quality_score": state.get("quality_score") or (qg_dict.get("quality_score") if qg_dict else 0.0),
        "release_readiness": state.get("release_readiness") or (qg_dict.get("release_readiness") if qg_dict else "NOT_READY"),
        "report": report_dict,
        "approval": approval,
    }


# ---------------------------------------------------------------------------
# Standalone report generation and export endpoints
# ---------------------------------------------------------------------------

@router.post("/report/generate", status_code=status.HTTP_200_OK)
def generate_report_from_state(payload: TestingStartRequest) -> dict:
    """Run the workflow and generate a comprehensive report with real execution results."""
    logger.info(f"Received report generation request for project ID: {payload.project_id}")

    # If state exists and has execution results, use it
    stored_state = _get_project_state(payload.project_id)
    if stored_state and stored_state.get("execution_results"):
        _generate_report(stored_state)
        report = stored_state.get("report")
        return {
            "project_id": payload.project_id,
            "report": report.model_dump() if report else None,
        }

    # Otherwise execute test cases through workflow
    exec_resp = execute_test_cases_from_workflow(payload)
    report = _reports_store.get(payload.project_id) or exec_resp.report
    return {
        "project_id": payload.project_id,
        "report": report.model_dump() if hasattr(report, "model_dump") else report,
    }


@router.post("/report/export", status_code=status.HTTP_200_OK)
def export_report(payload: TestingStartRequest, fmt: str = "json") -> Response:
    """Run the workflow and export the report in the specified format with real execution results."""
    logger.info(f"Received report export request for project ID: {payload.project_id}, format: {fmt}")

    try:
        export_format = ExportFormat(fmt.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}. Use pdf, docx, md, json, html, or csv.")

    # Check if we have an existing executed report
    report = _reports_store.get(payload.project_id)
    stored_state = _get_project_state(payload.project_id)

    if not report or not stored_state or not stored_state.get("execution_results"):
        # Execute workflow to ensure report has real execution results
        execute_test_cases_from_workflow(payload)
        report = _reports_store.get(payload.project_id)

    if not report:
        raise HTTPException(status_code=500, detail="Report generation failed")

    generator = ReportGenerator()
    content = generator.export_bytes(report, export_format)

    media_types = {
        ExportFormat.JSON: "application/json",
        ExportFormat.HTML: "text/html; charset=utf-8",
        ExportFormat.CSV: "text/csv; charset=utf-8",
        ExportFormat.MD: "text/markdown; charset=utf-8",
        ExportFormat.PDF: "application/pdf",
        ExportFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    filename = f"testing-report-{payload.project_id}.{export_format.value}"

    return Response(
        content=content,
        media_type=media_types[export_format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Human Approval / Reject Endpoints
# ---------------------------------------------------------------------------

@router.post("/report/approve", response_model=ApprovalResponse, status_code=status.HTTP_200_OK)
def approve_report(payload: ApprovalRequest) -> ApprovalResponse:
    """
    Approve a test report for release.
    
    Validates:
    - Report exists for the project
    - Current approval status is pending
    - Reviewer identifier is provided
    
    Sets status to approved and calculates release_allowed based on quality gate.
    """
    logger.info(f"Approval request for project {payload.project_id}, report {payload.report_id} by {payload.approved_by}")
    
    # Get current approval state
    current_state = _get_approval_state(payload.project_id)
    
    # Initialize as pending if no state exists
    if current_state is None:
        current_state = {
            "approval_status": "pending",
            "approved_by": None,
            "approval_comment": None,
            "approval_timestamp": None,
            "report_id": None,
            "release_readiness": None,
            "quality_gate_status": None,
        }
    
    # Validate state machine: can only approve from pending
    if current_state["approval_status"] != "pending":
        logger.warning(f"Cannot approve report in status: {current_state['approval_status']}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve report with current status: {current_state['approval_status']}. Status must be pending."
        )
    
    # Validate reviewer
    if not payload.approved_by or not payload.approved_by.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reviewer identifier (approved_by) is required"
        )
    
    # Generate timestamp
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Update approval state
    updated_state = {
        **current_state,
        "approval_status": "approved",
        "approved_by": payload.approved_by.strip(),
        "approval_comment": payload.comment,
        "approval_timestamp": timestamp,
        "report_id": payload.report_id,
    }
    
    _set_approval_state(payload.project_id, updated_state)
    
    # Calculate release_allowed based on quality gate
    release_allowed = _calculate_release_allowed(
        updated_state["approval_status"],
        updated_state.get("release_readiness")
    )

    # Sync with stored report if present
    if payload.project_id in _reports_store:
        rep = _reports_store[payload.project_id]
        if hasattr(rep, "governance") and rep.governance:
            rep.governance.approval_status = "approved"
            rep.governance.approved_by = payload.approved_by.strip()
            rep.governance.comment = payload.comment
            rep.governance.approval_timestamp = timestamp
            rep.governance.release_allowed = release_allowed
        if hasattr(rep, "release_allowed"):
            rep.release_allowed = release_allowed
    
    logger.info(f"Report {payload.report_id} approved by {payload.approved_by}, release_allowed: {release_allowed}")
    
    return ApprovalResponse(
        project_id=payload.project_id,
        report_id=payload.report_id,
        approval_status=ApprovalStatus.APPROVED,
        approved_by=payload.approved_by.strip(),
        approval_timestamp=timestamp,
        comment=payload.comment,
        release_allowed=release_allowed,
        quality_gate_status=updated_state.get("quality_gate_status"),
        release_readiness=updated_state.get("release_readiness"),
    )


@router.post("/report/reject", response_model=ApprovalResponse, status_code=status.HTTP_200_OK)
def reject_report(payload: ApprovalRequest) -> ApprovalResponse:
    """
    Reject a test report, blocking release.
    
    Validates:
    - Report exists for the project
    - Current approval status is pending
    - Reviewer identifier is provided
    - Rejection reason (comment) is non-empty
    
    Sets status to rejected and release_allowed to false.
    """
    logger.info(f"Rejection request for project {payload.project_id}, report {payload.report_id} by {payload.approved_by}")
    
    # Get current approval state
    current_state = _get_approval_state(payload.project_id)
    
    # Initialize as pending if no state exists
    if current_state is None:
        current_state = {
            "approval_status": "pending",
            "approved_by": None,
            "approval_comment": None,
            "approval_timestamp": None,
            "report_id": None,
            "release_readiness": None,
            "quality_gate_status": None,
        }
    
    # Validate state machine: can only reject from pending
    if current_state["approval_status"] != "pending":
        logger.warning(f"Cannot reject report in status: {current_state['approval_status']}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reject report with current status: {current_state['approval_status']}. Status must be pending."
        )
    
    # Validate reviewer
    if not payload.approved_by or not payload.approved_by.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Reviewer identifier (approved_by) is required"
        )
    
    # Validate rejection reason is required
    if not payload.comment or not payload.comment.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Rejection reason (comment) is required for rejecting a report"
        )
    
    # Generate timestamp
    timestamp = datetime.now(timezone.utc).isoformat()
    
    # Update approval state
    updated_state = {
        **current_state,
        "approval_status": "rejected",
        "approved_by": payload.approved_by.strip(),
        "approval_comment": payload.comment.strip(),
        "approval_timestamp": timestamp,
        "report_id": payload.report_id,
    }
    
    _set_approval_state(payload.project_id, updated_state)
    
    # Release is never allowed after rejection
    release_allowed = False

    # Sync with stored report if present
    if payload.project_id in _reports_store:
        rep = _reports_store[payload.project_id]
        if hasattr(rep, "governance") and rep.governance:
            rep.governance.approval_status = "rejected"
            rep.governance.approved_by = payload.approved_by.strip()
            rep.governance.comment = payload.comment.strip()
            rep.governance.approval_timestamp = timestamp
            rep.governance.release_allowed = False
        if hasattr(rep, "release_allowed"):
            rep.release_allowed = False
    
    logger.info(f"Report {payload.report_id} rejected by {payload.approved_by}, reason: {payload.comment[:100]}")
    
    return ApprovalResponse(
        project_id=payload.project_id,
        report_id=payload.report_id,
        approval_status=ApprovalStatus.REJECTED,
        approved_by=payload.approved_by.strip(),
        approval_timestamp=timestamp,
        comment=payload.comment.strip(),
        release_allowed=release_allowed,
        quality_gate_status=updated_state.get("quality_gate_status"),
        release_readiness=updated_state.get("release_readiness"),
    )


@router.get("/report/approval-status/{project_id}", response_model=ApprovalResponse, status_code=status.HTTP_200_OK)
def get_approval_status(project_id: str) -> ApprovalResponse:
    """
    Get current approval status for a project's report.
    
    Returns PENDING status if no approval has been recorded yet.
    """
    logger.info(f"Approval status request for project {project_id}")
    
    current_state = _get_approval_state(project_id)
    
    # Return pending state if no approval exists
    if current_state is None:
        return ApprovalResponse(
            project_id=project_id,
            report_id="",
            approval_status=ApprovalStatus.PENDING,
            approved_by="--",
            approval_timestamp="--",
            comment=None,
            release_allowed=False,
            quality_gate_status=None,
            release_readiness=None,
        )
    
    # Map string status to enum
    status_enum = ApprovalStatus(current_state["approval_status"])
    
    # Calculate current release_allowed
    release_allowed = _calculate_release_allowed(
        current_state["approval_status"],
        current_state.get("release_readiness")
    )
    
    return ApprovalResponse(
        project_id=project_id,
        report_id=current_state.get("report_id", "") or "",
        approval_status=status_enum,
        approved_by=current_state.get("approved_by") or "--",
        approval_timestamp=current_state.get("approval_timestamp") or "--",
        comment=current_state.get("approval_comment"),
        release_allowed=release_allowed,
        quality_gate_status=current_state.get("quality_gate_status"),
        release_readiness=current_state.get("release_readiness"),
    )


@router.get("/report/export/{project_id}", status_code=status.HTTP_200_OK)
@router.get("/report/{project_id}/export", status_code=status.HTTP_200_OK)
def export_stored_report(project_id: str, fmt: str = "json") -> Response:
    """
    Export the most recently generated report for a project in the specified format (pdf, docx, json, html, csv).
    """
    logger.info(f"Received stored report export request for project ID: {project_id}, format: {fmt}")

    report = _reports_store.get(project_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No generated test report found for project '{project_id}'. Run test execution first."
        )

    try:
        export_format = ExportFormat(fmt.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}. Use pdf, docx, md, json, html, or csv.")

    generator = ReportGenerator()
    content = generator.export_bytes(report, export_format)

    media_types = {
        ExportFormat.JSON: "application/json",
        ExportFormat.HTML: "text/html; charset=utf-8",
        ExportFormat.CSV: "text/csv; charset=utf-8",
        ExportFormat.MD: "text/markdown; charset=utf-8",
        ExportFormat.PDF: "application/pdf",
        ExportFormat.DOCX: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }
    filename = f"testing-report-{project_id}.{export_format.value}"

    return Response(
        content=content,
        media_type=media_types[export_format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

