import logging
from typing import Dict, Any, List
from app.models.state import TestingState

logger = logging.getLogger(__name__)

def validate_input(state: TestingState) -> Dict[str, Any]:
    """
    Validates that the required fields (project_id, srs, sdd, source_code)
    are present and not empty in the state.
    
    Returns a dictionary of updates to apply to the state.
    """
    logger.info("Executing Input Validation Agent Node")
    errors: List[str] = []

    # Validate project_id
    project_id = state.get("project_id")
    if project_id is None:
        errors.append("project_id is required")
    elif not isinstance(project_id, str):
        errors.append("project_id must be a string")
    elif not project_id.strip():
        errors.append("project_id cannot be empty")

    # Validate srs
    srs = state.get("srs")
    if srs is None:
        errors.append("srs is required")
    elif not isinstance(srs, dict):
        errors.append("srs must be a dictionary")
    elif not srs:
        errors.append("srs cannot be empty")

    # Validate sdd
    sdd = state.get("sdd")
    if sdd is None:
        errors.append("sdd is required")
    elif not isinstance(sdd, dict):
        errors.append("sdd must be a dictionary")
    elif not sdd:
        errors.append("sdd cannot be empty")

    # Validate source_code
    source_code = state.get("source_code")
    if source_code is None:
        errors.append("source_code is required")
    elif not isinstance(source_code, dict):
        errors.append("source_code must be a dictionary")
    elif not source_code:
        errors.append("source_code cannot be empty")

    validation_status = "failed" if errors else "passed"
    workflow_status = "running" if validation_status == "passed" else "failed"

    logger.info(f"Input validation status: {validation_status}. Errors: {errors}")

    return {
        "validation_status": validation_status,
        "validation_errors": errors,
        "workflow_status": workflow_status
    }
