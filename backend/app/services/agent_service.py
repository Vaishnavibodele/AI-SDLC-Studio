import json
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional

from ..agents.requirement_agent import compiled_graph
from ..schemas import RequirementMemory, ProjectDocument
from . import project_service

def get_graph_config(project_id: str) -> Dict[str, Any]:
    return {"configurable": {"thread_id": project_id}}

def get_agent_state_details(project_id: str) -> Dict[str, Any]:
    config = get_graph_config(project_id)
    state = compiled_graph.get_state(config)
    
    if not state.values:
        return {
            "messages": [],
            "memory": RequirementMemory(),
            "document": None,
            "gaps": None,
            "phase": "draft",
            "missing_info": ["Project summary is missing."],
            "validation_attempts": 0,
            "active_stage": None
        }
        
    active_stage = None
    if state.next:
        node = state.next[0]
        if "extraction" in node:
            active_stage = "EXTRACTION"
        elif "gap" in node:
            active_stage = "GAP_DETECTION"
        elif "validation" in node:
            active_stage = "VALIDATION"
        elif "finalization" in node:
            active_stage = "FINALIZATION"
        elif "clarification" in node:
            active_stage = "CLARIFICATION"
            
    return {
        "messages": state.values.get("messages", []),
        "memory": state.values.get("memory", RequirementMemory()),
        "document": state.values.get("document"),
        "gaps": state.values.get("gaps"),
        "phase": state.values.get("phase", "draft"),
        "missing_info": state.values.get("missing_info", []),
        "validation_attempts": state.values.get("validation_attempts", 0),
        "active_stage": active_stage
    }

def run_chat_step(db: Session, project_id: str, message_text: str) -> Dict[str, Any]:
    config = get_graph_config(project_id)
    current_state = get_agent_state_details(project_id)
    
    # Log user message in activity logs
    project_service.log_activity(db, project_id, "USER_MESSAGE", message_text[:100])
    
    state = compiled_graph.get_state(config)
    
    # Check if currently suspended for clarification
    if state.next and "clarification" in state.next[0]:
        print("[Requirement Service] Resuming graph from clarification interrupt...")
        # Resume by submitting user feedback answer
        compiled_graph.update_state(config, {"user_feedback": {"answer": message_text}}, as_node=state.next[0])
        outputs = compiled_graph.invoke(None, config)
    else:
        # Normal flow: append user message to messages list
        messages = list(current_state["messages"])
        messages.append({"sender": "user", "text": message_text})
        
        inputs = {
            "project_id": project_id,
            "messages": messages,
            "memory": current_state["memory"],
            "validation_attempts": current_state["validation_attempts"],
            "phase": current_state["phase"],
            "document": current_state["document"],
            "gaps": current_state["gaps"]
        }
        
        msg_lower = message_text.lower()
        compile_keywords = [
            "generate srs", "compile srs", "finish", "generate requirement", "generate requirements",
            "compile requirement", "compile requirements", "extract requirement", "extract requirements",
            "analyze requirement", "analyze requirements", "create requirement", "create requirements",
            "make requirement", "make requirements", "build requirements", "generate document",
            "process problem statement", "start extraction", "create srs", "build srs"
        ]
        if any(kw in msg_lower for kw in compile_keywords):
            inputs["phase"] = "GENERATING_SRS"
            
        try:
            outputs = compiled_graph.invoke(inputs, config)
        except Exception as e:
            print(f"[Requirement Service] Graph invoke interrupt or notice ({e})")
            outputs = {}
            
    # Process outputs and snapshot state values
    latest_state = compiled_graph.get_state(config)
    state_values = latest_state.values if (latest_state and latest_state.values) else {}
    if not outputs:
        outputs = state_values
        
    phase = state_values.get("phase") or outputs.get("phase") or "draft"
    document = state_values.get("document") or outputs.get("document")
    memory = state_values.get("memory") or outputs.get("memory")
    messages = state_values.get("messages") or outputs.get("messages")
    missing_info = state_values.get("missing_info") or outputs.get("missing_info")
    validation_attempts = state_values.get("validation_attempts") or outputs.get("validation_attempts", 0)
    
    doc_dict = document.dict() if (document and hasattr(document, "dict")) else document
    mem_dict = memory.dict() if (memory and hasattr(memory, "dict")) else memory
    
    # Save state to database
    project_service.update_with_state(
        db=db,
        project_id=project_id,
        phase="REQUIREMENT",
        status="IN_PROGRESS" if phase != "completed" else "APPROVED",
        current_state=phase,
        document=doc_dict,
        messages=messages,
        memory=mem_dict,
        missing_info=missing_info,
        validation_attempts=validation_attempts
    )
    
    # If completed, create version snapshot and transition to design phase
    if phase == "completed" and document:
        project_service.create_version_snapshot(db, project_id, doc_dict, "Final approval")
        project = project_service.get_project(db, project_id)
        if project:
            project.current_phase = "DESIGN"
            project.status = "IN_PROGRESS"
            db.commit()
            project_service.log_activity(db, project_id, "PHASE_TRANSITION", "Project transitioned automatically from REQUIREMENT to DESIGN phase.")
            
            # Trigger design generation automatically
            from . import design_service
            try:
                design_service.start_design_generation(db, project_id)
            except Exception as de:
                print(f"Error auto-starting design generation: {de}")
                pass
                
    # Find last agent response
    agent_msg = ""
    agent_messages = [m for m in outputs.get("messages", []) if m["sender"] == "agent"]
    if agent_messages:
        agent_msg = agent_messages[-1]["text"]
        
    if agent_msg:
        project_service.log_activity(db, project_id, "AGENT_RESPONSE", agent_msg[:100])
        
    return {
        "agent_response": agent_msg,
        "memory": outputs.get("memory", current_state["memory"]),
        "document": document,
        "status": phase,
        "missing_info": outputs.get("missing_info", []),
        "validation_attempts": outputs.get("validation_attempts", 0)
    }

