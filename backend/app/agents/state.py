from typing import List, Dict, Any, Optional, TypedDict
from ..schemas import RequirementMemory, ProjectDocument

class AgentState(TypedDict):
    project_id: str
    messages: List[Dict[str, Any]]  # List of message dicts: {"sender": "user"|"agent", "text": "..."}
    memory: RequirementMemory
    document: Optional[ProjectDocument]
    gaps: Optional[List[Dict[str, Any]]]  # List of gaps
    phase: str  # draft, processing, awaiting_extraction_approval, awaiting_gap_approval, etc.
    missing_info: List[str]
    validation_attempts: int
    user_feedback: Optional[Dict[str, Any]]  # {"status": "APPROVED"|"REJECTED", "comments": "..."}


