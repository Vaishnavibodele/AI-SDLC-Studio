import json
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from .. import models, schemas

def create_project(db: Session, project_in: schemas.ProjectCreate) -> models.Project:
    project = models.Project(
        name=project_in.name,
        description=project_in.description,
        current_phase="REQUIREMENT",
        status="IN_PROGRESS"
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    
    # Log creation
    log_activity(db, project.id, "PROJECT_CREATED", f"Project '{project.name}' initialized.")
    return project

def get_project(db: Session, project_id: str) -> models.Project:
    return db.query(models.Project).filter(models.Project.id == project_id).first()

def list_projects(db: Session):
    return db.query(models.Project).order_by(models.Project.created_at.desc()).all()

def update_project_status(db: Session, project_id: str, phase: str, status: str) -> models.Project:
    project = get_project(db, project_id)
    if project:
        project.current_phase = phase
        project.status = status
        db.commit()
        db.refresh(project)
    return project

def update_with_state(
    db: Session,
    project_id: str,
    phase: str,
    status: str,
    current_state: str,
    document: Optional[Dict[str, Any]] = None,
    messages: Optional[List[Dict[str, Any]]] = None,
    memory: Optional[Dict[str, Any]] = None,
    missing_info: Optional[List[str]] = None,
    validation_attempts: int = 0,
    last_reviewer_comments: Optional[str] = None
) -> models.Project:
    # 1. Update Project
    project = get_project(db, project_id)
    if not project:
        return None
    project.current_phase = phase
    project.status = status
    
    # 2. Update ProjectAgentState
    agent_state = db.query(models.ProjectAgentState).filter(models.ProjectAgentState.project_id == project_id).first()
    if not agent_state:
        agent_state = models.ProjectAgentState(project_id=project_id)
        db.add(agent_state)
        
    agent_state.current_state = current_state
    if document is not None:
        agent_state.document = json.dumps(document)
    if messages is not None:
        agent_state.messages = json.dumps(messages)
    if memory is not None:
        agent_state.memory = json.dumps(memory)
    if missing_info is not None:
        agent_state.missing_info = json.dumps(missing_info)
    agent_state.validation_attempts = validation_attempts
    if last_reviewer_comments is not None:
        agent_state.last_reviewer_comments = last_reviewer_comments
        
    db.commit()
    db.refresh(project)
    return project

def create_version_snapshot(db: Session, project_id: str, document: Dict[str, Any], reviewer_comments: Optional[str] = None) -> models.VersionSnapshot:
    # Find next version number
    last_snapshot = db.query(models.VersionSnapshot).filter(
        models.VersionSnapshot.project_id == project_id
    ).order_by(models.VersionSnapshot.version_num.desc()).first()
    
    version_num = (last_snapshot.version_num + 1) if last_snapshot else 1
    
    snapshot = models.VersionSnapshot(
        project_id=project_id,
        version_num=version_num,
        document=json.dumps(document),
        reviewer_comments=reviewer_comments
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    
    log_activity(db, project_id, "VERSION_SNAPSHOT_SAVED", f"Saved full document snapshot version {version_num}")
    return snapshot

def get_requirements(db: Session, project_id: str) -> models.Requirement:
    return db.query(models.Requirement).filter(models.Requirement.project_id == project_id).first()

def create_or_update_requirement_srs(db: Session, project_id: str, srs_data: Dict[str, Any], status: str = "PENDING", comments: str = "") -> models.Requirement:
    # Check if a requirement already exists for this project
    req = get_requirements(db, project_id)
    if not req:
        req = models.Requirement(project_id=project_id, approval_status=status)
        db.add(req)
        db.commit()
        db.refresh(req)
        version_num = 1
    else:
        req.approval_status = status
        db.commit()
        # Find next version number
        last_version = db.query(models.RequirementVersion).filter(models.RequirementVersion.requirement_id == req.id).order_by(models.RequirementVersion.version_num.desc()).first()
        version_num = (last_version.version_num + 1) if last_version else 1
        
    # Append version
    req_version = models.RequirementVersion(
        requirement_id=req.id,
        version_num=version_num,
        raw_srs=json.dumps(srs_data),
        reviewer_comments=comments
    )
    db.add(req_version)
    db.commit()
    
    log_activity(db, project_id, "SRS_VERSION_SAVED", f"SRS version {version_num} generated/saved with status: {status}")
    return req

def get_latest_srs_version(db: Session, project_id: str) -> models.RequirementVersion:
    req = get_requirements(db, project_id)
    if not req:
        return None
    return db.query(models.RequirementVersion).filter(models.RequirementVersion.requirement_id == req.id).order_by(models.RequirementVersion.version_num.desc()).first()

def get_effective_srs_data(db: Session, project_id: str):
    proj = get_project(db, project_id)
    if not proj:
        return None, 1
        
    latest_srs = get_latest_srs_version(db, project_id)
    if latest_srs and latest_srs.raw_srs:
        try:
            return json.loads(latest_srs.raw_srs), latest_srs.version_num
        except Exception:
            pass
            
    from . import agent_service
    state_details = agent_service.get_agent_state_details(project_id)
    doc = state_details.get("document")
    mem = state_details.get("memory")
    
    doc_dict = doc.dict() if (doc and hasattr(doc, "dict")) else (doc if isinstance(doc, dict) else {})
    mem_dict = mem.dict() if (mem and hasattr(mem, "dict")) else (mem if isinstance(mem, dict) else {})
    
    if not doc_dict and not mem_dict:
        return None, 1
        
    reqs_list = doc_dict.get("requirements") or []
    req_titles = []
    for i, r in enumerate(reqs_list):
        if isinstance(r, dict):
            req_titles.append(f"{r.get('requirement_id', f'REQ-{i+1:03d}')}: {r.get('title', '')} - {r.get('statement', '')}")
        else:
            req_titles.append(str(r))
            
    if not req_titles and mem_dict.get("functional_requirements"):
        req_titles = [str(r) for r in mem_dict.get("functional_requirements", [])]
        
    non_func = []
    for r in reqs_list:
        if isinstance(r, dict) and r.get("requirement_type") == "non_functional":
            non_func.append(f"{r.get('requirement_id', '')}: {r.get('statement', '')}")
    if not non_func and mem_dict.get("non_functional_requirements"):
        non_func = [str(r) for r in mem_dict.get("non_functional_requirements", [])]

    summary = doc_dict.get("project_summary") or mem_dict.get("project_summary") or proj.description or "Requirements specification document."
    problem = doc_dict.get("problem_statement") or proj.description or "Problem statement under analysis."
    goals = doc_dict.get("business_goals") or (mem_dict.get("business_goals") if mem_dict.get("business_goals") else ["Achieve project requirements."])
    if isinstance(goals, str):
        goals = [goals]

    srs_data = {
        "project_name": proj.name,
        "document_information": f"Classification: Enterprise Confidentially. Author: AI SDLC Studio. Project: {proj.name}.",
        "revision_history": "v1.0.0 - Requirement Specification Draft Export.",
        "approval_history": f"Status: {proj.status}",
        "executive_summary": summary,
        "problem_statement": problem,
        "business_objectives": ", ".join(goals) if isinstance(goals, list) else str(goals),
        "stakeholders": doc_dict.get("stakeholders") or ["Product Owner", "End Users"],
        "user_personas": ["Primary User Persona"],
        "actors": doc_dict.get("actors") or mem_dict.get("target_users") or ["User"],
        "scope": f"Software requirements definition for {proj.name}.",
        "out_of_scope": "Manual offline processes.",
        "business_requirements": req_titles or ["Core functional capabilities."],
        "functional_requirements": req_titles or ["System shall process user inputs."],
        "non_functional_requirements": non_func or ["System availability and performance metrics."],
        "business_rules": ["Standard authorization enforcement."],
        "user_stories": [f"As a user, I want {r.get('title', 'feature')}" for r in reqs_list if isinstance(r, dict)] if reqs_list else ["As a user, I want to interact with the platform."],
        "use_cases": ["Core User Workflow"],
        "acceptance_criteria": ["Given valid input, system processes request successfully."],
        "ui_requirements": ["Responsive web UI."],
        "navigation_flow": ["Landing Page -> Main View"],
        "data_requirements": ["Relational database persistence."],
        "security_requirements": ["Encrypted TLS communications."],
        "integration_requirements": [str(d) for d in doc_dict.get("dependencies", [])] or ["REST API integration."],
        "performance_requirements": ["Response time under 2 seconds."],
        "compliance_requirements": ["Data protection compliance."],
        "constraints": doc_dict.get("constraints") or mem_dict.get("constraints") or ["Web architecture."],
        "assumptions": doc_dict.get("assumptions") or mem_dict.get("assumptions") or ["Standard user environment."],
        "risks": doc_dict.get("risks") or ["Operational latency."],
        "dependencies": doc_dict.get("dependencies") or ["Backend APIs."],
        "requirement_traceability_matrix": [{"id": f"REQ-{i+1:03d}", "title": f"Requirement {i+1}", "description": str(r), "category": "Functional"} for i, r in enumerate(req_titles)]
    }
    
    return srs_data, 1

def submit_human_review(db: Session, project_id: str, phase: str, review_in: schemas.HumanReviewSubmit) -> models.HumanReview:
    review = models.HumanReview(
        project_id=project_id,
        phase=phase,
        status=review_in.status,
        comments=review_in.comments,
        reviewer_name=review_in.reviewer_name
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    
    # Update project status accordingly
    proj_status = "APPROVED" if review_in.status == "APPROVED" else "REJECTED"
    update_project_status(db, project_id, phase, proj_status)
    
    # Update requirement status if it is the Requirement phase
    if phase == "REQUIREMENT":
        req = get_requirements(db, project_id)
        if req:
            req.approval_status = review_in.status
            db.commit()
            
    log_activity(db, project_id, f"HUMAN_REVIEW_{review_in.status}", f"Reviewer {review_in.reviewer_name} marked phase {phase} as {review_in.status}. Comments: {review_in.comments or 'None'}")
    return review

def log_activity(db: Session, project_id: str, action: str, details: str = None) -> models.ActivityLog:
    log = models.ActivityLog(project_id=project_id, action=action, details=details)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log

def get_activity_logs(db: Session, project_id: str):
    return db.query(models.ActivityLog).filter(models.ActivityLog.project_id == project_id).order_by(models.ActivityLog.timestamp.desc()).all()