def resume_approval_step(
    db: Session,
    project_id: str,
    status: str,
    comments: Optional[str] = None,
    reviewer_name: Optional[str] = "Human Administrator",
    stage: Optional[str] = None
) -> Dict[str, Any]:
    config = get_graph_config(project_id)
    state = compiled_graph.get_state(config)
    
    if not state.next:
        print(f"[Requirement Service] Graph for {project_id} not in interrupted state. Auto-completing SRS & transitioning to DESIGN...")
        state_details = get_agent_state_details(project_id)
        doc = state_details.get("document")
        doc_dict = doc.dict() if (doc and hasattr(doc, "dict")) else doc
        
        project = project_service.get_project(db, project_id)
        if project:
            project.current_phase = "DESIGN"
            project.status = "IN_PROGRESS"
            db.commit()
            project_service.log_activity(db, project_id, "PHASE_TRANSITION", "Project transitioned automatically from REQUIREMENT to DESIGN phase.")
            
            if doc_dict:
                project_service.create_version_snapshot(db, project_id, doc_dict, comments or "SRS Approved")
                
            from . import design_service
            try:
                design_service.start_design_generation(db, project_id)
            except Exception as de:
                print(f"Error auto-starting design generation: {de}")
                pass
        return {"status": "completed", "current_phase": "DESIGN"}
        
    active_node = state.next[0]
    
    if not stage:
        if "extraction" in active_node:
            stage = "EXTRACTION"
        elif "gap" in active_node:
            stage = "GAP_DETECTION"
        elif "validation" in active_node:
            stage = "VALIDATION"
        elif "finalization" in active_node:
            stage = "FINALIZATION"
            
    # 1. Log review in database
    review_schema = project_service.schemas.HumanReviewSubmit(
        status=status,
        comments=comments,
        reviewer_name=reviewer_name,
        stage=stage
    )
    project_service.submit_human_review(db, project_id, "REQUIREMENT", review_schema)
    
    # 2. Update graph state with feedback
    feedback = {"status": status, "comments": comments or ""}
    compiled_graph.update_state(config, {"user_feedback": feedback}, as_node=active_node)
    
    # 3. Resume the graph
    try:
        outputs = compiled_graph.invoke(None, config)
    except Exception as e:
        print(f"[Requirement Service] Resume invoke interrupt/notice: {e}")
        outputs = {}
        
    latest_state = compiled_graph.get_state(config)
    state_values = latest_state.values if (latest_state and latest_state.values) else {}
    if not outputs:
        outputs = state_values
        
    phase = state_values.get("phase") or outputs.get("phase") or "draft"
    document = state_values.get("document") or outputs.get("document")
    memory = state_values.get("memory") or outputs.get("memory")
    messages = state_values.get("messages") or outputs.get("messages")
    missing_info = state_values.get("missing_info") or outputs.get("missing_info")
    validation_attempts = state_values.get("validation_attempts") or outputs.get("validation_attempts", 0)
    
    doc_dict = document.dict() if (document and hasattr(document, "dict")) else document
    mem_dict = memory.dict() if (memory and hasattr(memory, "dict")) else memory
    
    is_completed_or_finalized = (phase == "completed" or stage == "FINALIZATION") and status == "APPROVED"
    
    project_service.update_with_state(
        db=db,
        project_id=project_id,
        phase="REQUIREMENT" if not is_completed_or_finalized else "DESIGN",
        status="IN_PROGRESS" if not is_completed_or_finalized else "APPROVED",
        current_state=phase if not is_completed_or_finalized else "completed",
        document=doc_dict,
        messages=messages,
        memory=mem_dict,
        missing_info=missing_info,
        validation_attempts=validation_attempts,
        last_reviewer_comments=comments
    )
    
    # If completed or finalization approved, create version snapshot and transition to design phase
    if is_completed_or_finalized and document:
        project_service.create_or_update_requirement_srs(db, project_id, doc_dict, status="APPROVED", comments=comments or "SRS Approved")
        project_service.create_version_snapshot(db, project_id, doc_dict, comments)
        project = project_service.get_project(db, project_id)
        if project:
            project.current_phase = "DESIGN"
            project.status = "APPROVED"
            db.commit()
            project_service.log_activity(db, project_id, "PHASE_TRANSITION", "Requirements approved. Project transitioned to DESIGN phase.")
            
            from . import design_service
            try:
                print(f"[Requirement Service] Automatically triggering Design Agent for project {project_id}...")
                design_service.start_design_generation(db, project_id)
            except Exception as de:
                print(f"Error auto-starting design generation: {de}")
                pass
                
    # Find last agent response
    agent_msg = ""
    agent_messages = [m for m in outputs.get("messages", []) if m["sender"] == "agent"]
    if agent_messages:
        agent_msg = agent_messages[-1]["text"]
        
    return {
        "agent_response": agent_msg,
        "memory": outputs.get("memory", RequirementMemory()),
        "document": document,
        "status": phase,
        "missing_info": outputs.get("missing_info", []),
        "validation_attempts": outputs.get("validation_attempts", 0)
    }
