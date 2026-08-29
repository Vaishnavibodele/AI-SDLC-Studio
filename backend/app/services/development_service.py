import json
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, List

from ..agents.development.orchestrator import compiled_development_graph, save_multi_agent_dev_version
from . import project_service, design_service

def get_development_config(project_id: str) -> Dict[str, Any]:
    return {"configurable": {"thread_id": f"development:{project_id}"}}

def get_development_state(project_id: str, db: Session) -> Dict[str, Any]:
    config = get_development_config(project_id)
    state = compiled_development_graph.get_state(config)
    
    # Fetch reviews
    reviews_list = db.query(project_service.models.DevelopmentReview).filter(
        project_service.models.DevelopmentReview.project_id == project_id
    ).order_by(project_service.models.DevelopmentReview.created_at.desc()).all()
    
    reviews = [{
        "status": r.status,
        "comments": r.comments,
        "reviewer_name": r.reviewer_name,
        "quality_score": r.quality_score,
        "security_score": r.security_score,
        "created_at": r.created_at.isoformat()
    } for r in reviews_list]
    
    # Fetch logs
    logs_list = db.query(project_service.models.DevelopmentLog).filter(
        project_service.models.DevelopmentLog.project_id == project_id
    ).order_by(project_service.models.DevelopmentLog.timestamp.desc()).all()
    
    logs = [{
        "action": l.action,
        "details": l.details,
        "timestamp": l.timestamp.isoformat()
    } for l in logs_list]
    
    # Fetch execution logs
    exec_logs = get_development_logs(db, project_id)
    
    # Fetch artifacts
    latest_version = get_latest_development_version(db, project_id)
    artifact_paths = json.loads(latest_version.artifact_paths) if latest_version and latest_version.artifact_paths else {}

    # Load diagnostic report contents from disk
    reports = {}
    import os
    if latest_version and latest_version.artifact_paths:
        try:
            for key, rel_path in artifact_paths.items():
                if key != "source_zip" and os.path.exists(rel_path):
                    with open(rel_path, "r", encoding="utf-8") as rf:
                        reports[key] = rf.read()
        except Exception as e:
            print(f"Error loading diagnostic report files: {e}")

    if not state.values:
        return {
            "manifest": [],
            "generated_files": {},
            "validation_attempts": 0,
            "validation_errors": [],
            "phase": "DESIGN_APPROVED",
            "reviews": reviews,
            "logs": logs,
            "execution_logs": exec_logs,
            "artifact_paths": {},
            "reports": reports,
            "execution_state": "IDLE",
            "current_node": "",
            "current_task": "",
            "completed_tasks": [],
            "failed_tasks": [],
            "progress_percentage": 0,
            "current_version": 1,
            "build_status": "PENDING"
        }
        
    return {
        "manifest": state.values.get("manifest", []),
        "generated_files": state.values.get("merged_files", {}),
        "validation_attempts": state.values.get("validation_attempts", 0),
        "validation_errors": state.values.get("validation_errors", []),
        "phase": state.values.get("phase", "DEVELOPMENT_PLANNING"),
        "reviews": reviews,
        "logs": logs,
        "execution_logs": exec_logs,
        "artifact_paths": artifact_paths,
        "reports": reports,
        
        # Enriched state variables
        "execution_state": state.values.get("execution_state", "RUNNING"),
        "current_node": state.values.get("current_node", ""),
        "current_task": state.values.get("current_task", ""),
        "completed_tasks": state.values.get("completed_tasks", []),
        "failed_tasks": state.values.get("failed_tasks", []),
        "progress_percentage": state.values.get("progress_percentage", 0),
        "current_version": state.values.get("current_version", 1),
        "build_status": state.values.get("build_status", "PENDING")
    }

