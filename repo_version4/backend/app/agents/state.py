from typing import List, Dict, Any, Optional, TypedDict
from ..schemas import RequirementMemory, ProjectDocument

class AgentState(TypedDict):
    project_id: str
    messages: List[Dict[str, Any]]  # List of message dicts: {"sender": "user"|"agent", "text": "..."}
    memory: RequirementMemory
    document: Optional[ProjectDocument]
    gaps: Optional[List[Dict[str, Any]]]  # List of gaps / clarification questions
    clarification_questions: List[Dict[str, Any]]  # List of ClarificationQuestion dicts
    clarification_answers: List[Dict[str, Any]]  # List of ClarificationAnswer dicts
    conflicts: List[str]  # Detected contradictions or conflicts
    phase: str  # draft, processing, awaiting_extraction_approval, awaiting_gap_approval, waiting_for_clarification, etc.
    missing_info: List[str]
    validation_attempts: int
    user_feedback: Optional[Dict[str, Any]]  # {"status": "APPROVED"|"REJECTED", "comments": "..."}



