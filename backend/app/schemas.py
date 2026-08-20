from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from datetime import datetime
from enum import Enum

class RequirementStatus(str, Enum):
    proposed = "proposed"
    confirmed = "confirmed"
    rejected = "rejected"

class SourceType(str, Enum):
    user_input = "user_input"
    inference = "inference"
    clarification_answer = "clarification_answer"
    assumption = "assumption"

class RequirementSource(BaseModel):
    source_type: SourceType
    source_reference: Optional[str] = None
    source_text: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

class Requirement(BaseModel):
    requirement_id: str
    title: str
    statement: str
    requirement_type: Literal["functional", "non_functional", "business_rule"]
    actor: Optional[str] = None
    priority: Literal["must_have", "should_have", "could_have", "wont_have"]
    status: RequirementStatus
    source: RequirementSource
    linked_epic_ids: List[str] = []

class Epic(BaseModel):
    epic_id: str
    title: str
    description: Optional[str] = None
    status: RequirementStatus
    source: RequirementSource

class Feature(BaseModel):
    feature_id: str
    epic_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    status: RequirementStatus
    source: RequirementSource

class UserStory(BaseModel):
    story_id: str
    feature_id: Optional[str] = None
    title: str
    description: str  # e.g., "As a... I want... So that..."
    linked_requirement_ids: List[str] = []
    status: RequirementStatus
    source: RequirementSource

class AcceptanceCriterion(BaseModel):
    ac_id: str
    story_id: Optional[str] = None
    statement: str
    status: RequirementStatus
    source: RequirementSource

class TraceabilityItem(BaseModel):
    id: str = Field(..., description="Stable unique ID, e.g., REQ-001")
    title: str = Field(..., description="Short title of the requirement")
    description: str = Field(..., description="Full requirement text")
    category: str = Field(..., description="Category, e.g., Functional, Non-Functional, Security")

class WorkflowItem(BaseModel):
    workflow_id: str
    name: str
    actor: str
    trigger: str
    steps: List[str] = []

class QualityResult(BaseModel):
    valid: bool
    scores: Dict[str, int]  # completeness, consistency, clarity, testability, traceability, coverage
    overall_score: int
    issues: List[str] = []
    warnings: List[str] = []
    recommendations: List[str] = []

class ProjectDocument(BaseModel):
    project_id: str
    version: int
    project_summary: Optional[str] = None
    business_goals: List[str] = []
    problem_statement: Optional[str] = None
    stakeholders: List[str] = []
    actors: List[str] = []
    workflows: List[WorkflowItem] = []
    requirements: List[Requirement] = []
    assumptions: List[str] = []
    constraints: List[str] = []
    dependencies: List[str] = []
    risks: List[str] = []
    epics: List[Epic] = []
    features: List[Feature] = []
    user_stories: List[UserStory] = []
    acceptance_criteria: List[AcceptanceCriterion] = []
    traceability_matrix: List[TraceabilityItem] = []
    quality_result: Optional[QualityResult] = None

# --- Requirement Memory ---
class RequirementMemory(BaseModel):
    project_summary: Optional[str] = Field(None, description="High-level description of what the project is.")
    business_goals: Optional[str] = Field(None, description="Core business problems this software solves.")
    target_users: List[str] = Field(default_factory=list, description="Target user roles or personas.")
    functional_requirements: List[str] = Field(default_factory=list, description="Core operations the system must perform.")
    non_functional_requirements: List[str] = Field(default_factory=list, description="Performance, security, and scalability expectations.")
    constraints: List[str] = Field(default_factory=list, description="Technical or business restrictions.")
    assumptions: List[str] = Field(default_factory=list, description="Assumptions made about the system or environment.")
    acceptance_criteria: List[str] = Field(default_factory=list, description="Conditions the system must satisfy to be accepted.")
    open_questions: List[str] = Field(default_factory=list, description="Unresolved issues needing customer clarification.")

# --- SRS Traceability Metadata ---

