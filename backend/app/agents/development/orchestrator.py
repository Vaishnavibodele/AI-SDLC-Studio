import json
import os
from datetime import datetime
from typing import Dict, Any, List
from concurrent.futures import ThreadPoolExecutor

from langgraph.graph import StateGraph, END
from langgraph.types import interrupt

from .development_state import DevelopmentAgentState
from .context_builder import input_validator_node, context_builder_node
from .planning_engine import planning_engine_node
from .agents.backend_agent import backend_agent_node
from .agents.frontend_agent import frontend_agent_node
from .agents.database_agent import database_agent_node
from .agents.api_integration_agent import api_integration_agent_node
from .agents.documentation_agent import documentation_agent_node
from .agents.self_review_agent import self_review_agent_node
from .core.merge_validation import merge_validation_node
from .core.artifact_generator import artifact_generator_node

from ...database import sqlite_checkpointer, SessionLocal
from ...services import project_service
from .core.memory_manager import memory_manager

# ----------------- DB HELPERS -----------------

def update_db_project_status(project_id: str, phase: str, status: str):
    db = SessionLocal()
    try:
        proj = project_service.get_project(db, project_id)
        if proj:
            proj.current_phase = phase
            proj.status = status
            db.commit()
            print(f"[State Machine] Project {project_id} transitioned -> Phase: {phase}, Status: {status}")
    except Exception as e:
        print(f"[State Machine] Error updating project status: {e}")
    finally:
        db.close()


