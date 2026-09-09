from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExportFormat(str, Enum):
    JSON = "json"
    HTML = "html"
    CSV = "csv"
    PDF = "pdf"
    DOCX = "docx"
    MD = "md"


class PhaseStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"
    SKIPPED = "skipped"


class ProjectSummarySection(BaseModel):
    project_id: str = Field("", description="Unique identifier for the project")
    project_name: str = Field("", description="Project name / title")
    timestamp: str = Field("", description="Timestamp of report compilation")
    sdlc_phase: str = Field("TESTING", description="Current SDLC phase")
    sdlc_status: str = Field("READY_FOR_TESTING", description="Current SDLC stage status")


class RequirementSummarySection(BaseModel):
    title: str = Field("", description="SRS document title")
    version: str = Field("1.0.0", description="SRS version")
    features_count: int = Field(0, description="Total functional requirements count")
    features: List[str] = Field(default_factory=list, description="Summarized functional requirements")
    non_functional_requirements_count: int = Field(0, description="Total NFR count")
    non_functional_requirements: List[str] = Field(default_factory=list, description="Summarized NFRs")
    user_stories_count: int = Field(0, description="Total user stories count")
    business_goals: str = Field("", description="Business objectives summary")


class DesignSummarySection(BaseModel):
    architecture: str = Field("", description="High-level architecture design summary")
    components_count: int = Field(0, description="Total modules / components count")
    components: List[str] = Field(default_factory=list, description="Architecture components list")
    interfaces_count: int = Field(0, description="API endpoints / interfaces count")
    interfaces: List[str] = Field(default_factory=list, description="API interface contracts")
    database_tables_count: int = Field(0, description="Database tables count")
    database_tables: List[str] = Field(default_factory=list, description="Database tables mapped")
    security_policies: List[str] = Field(default_factory=list, description="Security policies and guardrails")


class DevelopmentSummarySection(BaseModel):
    repository: str = Field("", description="Source code repository identifier")
    language: str = Field("Python", description="Primary development language")
    build_version: str = Field("Build v1.0", description="Development artifact build version")
    files_count: int = Field(0, description="Total generated source files count")
    files: List[str] = Field(default_factory=list, description="Source code file paths")
    changed_files: List[str] = Field(default_factory=list, description="Files modified in this iteration")
    artifact_zip: Optional[str] = Field(None, description="Downloadable zip bundle path")


class GovernanceReportSection(BaseModel):
    approval_status: str = Field("pending", description="Human QA sign-off status: pending, approved, rejected")
    approved_by: Optional[str] = Field(None, description="Name of the QA reviewer")
    comment: Optional[str] = Field(None, description="Sign-off review observations or rejection reason")
    approval_timestamp: Optional[str] = Field(None, description="ISO timestamp of human sign-off")
    release_allowed: bool = Field(False, description="Whether release is certified and approved")
    quality_gate_status: Optional[str] = Field(None, description="Associated quality gate status")
    release_readiness: Optional[str] = Field(None, description="Release readiness tag")


class PhaseSummary(BaseModel):
    phase_number: int = Field(..., description="Phase number (1-8)")
    phase_name: str = Field(..., description="Human-readable phase name")
    status: PhaseStatus = Field(..., description="Overall phase status")
    summary: str = Field(..., description="Brief summary of phase results")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Key metrics for this phase")


class TestExecutionReportSection(BaseModel):
    __test__ = False
    total_tests: int = Field(0, description="Total number of tests executed")
    passed: int = Field(0, description="Number of passed tests")
    failed: int = Field(0, description="Number of failed tests")
    errors: int = Field(0, description="Number of error tests")
    skipped: int = Field(0, description="Number of skipped tests")
    pass_rate: float = Field(0.0, description="Pass rate percentage")
    duration: Optional[float] = Field(None, description="Total execution duration in seconds")
    failed_test_ids: List[str] = Field(default_factory=list, description="IDs of failed tests")
    error_test_ids: List[str] = Field(default_factory=list, description="IDs of error tests")


class AnalysisReportSection(BaseModel):
    total_failures: int = Field(0, description="Total failures analyzed")
    failure_types: Dict[str, int] = Field(default_factory=dict, description="Count by failure type")
    root_causes: List[Dict[str, Any]] = Field(default_factory=list, description="Root cause summaries")
    product_defects: int = Field(0, description="Number of product defects identified")
    test_defects: int = Field(0, description="Number of test defects identified")
    flaky_tests: int = Field(0, description="Number of flaky tests detected")


class QualityGateReportSection(BaseModel):
    overall_status: str = Field("NOT_EVALUATED", description="Overall gate status")
    release_readiness: str = Field("NOT_READY", description="Release readiness")
    quality_score: float = Field(0.0, description="Quality score (0-100)")
    gate_results: List[Dict[str, Any]] = Field(default_factory=list, description="Individual gate results")
    blocking_gates: List[str] = Field(default_factory=list, description="Names of failed gates")


class TraceabilityReportSection(BaseModel):
    total_entries: int = Field(0, description="Total traceability entries")
    coverage_percentage: float = Field(0.0, description="Requirements coverage percentage")
    uncovered_requirements: List[str] = Field(default_factory=list, description="Uncovered requirement IDs")
    orphaned_test_cases: List[str] = Field(default_factory=list, description="Test cases without traceability")
    orphaned_test_data: List[str] = Field(default_factory=list, description="Test data not linked to cases")


class TestReport(BaseModel):
    __test__ = False
    report_id: str = Field(..., description="Unique report ID")
    project_id: str = Field(..., description="Project identifier")
    project_name: Optional[str] = Field(None, description="Project human-readable title")
    generated_at: str = Field(..., description="ISO 8601 timestamp")
    
    # 1. SDLC & Upstream Summaries
    project_summary: ProjectSummarySection = Field(default_factory=ProjectSummarySection)
    requirement_summary: RequirementSummarySection = Field(default_factory=RequirementSummarySection)
    design_summary: DesignSummarySection = Field(default_factory=DesignSummarySection)
    development_summary: DevelopmentSummarySection = Field(default_factory=DevelopmentSummarySection)
    
    # 2. Testing Phases 1-8
    phases: List[PhaseSummary] = Field(default_factory=list, description="Phase-by-phase summaries")
    execution: TestExecutionReportSection = Field(default_factory=TestExecutionReportSection)
    analysis: AnalysisReportSection = Field(default_factory=AnalysisReportSection)
    quality_gate: QualityGateReportSection = Field(default_factory=QualityGateReportSection)
    traceability: TraceabilityReportSection = Field(default_factory=TraceabilityReportSection)
    
    # 3. Governance, Readiness & Recommendations
    governance: GovernanceReportSection = Field(default_factory=GovernanceReportSection)
    executive_summary: str = Field("", description="High-level executive summary")
    recommendations: List[str] = Field(default_factory=list, description="Actionable recommendations")
    release_readiness: str = Field("NOT_READY", description="Release readiness classification")
    release_allowed: bool = Field(False, description="Whether release is certified by quality gate & human approval")
    
    # 4. Raw Data
    raw_data: Dict[str, Any] = Field(default_factory=dict, description="Full raw data from all phases")
