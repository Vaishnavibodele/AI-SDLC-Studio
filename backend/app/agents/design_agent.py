import json
import os
from typing import Dict, Any, List, Optional
from pydantic import ValidationError

from langgraph.graph import StateGraph, END
from langgraph.types import interrupt

from .design_state import DesignAgentState
from ..schemas import SDDOutput, ProjectDocument
from ..services.llm_provider import get_llm
from ..prompts.design_prompts import SDD_GENERATOR_SYSTEM_PROMPT
from ..database import sqlite_checkpointer, SessionLocal
from ..services import project_service, json_repair

DESIGN_GAP_DETECTOR_SYSTEM_PROMPT = """
You are a Lead Software Architect and Quality Assurance Auditor. Your task is to analyze the generated System Design Document (SDD) against the source requirements and identify any gaps or architecture flaws.

Requirements:
{requirements_json}

System Design Document (SDD) to audit:
{sdd_json}

Audit for:
1. Missing coverage of functional features (e.g., does the API design or database schema fail to support any requirements?).
2. Non-functional requirements (NFRs) gaps (e.g., is there no caching strategy for latency-sensitive APIs?).
3. Inconsistent technology choices or unaddressed constraints.

Return the output as a JSON object containing a list of gaps:
{{
  "gaps": [
    {{
      "id": "DGAP-001",
      "description": "No security/TLS design is specified for authentication endpoints.",
      "blocking": true
    }}
  ]
}}

Do not write markdown block ticks or other chat formatting. Return ONLY the raw valid JSON.
"""

def save_sdd_version_to_db(project_id: str, sdd_data: Dict[str, Any], status: str = "PENDING", comments: str = ""):
    db = SessionLocal()
    try:
        proj = project_service.get_project(db, project_id)
        if not proj:
            return
            
        latest_req_ver = project_service.get_latest_srs_version(db, project_id)
        # Fallback to general requirement check if version missing
        req_ver_id = latest_req_ver.id if latest_req_ver else "fallback-req-ver-id"
            
        design_doc = db.query(project_service.models.DesignDocument).filter(
            project_service.models.DesignDocument.project_id == project_id
        ).first()
        
        if not design_doc:
            design_doc = project_service.models.DesignDocument(
                project_id=project_id,
                requirement_version_id=req_ver_id,
                approval_status=status
            )
            db.add(design_doc)
            db.commit()
            db.refresh(design_doc)
            version_num = 1
        else:
            design_doc.approval_status = status
            db.commit()
            last_version = db.query(project_service.models.DesignVersion).filter(
                project_service.models.DesignVersion.design_document_id == design_doc.id
            ).order_by(project_service.models.DesignVersion.version_num.desc()).first()
            version_num = (last_version.version_num + 1) if last_version else 1
            
        design_version = project_service.models.DesignVersion(
            design_document_id=design_doc.id,
            version_num=version_num,
            raw_sdd=json.dumps(sdd_data),
            reviewer_comments=comments
        )
        db.add(design_version)
        db.commit()
        
        project_service.log_activity(db, project_id, "DESIGN_VERSION_SAVED", f"SDD version {version_num} generated/saved with status: {status}")
    finally:
        db.close()

# ----------------- NODES & MULTI-STAGE REASONING -----------------

def input_validation(state: DesignAgentState) -> Dict[str, Any]:
    """Node: Reject design generation if the linked project requirements are missing."""
    print("[Design Node] input_validation starting...")
    doc = state.get("approved_document")
    if not doc or not doc.requirements:
        return {
            "phase": "error",
            "validation_errors": ["Linked project requirements (ProjectDocument) must exist and be populated."]
        }
    return {"phase": "analyzing"}


def requirement_analyzer(state: DesignAgentState) -> Dict[str, Any]:
    """Node: Analyze requirements and compile summary context."""
    print("[Design Node] requirement_analyzer starting...")
    if state.get("phase") == "error":
        return {}
        
    doc = state.get("approved_document")
    
    summary = {
        "project_name": f"Project {state.get('project_id')} Backlog",
        "summary": "Full project requirements and backlog.",
        "features": [f.title for f in doc.features],
        "functional_requirements": [r.statement for r in doc.requirements if r.requirement_type == "functional"],
        "non_functional_requirements": [r.statement for r in doc.requirements if r.requirement_type == "non_functional"],
        "constraints": [r.statement for r in doc.requirements if r.requirement_type == "business_rule"]
    }
    
    meta = dict(state.get("project_metadata", {}))
    meta["srs_summary"] = summary
    return {"project_metadata": meta, "phase": "architecture_planning"}