def record_node_execution(project_id: str, agent_name: str, stage: str, node_name: str, start_time: datetime, status: str = "SUCCESS", prompt_tokens: int = 0, completion_tokens: int = 0, retry_count: int = 0, error_message: str = None, task_id: str = None, files_generated: List[str] = None):
    db = SessionLocal()
    try:
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        latest_ver = db.query(project_service.models.DevelopmentVersion).filter(
            project_service.models.DevelopmentVersion.project_id == project_id
        ).order_by(project_service.models.DevelopmentVersion.version_num.desc()).first()
        
        log_entry = project_service.models.DevelopmentExecutionLog(
            project_id=project_id,
            version_id=latest_ver.id if latest_ver else None,
            agent_name=agent_name,
            stage=stage,
            node_name=node_name,
            started_at=start_time,
            completed_at=end_time,
            duration=duration,
            llm_provider="gemini",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            retry_count=retry_count,
            status=status,
            error_message=error_message,
            task_id=task_id,
            files_generated=json.dumps(files_generated) if files_generated else None
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        print(f"[Execution Log] Failed to save execution log: {e}")
    finally:
        db.close()


def save_multi_agent_dev_version(project_id: str, state: DevelopmentAgentState, zip_path: str, artifact_paths_map: dict):
    db = SessionLocal()
    try:
        proj = project_service.get_project(db, project_id)
        if not proj:
            return None
            
        design_doc = db.query(project_service.models.DesignDocument).filter(
            project_service.models.DesignDocument.project_id == project_id
        ).first()
        
        latest_design_ver = None
        if design_doc:
            latest_design_ver = db.query(project_service.models.DesignVersion).filter(
                project_service.models.DesignVersion.design_document_id == design_doc.id
            ).order_by(project_service.models.DesignVersion.version_num.desc()).first()
            
        last_dev_ver = db.query(project_service.models.DevelopmentVersion).filter(
            project_service.models.DevelopmentVersion.project_id == project_id
        ).order_by(project_service.models.DevelopmentVersion.version_num.desc()).first()
        version_num = (last_dev_ver.version_num + 1) if last_dev_ver else 1
        
        manifest_payload = {
            "files": state.get("manifest", []),
            "contents": state.get("merged_files", {})
        }

        # Calculate changed files compared to parent version
        changed_files_list = []
        if last_dev_ver:
            try:
                parent_manifest_payload = json.loads(last_dev_ver.raw_manifest)
                parent_contents = parent_manifest_payload.get("contents", {})
                current_contents = state.get("merged_files", {})
                for path, content in current_contents.items():
                    if path not in parent_contents or parent_contents[path] != content:
                        changed_files_list.append(path)
            except Exception:
                changed_files_list = []

        feedback = state.get("human_feedback") or {}
        reason_for_revision = feedback.get("comments", "Initial scaffold codebase generation.") if feedback else "Initial scaffold codebase generation."
        review_comments = feedback.get("comments", "") if feedback else ""

        dev_version = project_service.models.DevelopmentVersion(
            project_id=project_id,
            design_version_id=latest_design_ver.id if latest_design_ver else None,
            version_num=version_num,
            raw_manifest=json.dumps(manifest_payload),
            artifact_zip_path=zip_path,
            artifact_paths=json.dumps(artifact_paths_map),
            approval_status="PENDING",
            parent_version_id=last_dev_ver.id if last_dev_ver else None,
            changed_files=json.dumps(changed_files_list),
            reason_for_revision=reason_for_revision,
            review_comments=review_comments
        )
        db.add(dev_version)
        db.commit()
        db.refresh(dev_version)
        
        # Save tasks to development_tasks table
        tasks_list = state.get("tasks", [])
        for t in tasks_list:
            task_entry = project_service.models.DevelopmentTask(
                project_id=project_id,
                version_id=dev_version.id,
                module=t.get("module"),
                description=t.get("purpose"),
                owner_agent=t.get("owner_agent"),
                dependencies=json.dumps(t.get("depends_on", "")),
                priority=t.get("priority", 3),
                status="COMPLETED",
                requirement_id=t.get("requirement_id"),
                design_section_id=t.get("design_section_id")
            )
            db.add(task_entry)
            
        # Save outputs in development_agent_outputs table
        agents_outputs = {
            "DatabaseDeveloperAgent": state.get("database_output"),
            "BackendDeveloperAgent": state.get("backend_output"),
            "FrontendDeveloperAgent": state.get("frontend_output"),
            "APIIntegrationAgent": state.get("api_integration_output"),
            "DocumentationAgent": state.get("documentation_output")
        }
        for agent_name, out in agents_outputs.items():
            if out:
                out_entry = project_service.models.DevelopmentAgentOutput(
                    project_id=project_id,
                    version_id=dev_version.id,
                    agent_name=agent_name,
                    output_payload=json.dumps(out),
                    status=out.get("status", "SUCCESS")
                )
                db.add(out_entry)
                
        # Save artifacts in development_artifacts table
        import hashlib
        for art_type, file_path in artifact_paths_map.items():
            checksum = None
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    checksum = hashlib.md5(f.read()).hexdigest()
            art_entry = project_service.models.DevelopmentArtifact(
                project_id=project_id,
                version_id=dev_version.id,
                artifact_type=art_type,
                file_path=file_path,
                checksum=checksum
            )
            db.add(art_entry)
            
        # Log to development_logs
        dev_log = project_service.models.DevelopmentLog(
            project_id=project_id,
            action="CODE_VERSION_SAVED",
            details=f"Multi-agent codebase version {version_num} generated with status: PENDING."
        )
        db.add(dev_log)
        db.commit()
        
        project_service.log_activity(db, project_id, "DEVELOPMENT_VERSION_SAVED", f"Multi-agent code version {version_num} saved.")
        return dev_version
    except Exception as e:
        print(f"[Dev DB] Error saving dev version: {str(e)}")
        return None
    finally:
        db.close()


# ----------------- WRAPPER NODES -----------------

def get_execution_logs_state(project_id: str) -> List[dict]:
    db = SessionLocal()
    try:
        logs = db.query(project_service.models.DevelopmentExecutionLog).filter(
            project_service.models.DevelopmentExecutionLog.project_id == project_id
        ).all()
        return [{
            "project_id": l.project_id,
            "version_id": l.version_id,
            "agent_name": l.agent_name,
            "stage": l.stage,
            "task_id": l.task_id or "",
            "started_at": l.started_at.isoformat(),
            "completed_at": l.completed_at.isoformat() if l.completed_at else None,
            "duration": l.duration,
            "status": l.status,
            "retry_count": l.retry_count,
            "error_message": l.error_message,
            "files_generated": json.loads(l.files_generated) if l.files_generated else []
        } for l in logs]
    except Exception:
        return []
    finally:
        db.close()


def input_validation(state: DevelopmentAgentState) -> Dict[str, Any]:
    start_time = datetime.utcnow()
    project_id = state.get("project_id")
    try:
        res = input_validator_node(state)
        res["revision_attempts"] = state.get("revision_attempts", 0)
        res["current_node"] = "input_validation"
        res["errors"] = res.get("validation_errors", [])
        if res.get("validation_errors"):
            res["phase"] = "WAITING_FOR_REVIEW"
            res["execution_state"] = "INPUT_VALIDATION_FAILED"
            res["error_code"] = "INPUT_VALIDATION_FAILED"
            record_node_execution(project_id, "InputValidator", "1", "input_validation", start_time, "FAILED", error_message=str(res["validation_errors"]))
            res["execution_logs"] = get_execution_logs_state(project_id)
            return res
        record_node_execution(project_id, "InputValidator", "1", "input_validation", start_time, "SUCCESS")
        res["execution_logs"] = get_execution_logs_state(project_id)
        return res
    except Exception as e:
        record_node_execution(project_id, "InputValidator", "1", "input_validation", start_time, "FAILED", error_message=str(e))
        return {
            "phase": "WAITING_FOR_REVIEW",
            "validation_errors": [{"agent": "InputValidator", "error": str(e)}],
            "errors": [{"agent": "InputValidator", "error": str(e)}],
            "execution_state": "INPUT_VALIDATION_FAILED",
            "error_code": "INPUT_VALIDATION_FAILED",
            "current_node": "input_validation",
            "revision_attempts": state.get("revision_attempts", 0),
            "execution_logs": get_execution_logs_state(project_id)
        }


def development_context_builder(state: DevelopmentAgentState) -> Dict[str, Any]:
    start_time = datetime.utcnow()
    project_id = state.get("project_id")
    try:
        res = context_builder_node(state)
        res["context"] = res.get("development_context", {})
        res["current_node"] = "development_context_builder"
        update_db_project_status(project_id, "DEVELOPMENT", "DEVELOPMENT_PLANNING")
        record_node_execution(project_id, "ContextBuilder", "1", "development_context_builder", start_time, "SUCCESS")
        res["execution_logs"] = get_execution_logs_state(project_id)
        return res
    except Exception as e:
        record_node_execution(project_id, "ContextBuilder", "1", "development_context_builder", start_time, "FAILED", error_message=str(e))
        return {
            "phase": "WAITING_FOR_REVIEW",
            "validation_errors": [{"agent": "ContextBuilder", "error": str(e)}],
            "errors": [{"agent": "ContextBuilder", "error": str(e)}],
            "execution_state": "PLANNING_FAILED",
            "error_code": "PLANNING_FAILED",
            "current_node": "development_context_builder",
            "execution_logs": get_execution_logs_state(project_id)
        }


def project_planner(state: DevelopmentAgentState) -> Dict[str, Any]:
    start_time = datetime.utcnow()
    project_id = state.get("project_id")
    try:
        res = planning_engine_node(state)
        res["current_node"] = "project_planner"
        record_node_execution(project_id, "PlanningEngine", "3", "project_planner", start_time, "SUCCESS")
        res["execution_logs"] = get_execution_logs_state(project_id)
        return res
    except Exception as e:
        record_node_execution(project_id, "PlanningEngine", "3", "project_planner", start_time, "FAILED", error_message=str(e))
        return {
            "phase": "WAITING_FOR_REVIEW",
            "validation_errors": [{"agent": "PlanningEngine", "error": str(e)}],
            "errors": [{"agent": "PlanningEngine", "error": str(e)}],
            "execution_state": "PLANNING_FAILED",
            "error_code": "PLANNING_FAILED",
            "current_node": "project_planner",
            "execution_logs": get_execution_logs_state(project_id)
        }


def task_distribution_engine(state: DevelopmentAgentState) -> Dict[str, Any]:
    """Stage 4 Node Wrapper: Runs Backend, Frontend, Database, Integration, and Documentation agents using dependency-aware scheduling."""
    start_time = datetime.utcnow()
    project_id = state.get("project_id")
    print(f"[Task Distribution Engine] Dispatching Stage 4 agents for project {project_id}...")
    update_db_project_status(project_id, "DEVELOPMENT", "GENERATING_CODE")
    
    db_res = {}
    be_res = {}
    fe_res = {}
    integ_res = {}
    doc_res = {}
    
    try:
        # Create isolated inputs for Phase 1 (concurrency/thread safety)
        db_input = {
            "project_id": project_id,
            "rejected_modules": state.get("rejected_modules", []),
            "development_context": state.get("development_context", {}),
            "manifest": state.get("manifest", [])
        }
        fe_input = {
            "project_id": project_id,
            "rejected_modules": state.get("rejected_modules", []),
            "development_context": state.get("development_context", {}),
            "manifest": state.get("manifest", [])
        }
        doc_input = {
            "project_id": project_id,
            "rejected_modules": state.get("rejected_modules", []),
            "development_context": state.get("development_context", {}),
            "manifest": state.get("manifest", [])
        }
        
        # PHASE 1: Run DatabaseAgent, FrontendAgent, and DocumentationAgent (initial pass) in parallel
        print("[Scheduler] Phase 1: Dispatching DatabaseAgent, FrontendAgent, and DocumentationAgent concurrently...")
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_db = executor.submit(database_agent_node, db_input)
            future_fe = executor.submit(frontend_agent_node, fe_input)
            future_doc = executor.submit(documentation_agent_node, doc_input)
            
            db_res = future_db.result()
            fe_res = future_fe.result()
            doc_res = future_doc.result()
            
        # Update local states with Phase 1 outputs for Phase 2 only if newly returned
        if db_res.get("database_output"):
            state["database_output"] = db_res.get("database_output")
        if fe_res.get("frontend_output"):
            state["frontend_output"] = fe_res.get("frontend_output")
        if doc_res.get("documentation_output"):
            state["documentation_output"] = doc_res.get("documentation_output")
        
        # PHASE 2: Run BackendAgent (depends on DatabaseAgent)
        print("[Scheduler] Phase 2: Dispatching BackendAgent (depends on DatabaseAgent)...")
        be_input = {
            "project_id": project_id,
            "rejected_modules": state.get("rejected_modules", []),
            "development_context": state.get("development_context", {}),
            "manifest": state.get("manifest", []),
            "database_output": state.get("database_output")
        }
        be_res = backend_agent_node(be_input)
        if be_res.get("backend_output"):
            state["backend_output"] = be_res.get("backend_output")
        
        # PHASE 3: Run APIIntegrationAgent (depends on Backend + Frontend + Database)
        print("[Scheduler] Phase 3: Dispatching APIIntegrationAgent...")
        integ_input = {
            "project_id": project_id,
            "rejected_modules": state.get("rejected_modules", []),
            "database_output": state.get("database_output"),
            "backend_output": state.get("backend_output"),
            "frontend_output": state.get("frontend_output")
        }
        integ_res = api_integration_agent_node(integ_input)
        if integ_res.get("api_integration_output"):
            state["api_integration_output"] = integ_res.get("api_integration_output")
        
        validation_errors = (
            db_res.get("validation_errors", []) + 
            be_res.get("validation_errors", []) + 
            fe_res.get("validation_errors", []) + 
            integ_res.get("validation_errors", []) + 
            doc_res.get("validation_errors", [])
        )
        
        # Compile agent outputs and api contract properties
        agent_outputs = {
            "DatabaseDeveloperAgent": state["database_output"],
            "BackendDeveloperAgent": state["backend_output"],
            "FrontendDeveloperAgent": state["frontend_output"],
            "APIIntegrationAgent": state["api_integration_output"],
            "DocumentationAgent": state["documentation_output"]
        }
        
        # Compile agent statuses mapping (Objective Section 11)
        agent_statuses = {
            "DatabaseDeveloperAgent": "COMPLETED" if state["database_output"] else "PENDING",
            "BackendDeveloperAgent": "COMPLETED" if state["backend_output"] else "PENDING",
            "FrontendDeveloperAgent": "COMPLETED" if state["frontend_output"] else "PENDING",
            "APIIntegrationAgent": "COMPLETED" if state["api_integration_output"] else "PENDING",
            "DocumentationAgent": "COMPLETED" if state["documentation_output"] else "PENDING"
        }
        for err in validation_errors:
            ag = err.get("agent")
            if ag in agent_statuses:
                agent_statuses[ag] = "FAILED"
        
        api_contract = {
            "backend_routes": state["api_integration_output"].get("backend_routes", []) if state["api_integration_output"] else [],
            "mismatches": state["api_integration_output"].get("mismatches", []) if state["api_integration_output"] else []
        }
        
        return {
            "database_output": state["database_output"],
            "backend_output": state["backend_output"],
            "frontend_output": state["frontend_output"],
            "api_integration_output": state["api_integration_output"],
            "documentation_output": state["documentation_output"],
            "agent_outputs": agent_outputs,
            "agent_statuses": agent_statuses,
            "api_contract": api_contract,
            "api_contract_results": api_contract,
            "validation_errors": validation_errors,
            "errors": validation_errors,
            "phase": "VALIDATING",
            "current_node": "task_distribution_engine",
            "current_stage": "4",
            "current_agent": "TaskDistributionEngine",
            "current_task": "Stage 4 parallel worker agents complete.",
            "progress_percentage": 50,
            "execution_logs": get_execution_logs_state(project_id)
        }
    except Exception as e:
        attempts = state.get("agent_failed_attempts", 0)
        next_attempt = attempts + 1
        record_node_execution(project_id, "TaskDistributionEngine", "4", "task_distribution_engine", start_time=start_time, status="FAILED", retry_count=attempts, error_message=str(e))
        if next_attempt < 3:
            return {
                "phase": "task_distribution_engine",
                "agent_failed_attempts": next_attempt,
                "current_node": "task_distribution_engine",
                "execution_logs": get_execution_logs_state(project_id)
            }
        else:
            return {
                "phase": "WAITING_FOR_REVIEW",
                "agent_failed_attempts": next_attempt,
                "execution_state": "AGENT_FAILED",
                "error_code": "AGENT_FAILED",
                "failed_agent": "TaskDistributionEngine",
                "failed_stage": "CODE_GENERATION",
                "error_message": str(e),
                "validation_errors": [{"agent": "TaskDistributionEngine", "error": str(e)}],
                "errors": [{"agent": "TaskDistributionEngine", "error": str(e)}],
                "current_node": "task_distribution_engine",
                "execution_logs": get_execution_logs_state(project_id)
            }


def build_validator(state: DevelopmentAgentState) -> Dict[str, Any]:
    start_time = datetime.utcnow()
    project_id = state.get("project_id")
    attempts = state.get("validation_attempts", 0)
    try:
        update_db_project_status(project_id, "DEVELOPMENT", "VALIDATING")
        res = merge_validation_node(state)
        errors = res.get("validation_errors", [])
        
        res["generated_files"] = res.get("merged_files", {})
        res["current_node"] = "build_validator"
        
        # 1. Check for File Ownership Conflict
        ownership_conflicts = [e for e in errors if "FILE_OWNERSHIP_CONFLICT" in e.get("error", "")]
        if ownership_conflicts:
            res["phase"] = "WAITING_FOR_REVIEW"
            res["build_status"] = "FAILED"
            res["execution_state"] = "FILE_OWNERSHIP_CONFLICT"
            res["error_code"] = "FILE_OWNERSHIP_CONFLICT"
            res["failed_agent"] = "MergeValidationLayer"
            res["failed_stage"] = "MERGE_VALIDATION"
            res["error_message"] = f"FILE_OWNERSHIP_CONFLICT: {ownership_conflicts[0]['error']}"
            record_node_execution(project_id, "MergeValidationLayer", "5", "build_validator", start_time, "FAILED", retry_count=attempts, error_message=res["error_message"])
            res["execution_logs"] = get_execution_logs_state(project_id)
            return res
            
        # 2. Check for API Contract Mismatches
        api_mismatches = [e for e in errors if "API_CONTRACT_MISMATCH" in e.get("error", "")]
        
        if errors:
            next_attempt = attempts + 1
            res["validation_attempts"] = next_attempt
            
            if next_attempt >= 3:
                res["phase"] = "WAITING_FOR_REVIEW"
                res["build_status"] = "FAILED"
                syntax_errors = [e for e in errors if "compilation failed" in e.get("error", "").lower() or e.get("error_type") == "SYNTAX_ERROR"]
                if syntax_errors:
                    res["execution_state"] = "BUILD_VALIDATION_FAILED"
                    res["error_code"] = "BUILD_VALIDATION_FAILED"
                    res["failed_agent"] = "MergeValidationLayer"
                    res["failed_stage"] = "MERGE_VALIDATION"
                    res["error_message"] = "BUILD_VALIDATION_FAILED: Syntax or compilation validation check failed."
                elif api_mismatches:
                    res["execution_state"] = "API_CONTRACT_MISMATCH"
                    res["error_code"] = "API_CONTRACT_MISMATCH"
                    res["failed_agent"] = "APIIntegrationAgent"
                    res["failed_stage"] = "API_VALIDATION"
                    res["error_message"] = "API_CONTRACT_MISMATCH: API contract mismatch detected."
                else:
                    res["execution_state"] = "BUILD_VALIDATION_FAILED"
                    res["error_code"] = "BUILD_VALIDATION_FAILED"
                    res["failed_agent"] = "MergeValidationLayer"
                    res["failed_stage"] = "MERGE_VALIDATION"
                    res["error_message"] = "BUILD_VALIDATION_FAILED: Syntax or compilation validation check failed."
                record_node_execution(project_id, "MergeValidationLayer", "5", "build_validator", start_time, "FAILED", retry_count=attempts, error_message=res["error_message"])
            else:
                res["phase"] = "GENERATING_CODE"
                record_node_execution(project_id, "MergeValidationLayer", "5", "build_validator", start_time, "FAILED", retry_count=attempts, error_message=str(errors))
        else:
            res["phase"] = "AI_SELF_REVIEW"
            record_node_execution(project_id, "MergeValidationLayer", "5", "build_validator", start_time, "SUCCESS", retry_count=attempts)
            
        res["execution_logs"] = get_execution_logs_state(project_id)
        return res
    except Exception as e:
        record_node_execution(project_id, "MergeValidationLayer", "5", "build_validator", start_time, "FAILED", retry_count=attempts, error_message=str(e))
        return {
            "phase": "WAITING_FOR_REVIEW",
            "execution_state": "BUILD_VALIDATION_FAILED",
            "error_code": "BUILD_VALIDATION_FAILED",
            "failed_agent": "MergeValidationLayer",
            "failed_stage": "MERGE_VALIDATION",
            "error_message": str(e),
            "validation_errors": [{"agent": "MergeValidationLayer", "error": str(e)}],
            "errors": [{"agent": "MergeValidationLayer", "error": str(e)}],
            "current_node": "build_validator",
            "execution_logs": get_execution_logs_state(project_id)
        }


def run_self_review(state: DevelopmentAgentState) -> Dict[str, Any]:
    start_time = datetime.utcnow()
    project_id = state.get("project_id")
    try:
        update_db_project_status(project_id, "DEVELOPMENT", "AI_SELF_REVIEW")
        
        # Run ONLY SelfReviewAgent node (Section 9)
        print("[Scheduler] Executing SelfReviewAgent node...")
        sr_res = self_review_agent_node(state)
        
        return {
            "self_review_report": sr_res.get("self_review_report"),
            "self_review_results": sr_res.get("self_review_report"),
            "quality_score": sr_res.get("quality_score", 90.0),
            "security_score": sr_res.get("security_score", 95.0),
            "requirement_coverage": sr_res.get("requirement_coverage", 95.0),
            "architecture_compliance": sr_res.get("architecture_compliance", 100.0),
            "findings": sr_res.get("findings", []),
            "current_stage": "8",
            "current_node": "run_self_review",
            "current_agent": "SelfReviewAgent",
            "current_task": "Self-review advisory metrics calculated.",
            "progress_percentage": 85,
            "execution_logs": get_execution_logs_state(project_id)
        }
    except Exception as e:
        record_node_execution(project_id, "SelfReviewAgent", "8", "run_self_review", start_time, "FAILED", error_message=str(e))
        return {
            "phase": "ERROR",
            "execution_state": "SELF_REVIEW_FAILED",
            "error_code": "SELF_REVIEW_FAILED",
            "failed_agent": "SelfReviewAgent",
            "failed_stage": "SELF_REVIEW",
            "error_message": str(e),
            "validation_errors": [{"agent": "SelfReviewAgent", "error": str(e)}],
            "errors": [{"agent": "SelfReviewAgent", "error": str(e)}],
            "current_node": "run_self_review",
            "execution_logs": get_execution_logs_state(project_id)
        }


def final_documentation_refinement(state: DevelopmentAgentState) -> Dict[str, Any]:
    start_time = datetime.utcnow()
    project_id = state.get("project_id")
    print(f"[Documentation Agent] Running Stage 9 Final Documentation Refinement for project {project_id}...")
    
    from .core.prompt_manager import prompt_manager
    prompt = prompt_manager.get_prompt("DocumentationAgent", "v1")
    
    user_msg = f"""
You are the Technical Documentation Agent.
We have successfully compiled and validated the project scaffolds.
Please refine and write the final technical 'README.md' documentation.

Context received:
- Final Source Files: {list(state.get("merged_files", {}).keys())}
- Final Manifest: {state.get("manifest", [])}
- Build & Validation Status: {state.get("build_status", "SUCCESS")}
- API Mismatches / Contracts: {state.get("api_contract", {})}
- Self Review Advisory Quality metrics: {state.get("self_review_results", {})}
- Current Project Version: {state.get("current_version", 1)}
- Revision Attempts: {state.get("revision_attempts", 0)}

Output ONLY raw markdown content for 'README.md'.
Do not wrap the whole response in markdown code block backticks.
"""
    
    try:
        from ...services.llm_provider import get_llm
        llm = get_llm()
        res = llm.invoke([
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_msg}
        ])
        code = res.content.strip()
        
        if code.startswith("```"):
            lines = code.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            code = "\n".join(lines)
            
        merged_files = state.get("merged_files", {})
        merged_files["README.md"] = code
        
        manifest = state.get("manifest", [])
        if "README.md" in merged_files and not any(m.get("path") == "README.md" for m in manifest):
            manifest.append({
                "path": "README.md",
                "module": "documentation",
                "owner_agent": "DocumentationAgent",
                "purpose": "Technical guide documentation",
                "security_sensitive": False
            })
            
        record_node_execution(
            project_id=project_id,
            agent_name="DocumentationAgent",
            stage="9",
            node_name="final_documentation_refinement",
            start_time=start_time,
            status="SUCCESS",
            task_id="TASK-DOC-002",
            files_generated=["README.md"]
        )
        
        # Build payload
        documentation_output = {
            "agent": "DocumentationAgent",
            "files": ["README.md"],
            "status": "COMPLETED",
            "raw_files": {
                "README.md": code
            }
        }
        
        return {
            "merged_files": merged_files,
            "generated_files": merged_files,
            "manifest": manifest,
            "documentation_output": documentation_output,
            "current_stage": "9",
            "current_node": "final_documentation_refinement",
            "current_agent": "DocumentationAgent",
            "current_task": "Final README technical document refined successfully.",
            "progress_percentage": 90,
            "execution_logs": get_execution_logs_state(project_id)
        }
    except Exception as e:
        record_node_execution(
            project_id=project_id,
            agent_name="DocumentationAgent",
            stage="9",
            node_name="final_documentation_refinement",
            start_time=start_time,
            status="FAILED",
            task_id="TASK-DOC-002",
            error_message=str(e)
        )
        return {
            "phase": "WAITING_FOR_REVIEW",
            "execution_state": "ARTIFACT_GENERATION_FAILED",
            "error_code": "ARTIFACT_GENERATION_FAILED",
            "failed_agent": "DocumentationAgent",
            "failed_stage": "DOCUMENT_REFINEMENT",
            "error_message": str(e),
            "validation_errors": [{"agent": "DocumentationAgent", "error": str(e)}],
            "errors": [{"agent": "DocumentationAgent", "error": str(e)}],
            "current_node": "final_documentation_refinement",
            "execution_logs": get_execution_logs_state(project_id)
        }