def start_development_generation(db: Session, project_id: str) -> Dict[str, Any]:
    config = get_development_config(project_id)
    
    # If development graph already ran and is waiting for review, return that state
    from ..agents.development.orchestrator import compiled_development_graph
    current_state = compiled_development_graph.get_state(config)
    if current_state.values and current_state.values.get("phase") == "WAITING_FOR_REVIEW":
        return {
            "status": current_state.values.get("phase"),
            "manifest": current_state.values.get("manifest", []),
            "generated_files": current_state.values.get("merged_files", {}),
            "validation_attempts": current_state.values.get("validation_attempts", 0),
            "validation_errors": current_state.values.get("validation_errors", []),
            "execution_state": current_state.values.get("execution_state")
        }

    design_doc, latest_design = design_service.get_latest_design_version(db, project_id)
    if not design_doc or design_doc.approval_status != "APPROVED" or not latest_design:
        raise ValueError("Linked project software design specs (SDD) must be approved before development generation.")
        
    latest_req_ver = project_service.get_latest_srs_version(db, project_id)
    if not latest_req_ver:
        raise ValueError("Approved requirements specifications (SRS) document not found.")
        
    from ..schemas import SRSOutput
    approved_srs = SRSOutput.parse_safely(json.loads(latest_req_ver.raw_srs)).dict()
    approved_sdd = json.loads(latest_design.raw_sdd)
    
    project_service.log_activity(db, project_id, "DEVELOPMENT_STARTED", "Generating project codebase scaffolds...")
    
    dev_log = project_service.models.DevelopmentLog(
        project_id=project_id,
        action="DEVELOPMENT_STARTED",
        details="Multi-agent parallel codebase generation initialized."
    )
    db.add(dev_log)
    db.commit()
    
    inputs = {
        "project_id": project_id,
        "approved_srs": approved_srs,
        "approved_sdd": approved_sdd,
        "tech_stack": approved_sdd.get("technology_stack", {}),
        "existing_code_ref": None,
        "project_metadata": {},
        
        "development_context": {},
        "validation_flags": {},
        
        "plan": {},
        "tasks": [],
        "task_dependencies": {},
        
        "backend_output": None,
        "frontend_output": None,
        "database_output": None,
        "api_integration_output": None,
        "documentation_output": None,
        
        "merged_files": {},
        "manifest": [],
        "static_analysis_report": {},
        "security_quality_report": {},
        "build_report": {},
        "unit_test_report": {},
        
        "self_review_report": {},
        
        "artifact_paths": {},
        "quality_score": 0.0,
        "security_score": 0.0,
        
        "validation_errors": [],
        "validation_attempts": 0,
        
        "current_stage": "1",
        "current_agent": "InputValidator",
        "current_task": "Verifying input parameters",
        "execution_state": "RUNNING",
        "progress_percentage": 5,
        "current_version": 1,
        
        "human_feedback": None,
        "rejected_modules": []
    }
    
    outputs = compiled_development_graph.invoke(inputs, config)
    
    phase = outputs.get("phase", "DEVELOPMENT_PLANNING")
    errors = outputs.get("validation_errors", [])
    
    return {
        "status": phase,
        "manifest": outputs.get("manifest", []),
        "generated_files": outputs.get("merged_files", {}),
        "validation_attempts": outputs.get("validation_attempts", 0),
        "validation_errors": errors,
        "execution_state": outputs.get("execution_state")
    }

def resume_development_approval(db: Session, project_id: str, status: str, comments: Optional[str] = None, reviewer_name: Optional[str] = "Lead Developer", rejected_modules: Optional[List[str]] = None) -> Dict[str, Any]:
    config = get_development_config(project_id)
    
    feedback = {
        "status": status,
        "comments": comments or "",
        "reviewer_name": reviewer_name or "Lead Developer",
        "rejected_modules": rejected_modules or []
    }
    
    # 1. Update graph state at human_approval
    compiled_development_graph.update_state(config, {"human_feedback": feedback}, as_node="human_approval")
    
    # 2. Resume graph
    outputs = compiled_development_graph.invoke(None, config)
    
    phase = outputs.get("phase", "DEVELOPMENT_PLANNING")
    errors = outputs.get("validation_errors", [])
    
    return {
        "status": phase,
        "manifest": outputs.get("manifest", []),
        "generated_files": outputs.get("merged_files", {}),
        "validation_attempts": outputs.get("validation_attempts", 0),
        "validation_errors": errors,
        "execution_state": outputs.get("execution_state")
    }

