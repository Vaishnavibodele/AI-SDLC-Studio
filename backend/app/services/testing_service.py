import json
import datetime
import concurrent.futures
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from .. import models, schemas
from . import project_service, development_service
from ..agents.testing_agent import run_testing_agent, register_running_process, unregister_running_process, kill_running_process

TEST_TIMEOUT_SECONDS = 120  # Default hard execution limit

def start_testing_execution(db: Session, project_id: str, timeout_seconds: int = TEST_TIMEOUT_SECONDS) -> Dict[str, Any]:
    # 1. Validate Phase
    project = project_service.get_project(db, project_id)
    if not project:
        raise ValueError("Project not found")
    if project.current_phase != "TESTING":
        raise ValueError(f"PHASE_LOCKED: Testing is locked. Current phase is {project.current_phase}.")

    # 2. Check for active RUNNING execution (Concurrency Guard)
    active_run = db.query(models.TestingReport).filter(
        models.TestingReport.project_id == project_id,
        models.TestingReport.execution_state == "RUNNING"
    ).first()
    if active_run:
        raise ValueError("TEST_ALREADY_RUNNING: A testing execution is already running for this project.")

    # 3. Get latest development version
    dev_version = development_service.get_latest_development_version(db, project_id)
    if not dev_version or dev_version.approval_status != "APPROVED":
        raise ValueError("Linked project codebase (Development) must be approved before testing execution.")

    # Determine version number
    last_report = db.query(models.TestingReport).filter(
        models.TestingReport.project_id == project_id
    ).order_by(models.TestingReport.version_num.desc()).first()
    version_num = (last_report.version_num + 1) if last_report else 1

    # 4. FIRST DB WRITE: Write execution_state = "RUNNING" & started_at before spawning process
    started_now = datetime.datetime.utcnow()
    report = models.TestingReport(
        project_id=project_id,
        development_version_id=dev_version.id,
        version_num=version_num,
        execution_state="RUNNING",
        status=None,
        raw_report=None,
        approval_status="PENDING",
        started_at=started_now
    )
    db.add(report)
    project.status = "IN_PROGRESS"
    db.commit()
    db.refresh(report)

    report_id = report.id
    project_service.log_activity(
        db, 
        project_id, 
        "TESTING_STARTED", 
        f"Testing execution run v{version_num} started with state RUNNING."
    )

    # 5. Run execution with hard timeout & exception wrapping
    def _execute():
        return run_testing_agent(db, project_id, dev_version.id)

    report_data = None
    fault_state = None
    fault_msg = None

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_execute)
            report_data = future.result(timeout=timeout_seconds)
    except concurrent.futures.TimeoutError:
        fault_state = "TIMED_OUT"
        fault_msg = f"exceeded {timeout_seconds}s execution limit"
        kill_running_process(project_id)
    except Exception as ex:
        # Check if it was stopped/aborted externally
        db.refresh(report)
        if report.execution_state == "ABORTED":
            return {
                "execution_state": "ABORTED",
                "fault_reason": report.fault_reason or "stopped by user",
                "summary": "Testing execution stopped by user."
            }
        
        fault_state = "CRASHED"
        fault_msg = f"Unhandled testing runtime exception: {str(ex)}"
        kill_running_process(project_id)

    ended_now = datetime.datetime.utcnow()

    # Re-fetch report row cleanly
    rep_to_update = db.query(models.TestingReport).filter(models.TestingReport.id == report_id).first()
    if not rep_to_update:
        raise ValueError("TestingReport record lost during execution.")

    # Check if user clicked STOP while thread was finishing
    if rep_to_update.execution_state == "ABORTED":
        return {
            "execution_state": "ABORTED",
            "fault_reason": rep_to_update.fault_reason or "stopped by user",
            "summary": "Testing execution stopped by user."
        }

    if fault_state:
        # Handle TIMED_OUT or CRASHED (Terminal-but-unresolved, NO phase transition)
        rep_to_update.execution_state = fault_state
        rep_to_update.fault_reason = fault_msg
        rep_to_update.ended_at = ended_now
        db.commit()

        project_service.log_activity(
            db, project_id, f"TESTING_{fault_state}", f"Testing run v{version_num} {fault_state}: {fault_msg}"
        )
        return {
            "execution_state": fault_state,
            "fault_reason": fault_msg,
            "summary": f"Testing suite execution {fault_state.lower()}: {fault_msg}."
        }

    # 6. Validate JSON Schema before writing COMPLETED
    try:
        raw_json_str = json.dumps(report_data)
        # Quick validation check
        assert "status" in report_data and "summary" in report_data
    except Exception as val_ex:
        rep_to_update.execution_state = "CRASHED"
        rep_to_update.fault_reason = f"report validation failed: {str(val_ex)}"
        rep_to_update.ended_at = ended_now
        db.commit()
        return {
            "execution_state": "CRASHED",
            "fault_reason": f"report validation failed: {str(val_ex)}",
            "summary": "Report validation failed."
        }

    # 7. Atomic DB Write for Clean Completion
    verdict_status = report_data.get("status", "FAIL")
    rep_to_update.execution_state = "COMPLETED"
    rep_to_update.status = verdict_status
    rep_to_update.raw_report = raw_json_str
    rep_to_update.ended_at = ended_now
    
    # Update project status
    project.status = "AWAITING_APPROVAL"
    db.commit()

    project_service.log_activity(
        db,
        project_id,
        "TEST_REPORT_SAVED",
        f"Test report v{version_num} COMPLETED with verdict: {verdict_status}."
    )

    return report_data