def artifact_generator(state: DevelopmentAgentState) -> Dict[str, Any]:
    start_time = datetime.utcnow()
    project_id = state.get("project_id")
    try:
        update_db_project_status(project_id, "DEVELOPMENT", "ARTIFACT_GENERATION")
        res = artifact_generator_node(state)
        
        save_multi_agent_dev_version(
            project_id=project_id,
            state=state,
            zip_path=res["artifact_paths"]["source_zip"],
            artifact_paths_map=res["artifact_paths"]
        )
        
        res["phase"] = "WAITING_FOR_REVIEW"
        res["current_node"] = "artifact_generator"
        record_node_execution(project_id, "ArtifactGenerator", "7", "artifact_generator", start_time, "SUCCESS")
        res["execution_logs"] = get_execution_logs_state(project_id)
        return res
    except Exception as e:
        attempts = state.get("artifact_attempts", 0)
        next_attempt = attempts + 1
        record_node_execution(project_id, "ArtifactGenerator", "7", "artifact_generator", start_time, "FAILED", retry_count=attempts, error_message=str(e))
        if next_attempt < 2:
            return {
                "phase": "artifact_generator",
                "artifact_attempts": next_attempt,
                "current_node": "artifact_generator",
                "execution_logs": get_execution_logs_state(project_id)
            }
        else:
            return {
                "phase": "WAITING_FOR_REVIEW",
                "artifact_attempts": next_attempt,
                "validation_errors": [{"agent": "ArtifactGenerator", "error": str(e)}],
                "errors": [{"agent": "ArtifactGenerator", "error": str(e)}],
                "execution_state": "ARTIFACT_GENERATION_FAILED",
                "error_code": "ARTIFACT_GENERATION_FAILED",
                "current_node": "artifact_generator",
                "execution_logs": get_execution_logs_state(project_id)
            }