def get_latest_development_version(db: Session, project_id: str):
    return db.query(project_service.models.DevelopmentVersion).filter(
        project_service.models.DevelopmentVersion.project_id == project_id
    ).order_by(project_service.models.DevelopmentVersion.version_num.desc()).first()

def get_development_history(db: Session, project_id: str):
    versions = db.query(project_service.models.DevelopmentVersion).filter(
        project_service.models.DevelopmentVersion.project_id == project_id
    ).order_by(project_service.models.DevelopmentVersion.version_num.desc()).all()
    
    result = []
    for v in versions:
        manifest_payload = json.loads(v.raw_manifest)
        result.append({
            "version_num": v.version_num,
            "manifest": manifest_payload.get("files", []),
            "contents": manifest_payload.get("contents", {}),
            "artifact_zip_path": v.artifact_zip_path,
            "artifact_paths": json.loads(v.artifact_paths) if v.artifact_paths else {},
            "approval_status": v.approval_status,
            "created_at": v.created_at.isoformat()
        })
    return result

# --- NEW QUERY SERVICE ENDPOINTS ---

def get_development_tasks(db: Session, project_id: str) -> List[Dict[str, Any]]:
    tasks = db.query(project_service.models.DevelopmentTask).filter(
        project_service.models.DevelopmentTask.project_id == project_id
    ).order_by(project_service.models.DevelopmentTask.created_at.desc()).all()
    
    return [{
        "task_id": t.task_id,
        "module": t.module,
        "description": t.description,
        "owner_agent": t.owner_agent,
        "dependencies": json.loads(t.dependencies) if t.dependencies else [],
        "priority": t.priority,
        "status": t.status,
        "requirement_id": t.requirement_id,
        "design_section_id": t.design_section_id
    } for t in tasks]

def get_development_agents(db: Session, project_id: str) -> List[Dict[str, Any]]:
    # Get latest version agent outputs
    latest_version = get_latest_development_version(db, project_id)
    if not latest_version:
        return []
        
    outputs = db.query(project_service.models.DevelopmentAgentOutput).filter(
        project_service.models.DevelopmentAgentOutput.version_id == latest_version.id
    ).all()
    
    return [{
        "agent_name": o.agent_name,
        "status": o.status,
        "files_count": len(json.loads(o.output_payload).get("files", {})),
        "created_at": o.created_at.isoformat()
    } for o in outputs]

def get_development_logs(db: Session, project_id: str) -> List[Dict[str, Any]]:
    logs = db.query(project_service.models.DevelopmentExecutionLog).filter(
        project_service.models.DevelopmentExecutionLog.project_id == project_id
    ).order_by(project_service.models.DevelopmentExecutionLog.started_at.desc()).all()
    
    return [{
        "node_name": l.node_name,
        "agent_name": l.agent_name,
        "stage": l.stage,
        "started_at": l.started_at.isoformat(),
        "completed_at": l.completed_at.isoformat() if l.completed_at else None,
        "duration": l.duration,
        "status": l.status,
        "error_message": l.error_message,
        "llm_provider": l.llm_provider,
        "prompt_tokens": l.prompt_tokens,
        "completion_tokens": l.completion_tokens,
        "task_id": l.task_id or "",
        "files_generated": json.loads(l.files_generated) if l.files_generated else []
    } for l in logs]

def get_development_files(db: Session, project_id: str) -> Dict[str, Any]:
    latest_version = get_latest_development_version(db, project_id)
    if not latest_version:
        return {"manifest": [], "contents": {}}
        
    payload = json.loads(latest_version.raw_manifest)
    return {
        "manifest": payload.get("files", []),
        "contents": payload.get("contents", {})
    }

def get_development_artifacts(db: Session, project_id: str) -> List[Dict[str, Any]]:
    latest_version = get_latest_development_version(db, project_id)
    if not latest_version:
        return []
        
    artifacts = db.query(project_service.models.DevelopmentArtifact).filter(
        project_service.models.DevelopmentArtifact.version_id == latest_version.id
    ).all()
    
    return [{
        "id": a.id,
        "artifact_type": a.artifact_type,
        "file_path": a.file_path,
        "checksum": a.checksum,
        "created_at": a.created_at.isoformat()
    } for a in artifacts]
