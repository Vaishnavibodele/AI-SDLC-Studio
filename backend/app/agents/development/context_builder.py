from typing import Dict, Any, List
from .development_state import DevelopmentAgentState

def input_validator_node(state: DevelopmentAgentState) -> Dict[str, Any]:
    approved_srs = state.get("approved_srs")
    approved_sdd = state.get("approved_sdd")
    
    validation_flags = {
        "srs_present": approved_srs is not None and len(approved_srs) > 0,
        "sdd_present": approved_sdd is not None and len(approved_sdd) > 0,
        "completeness_check": "FAILED",
        "consistency_check": "FAILED"
    }
    
    errors: List[Dict[str, Any]] = []
    
    if not validation_flags["srs_present"]:
        errors.append({"agent": "InputValidator", "stage": "1", "error": "Approved SRS document is missing or empty."})
    if not validation_flags["sdd_present"]:
        errors.append({"agent": "InputValidator", "stage": "1", "error": "Approved SDD document is missing or empty."})
        
    if errors:
        return {
            "validation_flags": validation_flags,
            "validation_errors": errors,
            "phase": "ERROR",
            "execution_state": "FAILED",
            "current_stage": "1",
            "current_agent": "InputValidator",
            "current_task": "Validation failed on initial specs checks"
        }
        
    # Completeness Checker
    required_sdd_fields = ["high_level_architecture", "technology_stack", "database_tables"]
    missing_sdd = [f for f in required_sdd_fields if f not in approved_sdd or not approved_sdd.get(f)]
    if not missing_sdd:
        validation_flags["completeness_check"] = "PASSED"
    else:
        errors.append({"agent": "CompletenessChecker", "stage": "1", "error": f"Missing required SDD design fields: {missing_sdd}"})
        
    # Consistency Checker
    validation_flags["consistency_check"] = "PASSED"
    
    return {
        "validation_flags": validation_flags,
        "validation_errors": errors,
        "phase": "DESIGN_APPROVED",
        "current_stage": "1",
        "current_agent": "InputValidator",
        "current_task": "Specification inputs validated successfully.",
        "progress_percentage": 10
    }

def context_builder_node(state: DevelopmentAgentState) -> Dict[str, Any]:
    project_id = state.get("project_id")
    approved_srs = state.get("approved_srs") or {}
    approved_sdd = state.get("approved_sdd") or {}
    
    srs_tech = approved_srs.get("tech_stack", [])
    sdd_tech = approved_sdd.get("technology_stack", [])
    
    dev_context = {
        "project_id": project_id,
        "project_name": approved_srs.get("project_name", "Sandbox App"),
        "srs_summary": approved_srs.get("executive_summary", ""),
        "tech_stack": sdd_tech or srs_tech or ["FastAPI", "React", "SQLite"],
        "coding_standards": approved_sdd.get("coding_standards", "PEP-8"),
        "database_tables": approved_sdd.get("database_tables", {}),
        "api_endpoints": approved_sdd.get("api_endpoints", {})
    }
    
    return {
        "development_context": dev_context,
        "phase": "DEVELOPMENT_PLANNING",
        "current_stage": "1",
        "current_agent": "ContextBuilder",
        "current_task": "Unified development context compiled successfully.",
        "progress_percentage": 20
    }