def architecture_planner(state: DesignAgentState) -> Dict[str, Any]:
    """Node: Lightweight planner that infers architecture style hints."""
    print("[Design Node] architecture_planner starting...")
    if state.get("phase") == "error":
        return {}
        
    meta = state.get("project_metadata", {})
    srs_summary = meta.get("srs_summary", {})
    constraints = srs_summary.get("constraints", [])
    non_functional = srs_summary.get("non_functional_requirements", [])
    
    hints = []
    is_microservice = False
    for c in constraints + non_functional:
        c_lower = c.lower()
        if "microservice" in c_lower or "distributed" in c_lower or "scale" in c_lower:
            is_microservice = True
            
    if is_microservice:
        hints.append("Style: Microservices Architecture. Separate components into domain subservices.")
    else:
        hints.append("Style: Modular Monolith Architecture. Clean layered separation (API, Service, Repository).")
        
    meta_copy = dict(meta)
    meta_copy["architecture_hints"] = "\n".join(hints)
    return {"project_metadata": meta_copy, "phase": "technology_selection"}


def technology_selector(state: DesignAgentState) -> Dict[str, Any]:
    """Node: Select tech choices based on constraints."""
    print("[Design Node] technology_selector starting...")
    if state.get("phase") == "error":
        return {}
        
    meta = state.get("project_metadata", {})
    srs_summary = meta.get("srs_summary", {})
    constraints = srs_summary.get("constraints", [])
    
    tech_choices = ["FastAPI backend framework", "React with TypeScript frontend", "PostgreSQL database"]
    for c in constraints:
        c_lower = c.lower()
        if "sqlite" in c_lower:
            tech_choices.append("SQLite backend repository engine")
        elif "mongodb" in c_lower or "nosql" in c_lower:
            tech_choices.append("MongoDB engine")
            
    meta_copy = dict(meta)
    meta_copy["technology_choices"] = tech_choices
    return {"project_metadata": meta_copy, "phase": "module_design"}


def module_designer(state: DesignAgentState) -> Dict[str, Any]:
    """Node: Define backend modular layout boundaries."""
    print("[Design Node] module_designer starting...")
    if state.get("phase") == "error":
        return {}
        
    meta = state.get("project_metadata", {})
    srs_summary = meta.get("srs_summary", {})
    features = srs_summary.get("features", [])
    
    modules = ["Authentication Layer", "Core Business Routing"]
    for f in features:
        f_lower = f.lower()
        if "cart" in f_lower or "checkout" in f_lower or "payment" in f_lower:
            modules.append("Transactional Module Service")
        if "search" in f_lower or "catalog" in f_lower:
            modules.append("Search Index Service")
            
    meta_copy = dict(meta)
    meta_copy["designed_modules"] = modules
    return {"project_metadata": meta_copy, "phase": "database_design"}


def database_designer(state: DesignAgentState) -> Dict[str, Any]:
    print("[Design Node] database_designer starting...")
    if state.get("phase") == "error":
        return {}
    meta = state.get("project_metadata", {})
    meta_copy = dict(meta)
    meta_copy["database_schema_guidelines"] = "Enforce foreign keys integrity. Table columns must possess explicit types and nullable constraints."
    return {"project_metadata": meta_copy, "phase": "api_design"}


def api_designer(state: DesignAgentState) -> Dict[str, Any]:
    print("[Design Node] api_designer starting...")
    if state.get("phase") == "error":
        return {}
    meta = state.get("project_metadata", {})
    meta_copy = dict(meta)
    meta_copy["api_guidelines"] = "REST conventions. JSON payloads. Gated user authentication hooks."
    return {"project_metadata": meta_copy, "phase": "security_design"}


def security_designer(state: DesignAgentState) -> Dict[str, Any]:
    print("[Design Node] security_designer starting...")
    if state.get("phase") == "error":
        return {}
    meta = state.get("project_metadata", {})
    meta_copy = dict(meta)
    meta_copy["security_guidelines"] = "Stateless JWT authorization tokens. Cryptographic password hashing. Encryption at rest and in transit."
    return {"project_metadata": meta_copy, "phase": "deployment_planning"}


def deployment_planner(state: DesignAgentState) -> Dict[str, Any]:
    print("[Design Node] deployment_planner starting...")
    if state.get("phase") == "error":
        return {}
    meta = state.get("project_metadata", {})
    meta_copy = dict(meta)
    meta_copy["deployment_guidelines"] = "Docker containerization. AWS ECS/EKS deployment. 24h RPO database snapshots backup loop."
    return {"project_metadata": meta_copy, "phase": "diagram_generation"}


