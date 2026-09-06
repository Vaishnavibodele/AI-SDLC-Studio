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

def calculate_elicitation_completeness(memory_dict: Optional[dict] = None) -> int:
    """Calculates chat elicitation memory completeness (0-100%) across key BA fields."""
    if not memory_dict:
        return 0
    score = 0
    
    # 1. Project Summary
    summary = memory_dict.get("project_summary", "") or ""
    if len(summary.strip()) >= 150: score += 20
    elif len(summary.strip()) >= 50: score += 15
    elif len(summary.strip()) > 0: score += 10

    # 2. Business Goals
    goals = memory_dict.get("business_goals", "") or ""
    if len(goals.strip()) >= 80: score += 15
    elif len(goals.strip()) >= 30: score += 10
    elif len(goals.strip()) > 0: score += 5

    # 3. Target Users
    users = memory_dict.get("target_users", []) or []
    if len(users) >= 2: score += 10
    elif len(users) == 1: score += 5

    # 4. Functional Requirements
    func = memory_dict.get("functional_requirements", []) or []
    if len(func) >= 4: score += 25
    elif len(func) >= 2: score += 18
    elif len(func) == 1: score += 10

    # 5. Non-Functional Requirements
    nfr = memory_dict.get("non_functional_requirements", []) or []
    if len(nfr) >= 3: score += 15
    elif len(nfr) >= 1: score += 10

    # 6. Constraints & Assumptions
    constraints = memory_dict.get("constraints", []) or []
    assumptions = memory_dict.get("assumptions", []) or []
    ac = memory_dict.get("acceptance_criteria", []) or []
    if len(constraints) > 0: score += 5
    if len(assumptions) > 0: score += 5
    if len(ac) > 0: score += 5

    # 7. Open Questions Penalty
    questions = memory_dict.get("open_questions", []) or []
    if questions:
        score = max(0, score - (len(questions) * 5))

    return min(100, max(0, score))


def calculate_srs_completeness(srs_data: Optional[dict] = None, doc_dict: Optional[dict] = None) -> int:
    """Calculates coverage completeness of the compiled IEEE-830 SRS document."""
    if doc_dict:
        from . import requirement_validator
        try:
            doc_obj = schemas.ProjectDocument(**doc_dict)
            score, _ = requirement_validator.check_completeness(doc_obj, backlog_required=len(doc_obj.epics) > 0)
            return score
        except Exception:
            pass

    if srs_data:
        total_weight = 0.0
        
        # Core Sections (High Weight - 50%)
        core_sections = ["executive_summary", "problem_statement", "business_objectives", "scope", "functional_requirements", "non_functional_requirements"]
        core_filled = 0
        for s in core_sections:
            val = srs_data.get(s)
            if val:
                val_str = str(val) if not isinstance(val, list) else " ".join(str(i) for i in val)
                if len(val_str.strip()) > 100:
                    core_filled += 1
                elif len(val_str.strip()) > 20:
                    core_filled += 0.5
        total_weight += (core_filled / len(core_sections)) * 50.0

        # Detailed Engineering Sections (30%)
        eng_sections = ["user_personas", "actors", "business_rules", "user_stories", "use_cases", "acceptance_criteria", "ui_requirements", "navigation_flow", "data_requirements", "security_requirements", "integration_requirements", "performance_requirements"]
        eng_filled = 0
        for s in eng_sections:
            val = srs_data.get(s)
            if val and (not isinstance(val, list) or len(val) > 0):
                eng_filled += 1
        total_weight += (eng_filled / len(eng_sections)) * 30.0

        # Governance & Constraints Sections (20%)
        gov_sections = ["document_information", "revision_history", "approval_history", "out_of_scope", "compliance_requirements", "constraints", "assumptions", "risks", "dependencies", "requirement_traceability_matrix"]
        gov_filled = 0
        for s in gov_sections:
            val = srs_data.get(s)
            if val and (not isinstance(val, list) or len(val) > 0):
                gov_filled += 1
        total_weight += (gov_filled / len(gov_sections)) * 20.0

        return min(100, max(0, int(round(total_weight))))

    return 0


def calculate_logical_requirement_completeness(memory_dict: Optional[dict] = None, srs_data: Optional[dict] = None, doc_dict: Optional[dict] = None, is_approved: bool = False) -> int:
    """
    Logically calculates Requirement Completeness % (0 - 100%) based on phase and status.
    """
    if is_approved or srs_data:
        srs_score = calculate_srs_completeness(srs_data=srs_data, doc_dict=doc_dict)
        if srs_score > 0:
            return srs_score
    return calculate_elicitation_completeness(memory_dict)

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