# --- 30-Section SRS Output ---
class SRSOutput(BaseModel):
    project_name: str = Field(..., description="Name of the software project")
    
    # Sections 1-3: Document Metadata
    document_information: str = Field(..., description="Document metadata, classification, author, organization")
    revision_history: str = Field(..., description="Details of SRS changes, version numbers, dates, authors")
    approval_history: str = Field(..., description="Record of sign-offs, roles, and status of approvals")
    
    # Sections 4-9: Executive & Stakeholder Context
    executive_summary: str = Field(..., description="High-level overview of the product, goals, and business value")
    problem_statement: str = Field(..., description="Description of pain points, current state, and core problem to solve")
    business_objectives: str = Field(..., description="Measurable business goals, benefits, and KPI targets")
    stakeholders: List[str] = Field(default_factory=list, description="List of key stakeholder groups, roles, and project influence")
    user_personas: List[str] = Field(default_factory=list, description="Fictional character profiles representing primary users")
    actors: List[str] = Field(default_factory=list, description="User roles, systems, or entities interacting with the application")
    
    # Sections 10-11: Boundaries
    scope: str = Field(..., description="Boundaries, features, and capabilities included in the release")
    out_of_scope: str = Field(..., description="Items, integrations, or features explicitly excluded from the release")
    
    # Sections 12-18: Core Requirements
    business_requirements: List[str] = Field(default_factory=list, description="High-level business needs or processes that must be met")
    functional_requirements: List[str] = Field(default_factory=list, description="Detailed operations, inputs, processing, and outputs")
    non_functional_requirements: List[str] = Field(default_factory=list, description="Performance, security, usability, and availability standards")
    business_rules: List[str] = Field(default_factory=list, description="Policies, calculations, or logic governing the system operations")
    user_stories: List[str] = Field(default_factory=list, description="Agile formatting: 'As a... I want... So that...'")
    use_cases: List[str] = Field(default_factory=list, description="Step-by-step actor interactions with the system to achieve a goal")
    acceptance_criteria: List[str] = Field(default_factory=list, description="Gherkin or checklist constraints to mark features complete")
    
    # Sections 19-25: Interface & Operational
    ui_requirements: List[str] = Field(default_factory=list, description="Layout wireframes description, branding, layout guidelines")
    navigation_flow: List[str] = Field(default_factory=list, description="Pathways, screen sequences, transitions description")
    data_requirements: List[str] = Field(default_factory=list, description="Entities, data volumes, storage, and retrieval details")
    security_requirements: List[str] = Field(default_factory=list, description="Privacy protocols, threat mitigations, encryption standards")
    integration_requirements: List[str] = Field(default_factory=list, description="External APIs, services, and system connectivity interfaces")
    performance_requirements: List[str] = Field(default_factory=list, description="Response times, concurrency levels, throughput constraints")
    compliance_requirements: List[str] = Field(default_factory=list, description="Regulatory compliance criteria (HIPAA, GDPR, PCI-DSS)")
    
    # Sections 26-30: Constraints, Risks, Traceability
    constraints: List[str] = Field(default_factory=list, description="Technical boundaries, language locks, database restrictions")
    assumptions: List[str] = Field(default_factory=list, description="Foundational assumptions made during analysis")
    risks: List[str] = Field(default_factory=list, description="Identified project risks, schedules impact, and mitigations")
    dependencies: List[str] = Field(default_factory=list, description="External code libraries, platforms, or third-party dependencies")
    requirement_traceability_matrix: List[TraceabilityItem] = Field(default_factory=list, description="Requirement traceability mappings mapped to stable IDs")

    @classmethod
    def parse_safely(cls, raw_srs_dict: dict) -> "SRSOutput":
        data = dict(raw_srs_dict)
        for field_name, field_def in cls.model_fields.items():
            if field_name not in data:
                ann = field_def.annotation
                if ann == str:
                    data[field_name] = f"Placeholder legacy {field_name}"
                elif getattr(ann, "__origin__", None) is list:
                    data[field_name] = []
                elif getattr(ann, "__origin__", None) is dict:
                    data[field_name] = {}
                else:
                    data[field_name] = ""
        return cls(**data)

