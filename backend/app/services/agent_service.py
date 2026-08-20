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
            
        outputs = compiled_graph.invoke(inputs, config)
        
    # Process outputs and persist state
    phase = outputs.get("phase", "draft")
    document = outputs.get("document")
    
    doc_dict = document.dict() if (document and hasattr(document, "dict")) else document
    mem_dict = outputs.get("memory").dict() if (outputs.get("memory") and hasattr(outputs.get("memory"), "dict")) else outputs.get("memory")
    
    # Save state to database
    project_service.update_with_state(
        db=db,
        project_id=project_id,
        phase="REQUIREMENT",
        status="IN_PROGRESS" if phase != "completed" else "APPROVED",
        current_state=phase,
        document=doc_dict,
        messages=outputs.get("messages"),
        memory=mem_dict,
        missing_info=outputs.get("missing_info"),
        validation_attempts=outputs.get("validation_attempts")
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
        raise ValueError("Graph is not in an interrupted state.")
        
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
    outputs = compiled_graph.invoke(None, config)
    
    # 4. Sync new state to DB
    phase = outputs.get("phase", "draft")
    document = outputs.get("document")
    
    doc_dict = document.dict() if (document and hasattr(document, "dict")) else document
    mem_dict = outputs.get("memory").dict() if (outputs.get("memory") and hasattr(outputs.get("memory"), "dict")) else outputs.get("memory")
    
    project_service.update_with_state(
        db=db,
        project_id=project_id,
        phase="REQUIREMENT",
        status="IN_PROGRESS" if phase != "completed" else "APPROVED",
        current_state=phase,
        document=doc_dict,
        messages=outputs.get("messages"),
        memory=mem_dict,
        missing_info=outputs.get("missing_info"),
        validation_attempts=outputs.get("validation_attempts"),
        last_reviewer_comments=comments
    )
    
    # If completed, create version snapshot and transition to design phase
    if phase == "completed" and document:
        project_service.create_version_snapshot(db, project_id, doc_dict, comments)
        project = project_service.get_project(db, project_id)
        if project:
            project.current_phase = "DESIGN"
            project.status = "IN_PROGRESS"
            db.commit()
            project_service.log_activity(db, project_id, "PHASE_TRANSITION", "Project transitioned automatically from REQUIREMENT to DESIGN phase.")
            
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
        
    return {
        "agent_response": agent_msg,
        "memory": outputs.get("memory", RequirementMemory()),
        "document": document,
        "status": phase,
        "missing_info": outputs.get("missing_info", []),
        "validation_attempts": outputs.get("validation_attempts", 0)
    }
