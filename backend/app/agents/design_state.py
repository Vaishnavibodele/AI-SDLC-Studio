from typing import List, Dict, Any, Optional, TypedDict
from ..schemas import ProjectDocument, SDDOutput

class DesignAgentState(TypedDict):
    project_id: str
    approved_document: ProjectDocument
    project_metadata: Dict[str, Any]
    sdd: Optional[SDDOutput]
    gaps: Optional[List[Dict[str, Any]]]  # Design-level gaps
    validation_attempts: int
    validation_errors: List[str]
    user_feedback: Optional[Dict[str, Any]]  # {"status": "APPROVED"|"REJECTED", "comments": "..."}
    phase: str  # generating, awaiting_design_generation_approval, awaiting_design_gap_approval, etc.
    temp_sdd_data: Optional[Dict[str, Any]]