# --- API Models ---
class ProjectCreate(BaseModel):
    name: str
    description: Optional[str] = None

class ProjectResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    current_phase: str
    status: str
    created_at: datetime

    class Config:
        from_attributes = True

class ChatMessage(BaseModel):
    sender: str  # user or agent
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    agent_response: str
    memory: RequirementMemory
    srs: Optional[SRSOutput] = None
    status: str
    missing_info: List[str]
    validation_attempts: int

class HumanReviewSubmit(BaseModel):
    status: str  # APPROVED or REJECTED or REQUEST_CHANGES
    comments: Optional[str] = None
    reviewer_name: Optional[str] = "Human Administrator"
    stage: Optional[str] = None

class ActivityLogResponse(BaseModel):
    id: str
    project_id: str
    action: str
    details: Optional[str]
    timestamp: datetime

    class Config:
        from_attributes = True


# --- SDD Structures ---
class ADRItem(BaseModel):
    id: str = Field(..., description="ADR ID, e.g., ADR-001")
    title: str = Field(..., description="Title of the architectural decision")
    status: str = Field("Accepted", description="Status: Proposed, Accepted, Rejected, Superseded")
    context: str = Field(..., description="Context and problem statement requiring this decision")
    decision: str = Field(..., description="Chosen architectural decision and rationale")
    alternatives_considered: List[str] = Field(default_factory=list, description="Alternatives evaluated")
    trade_offs: List[str] = Field(default_factory=list, description="Consequences, trade-offs, and risks")

class DesignValidationResult(BaseModel):
    valid: bool = Field(True, description="Whether design passed architectural validation")
    overall_score: int = Field(85, description="Overall architecture quality index out of 100")
    missing_requirements: List[str] = Field(default_factory=list, description="Requirements not covered in design")
    unnecessary_components: List[str] = Field(default_factory=list, description="Components without linked requirement")
    missing_apis_or_tables: List[str] = Field(default_factory=list, description="Gaps in API endpoints or DB tables")
    security_gaps: List[str] = Field(default_factory=list, description="Identified security gaps")
    nfr_coverage_gaps: List[str] = Field(default_factory=list, description="Unaddressed quality or NFR demands")
    broken_traceability: List[str] = Field(default_factory=list, description="Traceability matrix broken links")

class ComponentItem(BaseModel):
    name: str = Field(..., description="Name of the software component, e.g., Auth Service")
    responsibility: str = Field(..., description="Key responsibility of this component")
    depends_on: List[str] = Field(default_factory=list, description="List of components this depends on")

class ColumnDef(BaseModel):
    name: str = Field(..., description="Name of the table column")
    type: str = Field(..., description="Data type of the column, e.g., VARCHAR, INT, TIMESTAMP")
    nullable: bool = Field(default=True, description="Whether the column can be null")
    description: str = Field(..., description="Purpose of this column")

class ForeignKeyDef(BaseModel):
    column: str = Field(..., description="Local column name")
    references_table: str = Field(..., description="Target references table name")
    references_column: str = Field(..., description="Target references column name")

class DatabaseTable(BaseModel):
    name: str = Field(..., description="Name of the database table")
    columns: List[ColumnDef] = Field(default_factory=list, description="List of table columns")
    primary_key: str = Field(..., description="Primary key column name")
    foreign_keys: List[ForeignKeyDef] = Field(default_factory=list, description="List of foreign keys")
    constraints: List[str] = Field(default_factory=list, description="Database constraints, e.g. UNIQUE, CHECK")