def human_approval(state: DevelopmentAgentState) -> Dict[str, Any]:
    project_id = state.get("project_id")
    print(f"[Human Approval] Node interrupt activated for project {project_id}...")
    update_db_project_status(project_id, "DEVELOPMENT", "WAITING_FOR_REVIEW")
    
    feedback = interrupt({
        "message": "Gated human review required. Code scaffolds compiled and reports validated successfully.",
        "manifest": state.get("manifest", []),
        "quality_score": state.get("quality_score", 9.0),
        "security_score": state.get("security_score", 9.5),
        "validation_errors": state.get("validation_errors", [])
    })
    
    return {
        "human_feedback": feedback,
        "phase": "WAITING_FOR_REVIEW"
    }


def post_approval_handler(state: DevelopmentAgentState) -> Dict[str, Any]:
    start_time = datetime.utcnow()
    project_id = state.get("project_id")
    feedback = state.get("human_feedback") or {}
    
    status = feedback.get("status")
    comments = feedback.get("comments", "")
    rejected_mods = feedback.get("rejected_modules", [])
    
    print(f"[Post Approval] Review status received: {status}")
    
    db = SessionLocal()
    try:
        latest_ver = db.query(project_service.models.DevelopmentVersion).filter(
            project_service.models.DevelopmentVersion.project_id == project_id
        ).order_by(project_service.models.DevelopmentVersion.version_num.desc()).first()
        
        review = project_service.models.DevelopmentReview(
            project_id=project_id,
            version_id=latest_ver.id if latest_ver else None,
            status=status,
            comments=comments,
            rejected_modules=json.dumps(rejected_mods),
            reviewer_name=feedback.get("reviewer_name", "Lead Developer")
        )
        db.add(review)
        
        dev_log = project_service.models.DevelopmentLog(
            project_id=project_id,
            action=f"REVIEW_{status}",
            details=f"Code reviewed by {feedback.get('reviewer_name')}. Comments: {comments}"
        )
        db.add(dev_log)
        db.commit()
        
        if latest_ver:
            memory_manager.save_iteration_memory(
                project_id=project_id,
                version=latest_ver.version_num,
                data={
                    "manifest": state.get("manifest", []),
                    "generated_files": state.get("merged_files", {}),
                    "errors": state.get("validation_errors", []),
                    "feedback": feedback
                }
            )

        # Track revision attempts on rejection
        revision_attempts = state.get("revision_attempts", 0)

        if status == "APPROVED":
            latest_ver.approval_status = "APPROVED"
            db.commit()
            
            update_db_project_status(project_id, "DEVELOPMENT", "DEVELOPMENT_APPROVED")
            update_db_project_status(project_id, "TESTING", "READY_FOR_TESTING")
            project_service.log_activity(db, project_id, "DEVELOPMENT_APPROVED", "Development scaffolds approved.")
            
            record_node_execution(project_id, "PostApprovalHandler", "8", "post_approval_handler", start_time, "SUCCESS")
            return {
                "phase": "READY_FOR_TESTING",
                "execution_state": "COMPLETED",
                "current_node": "post_approval_handler",
                "current_task": "Review approved. Phase transitioned to TESTING.",
                "progress_percentage": 100
            }
        else:
            latest_ver.approval_status = "REJECTED"
            db.commit()
            
            revision_attempts += 1
            update_db_project_status(project_id, "DEVELOPMENT", "DEVELOPMENT_PLANNING")
            project_service.log_activity(db, project_id, "DEVELOPMENT_REJECTED", f"Code revision requested. Comments: {comments}")
            
            record_node_execution(project_id, "PostApprovalHandler", "9", "post_approval_handler", start_time, "FAILED")
            return {
                "phase": "DEVELOPMENT_PLANNING",
                "execution_state": "RUNNING",
                "rejected_modules": rejected_mods,
                "revision_attempts": revision_attempts,
                "current_node": "post_approval_handler",
                "current_task": f"Review rejected. Modules rejected: {rejected_mods}",
                "progress_percentage": 20
            }
    finally:
        db.close()