def diagram_generator(state: DesignAgentState) -> Dict[str, Any]:
    print("[Design Node] diagram_generator starting...")
    if state.get("phase") == "error":
        return {}
    meta = state.get("project_metadata", {})
    meta_copy = dict(meta)
    meta_copy["diagram_guidelines"] = "Generate clean, valid Mermaid syntax. Do not leave placeholder labels."
    return {"project_metadata": meta_copy, "phase": "generating"}


def sdd_generator(state: DesignAgentState) -> Dict[str, Any]:
    """Node: Generates full 40-section SDD."""
    print("[Design Node] sdd_generator starting...")
    if state.get("phase") == "error":
        return {}
        
    meta = state.get("project_metadata", {})
    srs_summary = meta.get("srs_summary", {})
    srs_json = json.dumps(srs_summary, indent=2)
    hints = meta.get("architecture_hints", "No hints provided.")
    
    # Get reviewer comments if any
    feedback = state.get("user_feedback", {})
    reviewer_comments = ""
    if feedback and feedback.get("status") == "REJECTED":
        reviewer_comments = f"Reviewer Rejection Comments (address these specifically): {feedback.get('comments', '')}"
        
    llm = get_llm()
    
    try:
        response = llm.invoke([
            {
                "role": "system", 
                "content": SDD_GENERATOR_SYSTEM_PROMPT.format(
                    approved_srs_json=srs_json, 
                    architecture_hints=hints, 
                    reviewer_comments=reviewer_comments
                )
            },
            {
                "role": "user", 
                "content": "Generate the complete 40-section SDD JSON schema output."
            }
        ])
        
        sdd_data = json_repair.repair_json(response.content)
        return {
            "temp_sdd_data": sdd_data,
            "phase": "awaiting_design_generation_approval",
            "user_feedback": None
        }
    except Exception as e:
        print(f"Error compiling SDD in generator node: {e}")
        return {"phase": "error", "validation_errors": [f"Design generation failed: {str(e)}"]}


def awaiting_design_generation_approval(state: DesignAgentState) -> Dict[str, Any]:
    """Node: Pauses graph to review generated SDD."""
    print("[Design Node] awaiting_design_generation_approval interrupt...")
    feedback = interrupt({
        "stage": "DESIGN_GENERATION",
        "message": "Please review the generated System Design Document.",
        "sdd": state.get("temp_sdd_data")
    })
    return {"user_feedback": feedback}


def post_generation_handler(state: DesignAgentState) -> Dict[str, Any]:
    """Node: Processes design generation approval."""
    feedback = state.get("user_feedback") or {}
    if feedback.get("status") == "APPROVED":
        print("[Design Node] Design Generation Approved!")
        return {"phase": "design_gap_detection_running"}
    else:
        print("[Design Node] Design Generation Rejected.")
        return {"phase": "generating", "user_feedback": feedback}


def design_gap_detector_node(state: DesignAgentState) -> Dict[str, Any]:
    """Node: Runs LLM to check SDD for gaps against source requirements."""
    print("[Design Node] Running Design Gap Detection...")
    doc = state.get("approved_document")
    sdd_data = state.get("temp_sdd_data", {})
    llm = get_llm()
    
    reqs_json = json.dumps([r.dict() for r in doc.requirements], indent=2)
    sdd_json = json.dumps(sdd_data, indent=2)
    
    try:
        response = llm.invoke([
            {"role": "system", "content": DESIGN_GAP_DETECTOR_SYSTEM_PROMPT.format(requirements_json=reqs_json, sdd_json=sdd_json)},
            {"role": "user", "content": "Analyze the design against requirements for gaps."}
        ])
        
        repaired = json_repair.repair_json(response.content)
        gaps = repaired.get("gaps", [])
        
        return {
            "gaps": gaps,
            "phase": "awaiting_design_gap_approval",
            "user_feedback": None
        }
    except Exception as e:
        print(f"[Design Node] Gap detection error: {e}")
        return {"phase": "error", "validation_errors": [f"Design gap detection failed: {str(e)}"]}


def awaiting_design_gap_approval(state: DesignAgentState) -> Dict[str, Any]:
    """Node: Pauses graph to review design gaps."""
    print("[Design Node] awaiting_design_gap_approval interrupt...")
    feedback = interrupt({
        "stage": "DESIGN_GAP",
        "message": "Please review the detected design gaps.",
        "gaps": state.get("gaps", [])
    })
    return {"user_feedback": feedback}