class ApiEndpoint(BaseModel):
    method: str = Field(..., description="HTTP Method (GET, POST, etc.)")
    path: str = Field(..., description="API Path endpoint URL")
    request_body: Optional[str] = Field(None, description="Schema description of request payload")
    response_body: str = Field(..., description="Schema description of response payload")
    description: str = Field(..., description="Function and usage of the API endpoint")

class TraceabilityMatrixItem(BaseModel):
    requirement_id: str = Field(..., description="SRS Requirement ID, e.g. REQ-F001")
    module: str = Field(..., description="Target system module/component implementing the requirement")
    api_endpoint: str = Field(..., description="API Endpoint path mapping to the requirement")
    db_table: str = Field(..., description="Database table storing relevant entities")
    ui_screen: str = Field(..., description="UI Interface/Screen exposing the behavior")
    adr_id: Optional[str] = Field("", description="Linked Architecture Decision Record ID")

# --- 40-Section SDD Output ---
class SDDOutput(BaseModel):
    # Sections 1-3: Document Metadata
    cover_page: str = Field(..., description="Document title page, copyright details, and metadata information")
    revision_history: str = Field(..., description="Design documentation changes log and version increments")
    approval_history: str = Field(..., description="Review log and sign-off statuses for the architecture phase")
    
    # Sections 4-6: Introduction & High-Level Summary
    introduction: str = Field(..., description="Scope, goals, terminology, and objectives of the design")
    design_goals: str = Field(..., description="Design priorities (scalability, latency constraints, SLAs)")
    system_overview: str = Field(..., description="High-level narrative summarizing the proposed system design")
    
    # Sections 7-9: Architecture & Breakdown
    high_level_architecture: str = Field(..., description="Architectural pattern details (Microservices, Monolith, Clean Arch)")
    low_level_architecture: str = Field(..., description="Detailed low-level breakdown of software submodules")
    module_breakdown: str = Field(..., description="Package layouts, layers, and service separation structures")
    
    # Sections 10-16: 10 Mermaid Diagrams (Mapped to Sections 10-16 + root diagram fields)
    system_context_diagram_mermaid: str = Field(..., description="Mermaid syntax for System Context Diagram")
    use_case_diagram_mermaid: str = Field(..., description="Mermaid syntax for Use Case Diagram")
    component_diagram_mermaid: str = Field(..., description="Mermaid syntax for Component Diagram")
    class_diagram_mermaid: str = Field(..., description="Mermaid syntax for Class Diagram")
    sequence_diagram_mermaid: str = Field(..., description="Mermaid syntax for Sequence Diagram")
    activity_diagram_mermaid: str = Field(..., description="Mermaid syntax for Activity Diagram")
    er_diagram_mermaid: str = Field(..., description="Mermaid syntax for Entity Relationship Diagram")
    deployment_diagram_mermaid: str = Field(..., description="Mermaid syntax for Deployment Diagram")
    flow_diagram_mermaid: str = Field(..., description="Mermaid syntax for Flow Diagram")
    db_relationship_diagram_mermaid: str = Field(..., description="Mermaid syntax for Database Relationship Diagram")
    
    # Sections 17-20: Database Design
    database_design_overview: str = Field(..., description="Detailed database strategies, design principles and engine choice")
    database_tables: List[DatabaseTable] = Field(default_factory=list, description="Comprehensive list of tables, columns, PK, and FK definitions")
    database_relationships: List[str] = Field(default_factory=list, description="Relational links and mapping rules")
    database_constraints: List[str] = Field(default_factory=list, description="Unique, index, and check integrity constraints")
    
    # Sections 21-23: API & Authentication
    api_design_overview: str = Field(..., description="API conventions, error templates, and header policies")
    api_endpoints: List[ApiEndpoint] = Field(default_factory=list, description="API routing definitions")
    authentication_flow: str = Field(..., description="Detail of sign-on protocols, token refreshes, and hash controls")
    authorization_flow: str = Field(..., description="Role-based access lists and granular permission configurations")
    
    # Sections 24-27: Security & Administration
    security_design_policies: str = Field(..., description="Encryption at rest/transit, vulnerability protections")
    logging_strategy: str = Field(..., description="Format rules, aggregation, trace tags, and rotation limits")
    exception_handling: str = Field(..., description="Catch-all rules, system errors code schemas, and fallback boundaries")
    configuration_management: str = Field(..., description="Vault setups, environmental variables, and keys security")
    
    # Sections 28-30: Technology & Standards
    technology_stack: List[str] = Field(default_factory=list, description="Programming languages, frameworks, DB choice, libraries")
    folder_structure: str = Field(..., description="Proposed directory layout structure inside the code repository")
    coding_standards: str = Field(..., description="Code conventions, review patterns, and quality standard bounds")
    
    # Sections 31-33: NFR Designs
    performance_design: str = Field(..., description="Cache configurations, load pools, and connection tuning specs")
    scalability_design: str = Field(..., description="Auto-scaling rules, partitioning models, and load balancers")
    availability_design: str = Field(..., description="Failover levels, Multi-AZ backups, and uptime specifications")
    
    # Sections 34-36: Monitoring & DR
    monitoring_strategy: str = Field(..., description="Metrics aggregations, dashboards, trace hooks, and paging rules")
    backup_strategy: str = Field(..., description="Recovery objective levels (RPO/RTO), rotation rules, and locations")
    disaster_recovery_runbook: str = Field(..., description="Failover procedures, replica syncs, and emergency checklists")
    
    # Sections 37-40: Risks, Traceability & ADRs
    architectural_risks: List[str] = Field(default_factory=list, description="List of technical risks, limitations, and mitigations")
    design_assumptions: List[str] = Field(default_factory=list, description="Key design assumptions made during system definition")
    future_enhancements: List[str] = Field(default_factory=list, description="Future features scope scale plans mapping")
    traceability_matrix: List[TraceabilityMatrixItem] = Field(default_factory=list, description="Requirement Traceability Matrix")
    adrs: List[ADRItem] = Field(default_factory=list, description="Architecture Decision Records explaining major design decisions")
    validation_result: Optional[DesignValidationResult] = Field(None, description="Automated design validation and audit results")