def create_or_update_requirement_srs(db: Session, project_id: str, srs_data: Any, status: str = "PENDING", comments: str = "") -> models.Requirement:
    # Safely convert to dict
    if hasattr(srs_data, "model_dump"):
        raw_dict = srs_data.model_dump()
    elif hasattr(srs_data, "dict"):
        raw_dict = srs_data.dict()
    elif isinstance(srs_data, dict):
        raw_dict = srs_data
    elif isinstance(srs_data, str):
        try:
            raw_dict = json.loads(srs_data)
        except Exception:
            raw_dict = {"project_name": "Project", "raw_content": srs_data}
    else:
        raw_dict = {"project_name": "Project"}

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
        raw_srs=json.dumps(raw_dict),
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
            parsed = json.loads(latest_srs.raw_srs)
            if isinstance(parsed, dict) and len(parsed.get("functional_requirements", [])) > 0:
                return parsed, latest_srs.version_num
        except Exception:
            pass
            
    from . import agent_service
    state_details = agent_service.get_agent_state_details(project_id)
    doc = state_details.get("document")
    mem = state_details.get("memory")
    
    doc_dict = doc.dict() if (doc and hasattr(doc, "dict")) else (doc if isinstance(doc, dict) else {})
    mem_dict = mem.dict() if (mem and hasattr(mem, "dict")) else (mem if isinstance(mem, dict) else {})
    
    reqs_list = doc_dict.get("requirements") or []
    
    # Process functional requirements strictly from user input/memory
    func_reqs = []
    func_titles = []
    if reqs_list:
        for i, r in enumerate(reqs_list):
            if isinstance(r, dict):
                if r.get("requirement_type", "functional") == "functional":
                    req_id = r.get("requirement_id") or f"REQ-F{len(func_reqs)+1:03d}"
                    title = r.get("title", "")
                    stmt = r.get("statement", "")
                    prio = r.get("priority", "must_have").upper().replace("_", " ")
                    actor = r.get("actor") or "User"
                    evidence = r.get("source", {}).get("source_text") if isinstance(r.get("source"), dict) else r.get("source_evidence", "")
                    evidence_str = f"\nEvidence: {evidence}" if evidence else ""
                    func_reqs.append(f"[{req_id}] {title} (Priority: {prio}, Actor: {actor})\nDescription: {stmt}{evidence_str}")
                    func_titles.append((req_id, title or stmt, actor, stmt))
            elif isinstance(r, str):
                func_reqs.append(f"[REQ-F{len(func_reqs)+1:03d}] {r}")
                func_titles.append((f"REQ-F{len(func_reqs)+1:03d}", r, "User", r))
                
    if not func_reqs and mem_dict.get("functional_requirements"):
        for i, r in enumerate(mem_dict.get("functional_requirements", [])):
            func_reqs.append(f"[REQ-F{i+1:03d}] {r}")
            func_titles.append((f"REQ-F{i+1:03d}", r, "User", r))

    if not func_reqs:
        func_reqs = ["Not specified in the provided requirements."]

    # Process non-functional requirements strictly from input/memory
    non_func_reqs = []
    if reqs_list:
        for i, r in enumerate(reqs_list):
            if isinstance(r, dict) and r.get("requirement_type") == "non_functional":
                req_id = r.get("requirement_id") or f"REQ-NF{len(non_func_reqs)+1:03d}"
                stmt = r.get("statement", "")
                non_func_reqs.append(f"[{req_id}] {stmt}")
            elif isinstance(r, str) and ("nfr" in r.lower() or "non-functional" in r.lower()):
                non_func_reqs.append(f"[REQ-NF{len(non_func_reqs)+1:03d}] {r}")
                
    if not non_func_reqs and mem_dict.get("non_functional_requirements"):
        for i, r in enumerate(mem_dict.get("non_functional_requirements", [])):
            non_func_reqs.append(f"[REQ-NF{i+1:03d}] {r}")

    if not non_func_reqs:
        non_func_reqs = ["Not specified in the provided requirements."]

    summary = doc_dict.get("project_summary") or mem_dict.get("project_summary") or proj.description or f"Software Requirements Specification for {proj.name}."
    problem = doc_dict.get("problem_statement") or proj.description or f"Requirements for {proj.name} as specified by user input."
    
    raw_goals = doc_dict.get("business_goals") or mem_dict.get("business_goals")
    if isinstance(raw_goals, str):
        raw_goals = [raw_goals]
    elif not raw_goals:
        raw_goals = ["Not specified in the provided requirements."]

    import re

    def _derive_user_story_and_ac(actor_val: str, clean_action_val: str, clean_stmt_val: str):
        actor_sing = actor_val.rstrip('s').strip() if actor_val.lower().endswith('s') and not actor_val.lower().endswith('ss') else actor_val.strip()
        if not actor_sing or actor_sing == "User":
            actor_sing = "User"
        art = "an" if actor_sing and actor_sing[0].lower() in "aeiou" else "a"
        action_lower = clean_action_val.lower().strip()
        
        # Exclude Non-Functional Requirements
        is_nfr = any(k in action_lower or k in clean_stmt_val.lower() for k in [
            "response time", "latency", "https", "tls", "gdpr", "soc2", "security", "encryption", "sla", "uptime", "throughput", "concurrency"
        ])
        if is_nfr:
            return None, None, None
            
        action_clean = re.sub(r'^(?:[a-zA-Z]+s?\s+can\s+)', '', action_lower, flags=re.IGNORECASE).strip()
        if not action_clean:
            action_clean = action_lower

        if any(k in action_clean for k in ["view", "see", "display", "check", "browse", "read", "monitor", "search", "track"]):
            topic = re.sub(r'^(?:view|see|display|check|browse|read|monitor|search|track)\s*', '', action_clean).strip()
            benefit = f"stay informed about relevant {topic or 'information'}"
            ac_given = f"Given {art} {actor_sing} is accessing the system"
            ac_when = f"when they request to {action_clean}"
            ac_then = f"then the system retrieves and displays the requested {topic or 'details'}."
            flow_step1 = f"{actor_sing} selects the option to {action_clean}."
            flow_step2 = f"System retrieves and presents the requested information."
            flow_step3 = f"{actor_sing} reviews the displayed details."
        elif any(k in action_clean for k in ["buy", "purchase", "pay", "checkout", "order", "book", "reserve"]):
            topic = re.sub(r'^(?:buy|purchase|pay|checkout|order|book|reserve)\s*', '', action_clean).strip()
            benefit = f"successfully obtain the requested {topic or 'items or services'}"
            ac_given = f"Given {art} {actor_sing} selects {topic or 'items'} to {action_clean}"
            ac_when = f"when they confirm and submit the transaction"
            ac_then = f"then the system processes the request and provides confirmation."
            flow_step1 = f"{actor_sing} initiates the process to {action_clean}."
            flow_step2 = f"System validates transaction details and processes the request."
            flow_step3 = f"System completes the transaction and displays confirmation."
        elif any(k in action_clean for k in ["manage", "create", "add", "edit", "update", "delete", "configure", "setup"]):
            topic = re.sub(r'^(?:manage|create|add|edit|update|delete|configure|setup)\s*', '', action_clean).strip()
            benefit = f"keep {topic or 'system records'} accurate and up to date"
            ac_given = f"Given {art} {actor_sing} accesses the management interface"
            ac_when = f"when they submit updates to {action_clean}"
            ac_then = f"then the system validates and saves the updated configuration."
            flow_step1 = f"{actor_sing} opens the interface to {action_clean}."
            flow_step2 = f"System validates the submitted data."
            flow_step3 = f"System updates the records and confirms successful save."
        else:
            benefit = f"accomplish {action_clean} effectively"
            ac_given = f"Given {art} {actor_sing} initiates the request"
            ac_when = f"when valid parameters are provided for {action_clean}"
            ac_then = f"then the system completes the workflow and returns confirmation."
            flow_step1 = f"{actor_sing} initiates request to {action_clean}."
            flow_step2 = f"System validates input parameters and executes business logic."
            flow_step3 = f"System updates state and returns confirmation to {actor_sing}."

        user_story = f"US-{story_num:03d}: As {art} {actor_sing}, I want to {action_clean} so that I can {benefit}."
        acceptance_criterion = f"AC-{story_num:03d}: {ac_given}, {ac_when}, {ac_then}"
        use_case = (
            f"UC-{story_num:03d}: {action_clean.capitalize()}\n"
            f"  • Primary Actor: {actor_sing}\n"
            f"  • Goal: Enable {actor_sing} to {action_clean}.\n"
            f"  • Main Flow:\n"
            f"    1. {flow_step1}\n"
            f"    2. {flow_step2}\n"
            f"    3. {flow_step3}"
        )
        return user_story, acceptance_criterion, use_case

    # Derive user stories, use cases, acceptance criteria, and traceability matrix strictly from confirmed functional requirements
    user_stories = []
    use_cases = []
    acceptance_criteria = []
    rtm_matrix = []

    story_count = 1
    if func_titles:
        for i, (req_id, title, actor, stmt) in enumerate(func_titles):
            clean_stmt = stmt.rstrip('.').strip()
            clean_action = re.sub(r'^(?:[a-zA-Z]+s?\s+can\s+)', '', clean_stmt, flags=re.IGNORECASE).strip()
            actor_sing = actor.rstrip('s') if actor.lower().endswith('s') and not actor.lower().endswith('ss') else actor
            
            story_num = story_count
            u_story, a_criterion, u_case = _derive_user_story_and_ac(actor_sing, clean_action, clean_stmt)
            if u_story:
                user_stories.append(u_story)
                use_cases.append(u_case)
                acceptance_criteria.append(a_criterion)
                story_count += 1
                rtm_matrix.append({
                    "id": req_id,
                    "title": clean_action.capitalize()[:50],
                    "description": clean_stmt,
                    "category": "Functional Requirement"
                })
    
    if not user_stories:
        user_stories = ["Not specified in the provided requirements."]
        use_cases = ["Not specified in the provided requirements."]
        acceptance_criteria = ["Not specified in the provided requirements."]
        rtm_matrix = [{"id": "REQ-001", "title": "Requirements Specification", "description": summary, "category": "Functional Requirement"}]

    # Extract actors strictly from input/memory
    actors = doc_dict.get("actors") or mem_dict.get("target_users")
    if not actors or len(actors) == 0:
        # Check if actors were derived in func_titles
        extracted_actors = list(set([a for _, _, a, _ in func_titles if a and a != "User"]))
        actors = extracted_actors if extracted_actors else ["User"]

    srs_data = {
        "project_name": proj.name,
        "document_information": [
            f"Document Identifier: SRS-DOC-{proj.id[:8].upper()}",
            f"Authoring System: AI SDLC Studio Requirements Engine",
            f"Project Name: {proj.name}",
            f"Standard Compliance: IEEE-830 Software Requirements Specification Standard"
        ],
        "revision_history": [
            "v1.0.0 - Requirements specification derived from user problem statement and clarifications."
        ],
        "approval_history": [
            f"Phase Status: {proj.status}",
            f"Requirement Sign-Off: {proj.status}"
        ],
        "executive_summary": summary,
        "problem_statement": problem,
        "business_objectives": raw_goals,
        "stakeholders": doc_dict.get("stakeholders") or actors or ["Not specified in the provided requirements."],
        "user_personas": doc_dict.get("user_personas") or ["Not specified in the provided requirements."],
        "actors": actors,
        "scope": doc_dict.get("scope") or summary,
        "out_of_scope": doc_dict.get("out_of_scope") or ["Not specified in the provided requirements."],
        "business_requirements": doc_dict.get("business_requirements") or ["Not specified in the provided requirements."],
        "functional_requirements": func_reqs,
        "non_functional_requirements": non_func_reqs,
        "business_rules": doc_dict.get("business_rules") or ["Not specified in the provided requirements."],
        "user_stories": user_stories,
        "use_cases": use_cases,
        "acceptance_criteria": acceptance_criteria,
        "ui_requirements": doc_dict.get("ui_requirements") or ["Not specified in the provided requirements."],
        "navigation_flow": doc_dict.get("navigation_flow") or ["Not specified in the provided requirements."],
        "data_requirements": doc_dict.get("data_requirements") or ["Not specified in the provided requirements."],
        "security_requirements": doc_dict.get("security_requirements") or ["Not specified in the provided requirements."],
        "integration_requirements": doc_dict.get("integration_requirements") or ["Not specified in the provided requirements."],
        "performance_requirements": doc_dict.get("performance_requirements") or ["Not specified in the provided requirements."],
        "compliance_requirements": doc_dict.get("compliance_requirements") or ["Not specified in the provided requirements."],
        "constraints": doc_dict.get("constraints") or mem_dict.get("constraints") or ["Not specified in the provided requirements."],
        "assumptions": doc_dict.get("assumptions") or mem_dict.get("assumptions") or ["Not specified in the provided requirements."],
        "risks": doc_dict.get("risks") or ["Not specified in the provided requirements."],
        "dependencies": doc_dict.get("dependencies") or ["Not specified in the provided requirements."],
        "requirement_traceability_matrix": rtm_matrix
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