# ----------------- ROUTING LOGIC -----------------

def route_after_input_validation(state: DevelopmentAgentState) -> str:
    if state.get("phase") == "WAITING_FOR_REVIEW":
        return "human_approval"
    return "development_context_builder"


def route_after_context_builder(state: DevelopmentAgentState) -> str:
    if state.get("phase") == "WAITING_FOR_REVIEW":
        return "human_approval"
    return "project_planner"


def route_after_planner(state: DevelopmentAgentState) -> str:
    if state.get("phase") == "WAITING_FOR_REVIEW":
        return "human_approval"
    return "task_distribution_engine"


def route_after_task_distribution(state: DevelopmentAgentState) -> str:
    phase = state.get("phase")
    if phase == "WAITING_FOR_REVIEW":
        return "human_approval"
    elif phase == "task_distribution_engine":
        return "task_distribution_engine"
    return "build_validator"


def route_after_validation(state: DevelopmentAgentState) -> str:
    phase = state.get("phase")
    if phase == "WAITING_FOR_REVIEW":
        return "human_approval"
    elif phase == "AI_SELF_REVIEW":
        return "run_self_review"
    else:
        return "task_distribution_engine"


def route_after_artifact_generator(state: DevelopmentAgentState) -> str:
    phase = state.get("phase")
    if phase == "artifact_generator":
        return "artifact_generator"
    return "human_approval"