def stop_testing_execution(db: Session, project_id: str) -> Dict[str, Any]:
    project = project_service.get_project(db, project_id)
    if not project:
        raise ValueError("Project not found")

    # Find active running report
    running_report = db.query(models.TestingReport).filter(
        models.TestingReport.project_id == project_id,
        models.TestingReport.execution_state == "RUNNING"
    ).first()

    if not running_report:
        raise ValueError("No active test run to stop.")

    # 1. Kill spawned subprocess if any
    kill_running_process(project_id)

    # 2. Mark state = ABORTED
    now = datetime.datetime.utcnow()
    running_report.execution_state = "ABORTED"
    running_report.fault_reason = "stopped by user"
    running_report.ended_at = now
    
    db.commit()

    project_service.log_activity(
        db, project_id, "TESTING_ABORTED", "Testing execution stopped by user."
    )

    return {
        "execution_state": "ABORTED",
        "fault_reason": "stopped by user",
        "message": "Testing execution stopped. Phase remains in TESTING."
    }

def resume_testing_approval(
    db: Session, 
    project_id: str, 
    status: str, 
    comments: Optional[str] = None, 
    reviewer_name: Optional[str] = "Lead Tester"
) -> Dict[str, Any]:
    report = db.query(models.TestingReport).filter(
        models.TestingReport.project_id == project_id
    ).order_by(models.TestingReport.version_num.desc()).first()
    
    if not report:
        raise ValueError("No test report generated yet to approve.")

    if report.execution_state != "COMPLETED":
        raise ValueError(f"Cannot approve a test run that is in state {report.execution_state}. Only COMPLETED reports can be reviewed.")

    if status == "APPROVED" and report.status == "FAIL":
        raise ValueError("Cannot approve a failed test report. Failed builds must be sent back to DEVELOPMENT.")

    report.approval_status = status
    report.reviewer_comments = comments or ""
    report.reviewer_name = reviewer_name or "Lead Tester"
    db.commit()

    if status == "APPROVED":
        project_service.transition_phase(
            db=db,
            project_id=project_id,
            from_phase="TESTING",
            to_phase="COMPLETED",
            review_status="APPROVED",
            comments=comments,
            reviewer_name=reviewer_name,
            artifact_version=f"Test Report v{report.version_num}"
        )
    else:
        project_service.transition_phase(
            db=db,
            project_id=project_id,
            from_phase="TESTING",
            to_phase="DEVELOPMENT",
            review_status="REJECTED",
            comments=comments,
            reviewer_name=reviewer_name,
            artifact_version=f"Test Report v{report.version_num}"
        )

    return json.loads(report.raw_report) if report.raw_report else {"status": report.status}

def get_latest_testing_report(db: Session, project_id: str) -> Optional[models.TestingReport]:
    return db.query(models.TestingReport).filter(
        models.TestingReport.project_id == project_id
    ).order_by(models.TestingReport.version_num.desc()).first()

def get_testing_history(db: Session, project_id: str):
    reports = db.query(models.TestingReport).filter(
        models.TestingReport.project_id == project_id
    ).order_by(models.TestingReport.version_num.desc()).all()
    
    return [{
        "version_num": r.version_num,
        "execution_state": r.execution_state,
        "status": r.status,
        "report": json.loads(r.raw_report) if r.raw_report else None,
        "approval_status": r.approval_status,
        "reviewer_comments": r.reviewer_comments,
        "reviewer_name": r.reviewer_name,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "ended_at": r.ended_at.isoformat() if r.ended_at else None,
        "fault_reason": r.fault_reason,
        "created_at": r.created_at.isoformat()
    } for r in reports]