def post_gap_handler(state: DesignAgentState) -> Dict[str, Any]:
    """Node: Processes gap approval."""
    feedback = state.get("user_feedback") or {}
    if feedback.get("status") == "APPROVED":
        print("[Design Node] Design Gaps Approved!")
        return {"phase": "design_validation_running"}
    else:
        print("[Design Node] Design Gaps Rejected.")
        return {"phase": "design_gap_detection_running", "user_feedback": feedback}


def design_validation_node(state: DesignAgentState) -> Dict[str, Any]:
    """Node: Performs deterministic checks on traceability matrix matching."""
    print("[Design Node] Running Design Validation...")
    doc = state.get("approved_document")
    sdd_data = state.get("temp_sdd_data", {})
    errors = []
    
    # Parse SDD into Pydantic model for validation
    validated_sdd = None
    try:
        validated_sdd = SDDOutput(**sdd_data)
    except Exception as e:
        errors.append(f"Pydantic Validation Error: {str(e)}")
        
    if validated_sdd:
        req_ids = {r.requirement_id for r in doc.requirements}
        api_paths = {api.path.lower().strip() for api in validated_sdd.api_endpoints}
        db_tables = {t.name.lower().strip() for t in validated_sdd.database_tables}
        
        for item in validated_sdd.traceability_matrix:
            # 1. Check requirement ID exists
            if item.requirement_id not in req_ids:
                errors.append(f"Traceability Error: requirement_id '{item.requirement_id}' not found in requirements.")
            # 2. Check api path exists
            if item.api_endpoint.lower().strip() not in api_paths:
                errors.append(f"Traceability Error: API endpoint '{item.api_endpoint}' not found in API design.")
            # 3. Check table exists
            if item.db_table.lower().strip() not in db_tables:
                errors.append(f"Traceability Error: Database table '{item.db_table}' not found in database design.")
                
    return {
        "validation_errors": errors,
        "phase": "awaiting_design_validation_approval",
        "user_feedback": None
    }


def awaiting_design_validation_approval(state: DesignAgentState) -> Dict[str, Any]:
    """Node: Pauses graph to review validation errors."""
    print("[Design Node] awaiting_design_validation_approval interrupt...")
    feedback = interrupt({
        "stage": "DESIGN_VALIDATION",
        "message": "Please review design validation results.",
        "errors": state.get("validation_errors", [])
    })
    return {"user_feedback": feedback}


def post_validation_handler(state: DesignAgentState) -> Dict[str, Any]:
    """Node: Processes validation approval."""
    feedback = state.get("user_feedback") or {}
    if feedback.get("status") == "APPROVED":
        print("[Design Node] Design Validation Approved!")
        return {"phase": "design_finalizing"}
    else:
        print("[Design Node] Design Validation Rejected.")
        return {"phase": "design_validation_running", "user_feedback": feedback}


def design_finalization_node(state: DesignAgentState) -> Dict[str, Any]:
    """Node: Finalizes design doc and saves to database."""
    print("[Design Node] Finalizing System Design Document...")
    sdd_data = state.get("temp_sdd_data", {})
    validated_sdd = SDDOutput(**sdd_data)
    
    # Save design version
    project_id = state.get("project_id")
    save_sdd_version_to_db(project_id, sdd_data, status="APPROVED", comments="Finalized System Design Document")
    
    return {
        "sdd": validated_sdd,
        "phase": "awaiting_design_finalization_approval",
        "user_feedback": None
    }


def awaiting_design_finalization_approval(state: DesignAgentState) -> Dict[str, Any]:
    """Node: Pauses graph for final export approval."""
    print("[Design Node] awaiting_design_finalization_approval interrupt...")
    feedback = interrupt({
        "stage": "DESIGN_FINALIZATION",
        "message": "Please confirm final export approval for System Design Document.",
        "sdd": state.get("sdd").dict() if state.get("sdd") else None
    })
    return {"user_feedback": feedback}


def post_finalization_handler(state: DesignAgentState) -> Dict[str, Any]:
    """Node: Final route after confirmation."""
    feedback = state.get("user_feedback") or {}
    if feedback.get("status") == "APPROVED":
        print("[Design Node] Finalization Approved! Design Complete.")
        return {"phase": "completed"}
    else:
        print("[Design Node] Finalization Rejected.")
        return {"phase": "design_finalizing", "user_feedback": feedback}

