from typing import Dict, Any, List, Optional, TypedDict

class DevelopmentAgentState(TypedDict):
    project_id: str
    approved_srs: Dict[str, Any]
    approved_sdd: Dict[str, Any]
    design_version_id: str
    manifest: List[Dict[str, Any]]  # List of ManifestFile: path, module, owner_agent, purpose, depends_on, priority, language, security_sensitive, estimated_tokens
    generated_files: Dict[str, str] # Map path -> content
    validation_attempts: int
    validation_errors: List[str]
    phase: str # Matches project status codes: DESIGN_APPROVED, DEVELOPMENT_PLANNING, GENERATING_CODE, VALIDATING, GENERATING_ARTIFACTS, WAITING_FOR_REVIEW, DEVELOPMENT_APPROVED, READY_FOR_TESTING, ERROR
    user_feedback: Optional[Dict[str, Any]]
    
    # Enriched enterprise state parameters
    context: Dict[str, Any]         # Unified loading of SRS, SDD, metadata, tech stack, rules, constraints
    execution_state: str            # RUNNING, COMPLETED, FAILED, IDLE
    current_node: str               # Name of the active node executing in the graph
    current_task: str               # Details of what the active node is working on
    completed_tasks: List[str]      # List of completed nodes or files
    failed_tasks: List[str]         # List of failed compilation checks/files
    progress_percentage: int        # Quantitative tracking: e.g. 0 to 100
    current_version: int            # Dynamic version counter
    artifact_path: str              # Path to primary zip file
    build_status: str               # PENDING, SUCCESS, FAILED
