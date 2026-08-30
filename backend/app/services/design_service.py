import json
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional

from ..agents.design_agent import compiled_design_graph, save_sdd_version_to_db
from ..schemas import SDDOutput, ProjectDocument
from . import project_service

def get_design_config(project_id: str) -> Dict[str, Any]:
    # Namespaced thread ID as requested: "design:{project_id}"
    return {"configurable": {"thread_id": f"design:{project_id}"}}

def get_design_state_details(project_id: str, db: Session) -> Dict[str, Any]:
    config = get_design_config(project_id)
    state = compiled_design_graph.get_state(config)
    
    # Load requirements document from ProjectAgentState
    agent_state = db.query(project_service.models.ProjectAgentState).filter(
        project_service.models.ProjectAgentState.project_id == project_id
    ).first()
    
    approved_document = None
    if agent_state and agent_state.document:
        try:
            approved_document = ProjectDocument(**json.loads(agent_state.document))
        except Exception:
            pass
            
    if not state.values:
        return {
            "approved_document": approved_document,
            "project_metadata": {"srs_status": "APPROVED"},
            "sdd": None,
            "validation_attempts": 0,
            "validation_errors": [],
            "phase": "generating",
            "active_stage": None
        }
        
    active_stage = None
    if state.next:
        node = state.next[0]
        if "generation" in node:
            active_stage = "DESIGN_GENERATION"
        elif "gap" in node:
            active_stage = "DESIGN_GAP"
        elif "validation" in node:
            active_stage = "DESIGN_VALIDATION"
        elif "finalization" in node:
            active_stage = "DESIGN_FINALIZATION"
            
    phase = state.values.get("phase", "generating")
    design_doc, _ = get_latest_design_version(db, project_id)
    proj = project_service.get_project(db, project_id)
    if (design_doc and design_doc.approval_status == "APPROVED") or (proj and (proj.status == "APPROVED" or proj.current_phase == "DEVELOPMENT")):
        phase = "approved"

    return {
        "approved_document": approved_document,
        "project_metadata": state.values.get("project_metadata", {}),
        "sdd": state.values.get("sdd"),
        "validation_attempts": state.values.get("validation_attempts", 0),
        "validation_errors": state.values.get("validation_errors", []),
        "phase": phase,
        "active_stage": active_stage
    }

def start_design_generation(db: Session, project_id: str) -> Dict[str, Any]:
    config = get_design_config(project_id)
    
    # Load approved requirement document
    agent_state = db.query(project_service.models.ProjectAgentState).filter(
        project_service.models.ProjectAgentState.project_id == project_id
    ).first()
    
    if not agent_state or not agent_state.document:
        raise ValueError("Linked project requirements must exist before design generation.")
        
    approved_document = ProjectDocument(**json.loads(agent_state.document))
    
    # Log start
    project_service.log_activity(db, project_id, "DESIGN_STARTED", "Generating architecture design...")
    project_service.update_project_status(db, project_id, "DESIGN", "IN_PROGRESS")
    
    # Invoke graph
    inputs = {
        "project_id": project_id,
        "approved_document": approved_document,
        "project_metadata": {"srs_status": "APPROVED"},
        "validation_attempts": 0,
        "validation_errors": [],
        "phase": "generating"
    }
    
    # Invoke graph safely
    try:
        outputs = compiled_design_graph.invoke(inputs, config)
    except Exception as e:
        print(f"[Design Service] Graph invoke interrupt/notice: {e}")
        outputs = {}
        
    latest_state = compiled_design_graph.get_state(config)
    state_values = latest_state.values if (latest_state and latest_state.values) else {}
    
    sdd = state_values.get("sdd") or outputs.get("sdd")
    phase = state_values.get("phase") or outputs.get("phase") or "awaiting_design_generation_approval"
    errors = state_values.get("validation_errors") or outputs.get("validation_errors", [])
    
    # Ensure SDD is populated with fallbacks if LLM hit rate limit
    if not sdd:
        from ..agents.design_agent import build_fallback_sdd
        sdd = build_fallback_sdd(approved_document, {"srs_status": "APPROVED"})
        compiled_design_graph.update_state(config, {"sdd": sdd, "phase": "awaiting_design_generation_approval"})
        phase = "awaiting_design_generation_approval"
        
    project_service.update_project_status(db, project_id, "DESIGN", "AWAITING_APPROVAL")
        
    return {
        "status": phase,
        "sdd": sdd,
        "validation_attempts": state_values.get("validation_attempts", 0),
        "validation_errors": errors
    }