class DesignResponse(BaseModel):
    id: str
    project_id: str
    requirement_version_id: str
    approval_status: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class DesignVersionResponse(BaseModel):
    version_num: int
    sdd: SDDOutput
    reviewer_comments: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class ManifestFile(BaseModel):
    path: str = Field(..., description="File path within the workspace")
    module: str = Field(..., description="Target system module, e.g. backend, database, frontend, api, doc")
    owner_agent: str = Field("CodeGenerator", description="Name of specialized owner agent responsible for this file")
    purpose: str = Field(..., description="Explanation of what this file contains and why it is included")
    depends_on: str = Field("", description="Other file path that this file relies on")
    priority: int = Field(3, description="File generation priority from 1 (highest) to 5 (lowest)")
    language: str = Field(..., description="Target coding language, e.g. python, sql, tsx, css, html, markdown")
    security_sensitive: bool = Field(False, description="Flag indicating if the file touches auth/authz, keys or credentials")
    estimated_tokens: int = Field(500, description="Estimated number of tokens required to generate this file")


class DevelopmentVersionResponse(BaseModel):
    id: str
    project_id: str
    design_version_id: Optional[str] = None
    version_num: int
    raw_manifest: str  # Store manifest + file contents as JSON string
    artifact_zip_path: Optional[str] = None
    approval_status: str
    created_at: datetime

    class Config:
        from_attributes = True


class DevelopmentReviewSubmit(BaseModel):
    status: str = Field(..., description="APPROVED or REJECTED or REQUEST_CHANGES")
    comments: Optional[str] = Field(None, description="Review comments/feedback")
    reviewer_name: Optional[str] = Field("Lead Developer", description="Name of the reviewer")
    rejected_modules: Optional[List[str]] = Field(default_factory=list, description="List of modules rejected for targeted revision")