def route_after_approval(state: DevelopmentAgentState) -> str:
    phase = state.get("phase")
    if phase == "READY_FOR_TESTING":
        return END
    else:
        return "project_planner"


# ----------------- GRAPH ORCHESTRATION -----------------

workflow = StateGraph(DevelopmentAgentState)

# Register Nodes
workflow.add_node("input_validation", input_validation)
workflow.add_node("development_context_builder", development_context_builder)
workflow.add_node("project_planner", project_planner)
workflow.add_node("task_distribution_engine", task_distribution_engine)
workflow.add_node("build_validator", build_validator)
workflow.add_node("run_self_review", run_self_review)
workflow.add_node("final_documentation_refinement", final_documentation_refinement)
workflow.add_node("artifact_generator", artifact_generator)
workflow.add_node("human_approval", human_approval)
workflow.add_node("post_approval_handler", post_approval_handler)

# Set Entry Point
workflow.set_entry_point("input_validation")

# Connect Graph
workflow.add_conditional_edges(
    "input_validation",
    route_after_input_validation,
    {
        "human_approval": "human_approval",
        "development_context_builder": "development_context_builder"
    }
)

workflow.add_conditional_edges(
    "development_context_builder",
    route_after_context_builder,
    {
        "human_approval": "human_approval",
        "project_planner": "project_planner"
    }
)