def resume_design_approval(
    db: Session,
    project_id: str,
    status: str,
    comments: Optional[str] = None,
    reviewer_name: Optional[str] = "Human Administrator",
    stage: Optional[str] = None
) -> Dict[str, Any]:
    config = get_design_config(project_id)
    state = compiled_design_graph.get_state(config)
    
    if not state.next:
        print(f"[Design Service] Graph for {project_id} not in interrupted state. Auto-completing Design approval...")
        latest_state = compiled_design_graph.get_state(config)
        sdd = latest_state.values.get("sdd") if latest_state.values else None
        
        if not sdd:
            # Fetch approved document
            agent_state = db.query(project_service.models.ProjectAgentState).filter(
                project_service.models.ProjectAgentState.project_id == project_id
            ).first()
            if agent_state and agent_state.document:
                approved_doc = ProjectDocument(**json.loads(agent_state.document))
                from ..agents.design_agent import build_fallback_sdd
                sdd = build_fallback_sdd(approved_doc, {"srs_status": "APPROVED"})
                
        if sdd:
            save_sdd_version_to_db(project_id, sdd, status="APPROVED", comments=comments or "Design Specification Approved")
            
        project_service.update_project_status(db, project_id, "DESIGN", "APPROVED")
        project = project_service.get_project(db, project_id)
        if project:
            project.current_phase = "DEVELOPMENT"
            project.status = "IN_PROGRESS"
            db.commit()
            project_service.log_activity(db, project_id, "PHASE_TRANSITION", "Project transitioned automatically from DESIGN to DEVELOPMENT phase.")
            
            from . import development_service
            try:
                development_service.start_development_generation(db, project_id)
            except Exception as de:
                print(f"Error auto-starting development generation: {de}")
                pass
            
        return {"status": "approved", "sdd": sdd, "validation_attempts": 0, "validation_errors": []}
        
    active_node = state.next[0]
    
    if not stage:
        if "generation" in active_node:
            stage = "DESIGN_GENERATION"
        elif "gap" in active_node:
            stage = "DESIGN_GAP"
        elif "validation" in active_node:
            stage = "DESIGN_VALIDATION"
        elif "finalization" in active_node:
            stage = "DESIGN_FINALIZATION"
            
    # 1. Log review in DB
    review_schema = project_service.schemas.HumanReviewSubmit(
        status=status,
        comments=comments,
        reviewer_name=reviewer_name,
        stage=stage
    )
    project_service.submit_human_review(db, project_id, "DESIGN", review_schema)
    
    # 2. Update graph state with feedback
    feedback = {"status": status, "comments": comments or ""}
    compiled_design_graph.update_state(config, {"user_feedback": feedback}, as_node=active_node)
    
    # 3. Resume the graph safely
    try:
        outputs = compiled_design_graph.invoke(None, config)
    except Exception as e:
        print(f"[Design Service] Resume invoke interrupt/notice: {e}")
        outputs = {}
        
    latest_state = compiled_design_graph.get_state(config)
    state_values = latest_state.values if (latest_state and latest_state.values) else {}
    
    phase = state_values.get("phase") or outputs.get("phase") or "awaiting_design_gap_approval"
    sdd = state_values.get("sdd") or outputs.get("sdd")
    errors = state_values.get("validation_errors") or outputs.get("validation_errors", [])
    
    # Sync database based on approval or rejection
    if phase in ("completed", "approved") or status == "APPROVED":
        phase = "approved"
        try:
            compiled_design_graph.update_state(config, {"phase": "approved"})
        except Exception:
            pass
        if sdd:
            save_sdd_version_to_db(project_id, sdd, status="APPROVED", comments=comments or "Design Approved")
        project_service.update_project_status(db, project_id, "DESIGN", "APPROVED")
        project = project_service.get_project(db, project_id)
        if project:
            project.current_phase = "DEVELOPMENT"
            project.status = "IN_PROGRESS"
            db.commit()
            project_service.log_activity(db, project_id, "PHASE_TRANSITION", "Project transitioned automatically from DESIGN to DEVELOPMENT phase.")
            
            from . import development_service
            try:
                development_service.start_development_generation(db, project_id)
            except Exception as de:
                print(f"Error auto-starting development generation: {de}")
                pass
    elif status == "REJECTED":
        project_service.update_project_status(db, project_id, "DESIGN", "REJECTED")
        
    return {
        "status": phase,
        "sdd": sdd,
        "validation_attempts": state_values.get("validation_attempts", 0),
        "validation_errors": errors
    }

def get_latest_design_version(db: Session, project_id: str):
    design_doc = db.query(project_service.models.DesignDocument).filter(
        project_service.models.DesignDocument.project_id == project_id
    ).first()
    if not design_doc:
        return None, None
    latest_ver = db.query(project_service.models.DesignVersion).filter(
        project_service.models.DesignVersion.design_document_id == design_doc.id
    ).order_by(project_service.models.DesignVersion.version_num.desc()).first()
    return design_doc, latest_ver

def get_effective_sdd_data(db: Session, project_id: str):
    design_doc, latest_ver = get_latest_design_version(db, project_id)
    if latest_ver and latest_ver.raw_sdd:
        try:
            return json.loads(latest_ver.raw_sdd), latest_ver.version_num, (design_doc.approval_status if design_doc else "APPROVED")
        except Exception:
            pass
            
    design_state = get_design_state_details(project_id, db)
    sdd = design_state.get("sdd")
    if not sdd and design_state.get("approved_document"):
        from ..agents.design_agent import build_fallback_sdd
        sdd = build_fallback_sdd(design_state.get("approved_document"), {})
    return sdd, 1, (design_doc.approval_status if design_doc else "DRAFT")

def get_design_history(db: Session, project_id: str):
    design_doc, _ = get_latest_design_version(db, project_id)
    if not design_doc:
        return []
    versions = db.query(project_service.models.DesignVersion).filter(
        project_service.models.DesignVersion.design_document_id == design_doc.id
    ).order_by(project_service.models.DesignVersion.version_num.desc()).all()
    history = []
    for v in versions:
        history.append({
            "id": v.id,
            "version_num": v.version_num,
            "reviewer_comments": v.reviewer_comments,
            "created_at": v.created_at.isoformat() if v.created_at else None,
            "sdd": json.loads(v.raw_sdd) if v.raw_sdd else None
        })
    return history