# ----------------- EDGES & ROUTING -----------------

def route_after_input(state: DesignAgentState) -> str:
    if state.get("phase") == "error":
        return END
    return "requirement_analyzer"

def route_after_generation(state: DesignAgentState) -> str:
    if state.get("phase") == "error":
        return END
    return "awaiting_design_generation_approval"

def route_after_generation_approval(state: DesignAgentState) -> str:
    if state.get("phase") == "generating":
        return "sdd_generator"
    return "design_gap_detector_node"

def route_after_gap(state: DesignAgentState) -> str:
    if state.get("phase") == "error":
        return END
    return "awaiting_design_gap_approval"

def route_after_gap_approval(state: DesignAgentState) -> str:
    if state.get("phase") == "design_gap_detection_running":
        return "design_gap_detector_node"
    return "design_validation_node"

def route_after_validation(state: DesignAgentState) -> str:
    return "awaiting_design_validation_approval"

def route_after_validation_approval(state: DesignAgentState) -> str:
    if state.get("phase") == "design_validation_running":
        return "design_validation_node"
    return "design_finalization_node"

def route_after_finalization(state: DesignAgentState) -> str:
    return "awaiting_design_finalization_approval"

def route_after_finalization_approval(state: DesignAgentState) -> str:
    if state.get("phase") == "design_finalizing":
        return "design_finalization_node"
    return END

# ----------------- GRAPH COMPILATION -----------------

workflow = StateGraph(DesignAgentState)

workflow.add_node("input_validation", input_validation)
workflow.add_node("requirement_analyzer", requirement_analyzer)
workflow.add_node("architecture_planner", architecture_planner)
workflow.add_node("technology_selector", technology_selector)
workflow.add_node("module_designer", module_designer)
workflow.add_node("database_designer", database_designer)
workflow.add_node("api_designer", api_designer)
workflow.add_node("security_designer", security_designer)
workflow.add_node("deployment_planner", deployment_planner)
workflow.add_node("diagram_generator", diagram_generator)
workflow.add_node("sdd_generator", sdd_generator)
workflow.add_node("awaiting_design_generation_approval", awaiting_design_generation_approval)
workflow.add_node("post_generation_handler", post_generation_handler)
workflow.add_node("design_gap_detector_node", design_gap_detector_node)
workflow.add_node("awaiting_design_gap_approval", awaiting_design_gap_approval)
workflow.add_node("post_gap_handler", post_gap_handler)
workflow.add_node("design_validation_node", design_validation_node)
workflow.add_node("awaiting_design_validation_approval", awaiting_design_validation_approval)
workflow.add_node("post_validation_handler", post_validation_handler)
workflow.add_node("design_finalization_node", design_finalization_node)
workflow.add_node("awaiting_design_finalization_approval", awaiting_design_finalization_approval)
workflow.add_node("post_finalization_handler", post_finalization_handler)

workflow.set_entry_point("input_validation")

workflow.add_conditional_edges("input_validation", route_after_input)
workflow.add_edge("requirement_analyzer", "architecture_planner")
workflow.add_edge("architecture_planner", "technology_selector")
workflow.add_edge("technology_selector", "module_designer")
workflow.add_edge("module_designer", "database_designer")
workflow.add_edge("database_designer", "api_designer")
workflow.add_edge("api_designer", "security_designer")
workflow.add_edge("security_designer", "deployment_planner")
workflow.add_edge("deployment_planner", "diagram_generator")
workflow.add_edge("diagram_generator", "sdd_generator")

workflow.add_conditional_edges("sdd_generator", route_after_generation)
workflow.add_edge("awaiting_design_generation_approval", "post_generation_handler")
workflow.add_conditional_edges("post_generation_handler", route_after_generation_approval)

workflow.add_conditional_edges("design_gap_detector_node", route_after_gap)
workflow.add_edge("awaiting_design_gap_approval", "post_gap_handler")
workflow.add_conditional_edges("post_gap_handler", route_after_gap_approval)

workflow.add_conditional_edges("design_validation_node", route_after_validation)
workflow.add_edge("awaiting_design_validation_approval", "post_validation_handler")
workflow.add_conditional_edges("post_validation_handler", route_after_validation_approval)

workflow.add_conditional_edges("design_finalization_node", route_after_finalization)
workflow.add_edge("awaiting_design_finalization_approval", "post_finalization_handler")
workflow.add_conditional_edges("post_finalization_handler", route_after_finalization_approval)

compiled_design_graph = workflow.compile(checkpointer=sqlite_checkpointer)