workflow.add_conditional_edges(
    "project_planner",
    route_after_planner,
    {
        "human_approval": "human_approval",
        "task_distribution_engine": "task_distribution_engine"
    }
)

workflow.add_conditional_edges(
    "task_distribution_engine",
    route_after_task_distribution,
    {
        "human_approval": "human_approval",
        "task_distribution_engine": "task_distribution_engine",
        "build_validator": "build_validator"
    }
)

workflow.add_conditional_edges(
    "build_validator",
    route_after_validation,
    {
        "human_approval": "human_approval",
        "run_self_review": "run_self_review",
        "task_distribution_engine": "task_distribution_engine"
    }
)

workflow.add_edge("run_self_review", "final_documentation_refinement")
workflow.add_edge("final_documentation_refinement", "artifact_generator")

workflow.add_conditional_edges(
    "artifact_generator",
    route_after_artifact_generator,
    {
        "artifact_generator": "artifact_generator",
        "human_approval": "human_approval"
    }
)

workflow.add_edge("human_approval", "post_approval_handler")

workflow.add_conditional_edges(
    "post_approval_handler",
    route_after_approval,
    {
        END: END,
        "project_planner": "project_planner"
    }
)

compiled_development_graph = workflow.compile(checkpointer=sqlite_checkpointer)
