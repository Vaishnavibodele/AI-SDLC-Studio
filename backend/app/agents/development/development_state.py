from typing import Dict, Any, List, Optional, TypedDict

class DevelopmentAgentState(TypedDict):
    project_id: str
    approved_srs: dict
    approved_sdd: dict
    tech_stack: dict
    existing_code_ref: Optional[str]
    project_metadata: dict

    development_context: dict          # Stage 1 output
    validation_flags: dict             # completeness/consistency check results

    plan: dict                         # Stage 3: modules, dependency graph
    tasks: List[dict]
    task_dependencies: dict

    backend_output: Optional[dict]
    frontend_output: Optional[dict]
    database_output: Optional[dict]
    api_integration_output: Optional[dict]
    documentation_output: Optional[dict]

    merged_files: dict
    manifest: List[dict]
    static_analysis_report: dict
    security_quality_report: dict
    build_report: dict
    unit_test_report: dict

    self_review_report: dict           # Stage 6, advisory

    artifact_paths: dict               # Stage 7
    quality_score: float
    security_score: float

    validation_errors: List[dict]
    validation_attempts: int           # capped at 3

    current_stage: str                 # 1..9
    current_agent: str
    current_task: str
    execution_state: str               # RUNNING | COMPLETED | FAILED
    progress_percentage: int
    current_version: int
    phase: str
    
    human_feedback: Optional[dict]
    rejected_modules: List[str]

    # Section 5 Hardening keys
    context: dict
    agent_outputs: dict
    generated_files: dict
    api_contract: dict
    validation_results: dict
    self_review_results: dict
    execution_logs: List[dict]
    current_node: str
    revision_attempts: int
    build_status: str
    errors: List[dict]

    # Section 3 required keys
    planned_tasks: List[dict]
    api_contract_results: dict
    agent_statuses: dict
    human_review: Optional[dict]
    project_status: str
    agent_failed_attempts: int
    artifact_attempts: int
