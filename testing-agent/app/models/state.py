from typing import TypedDict, List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field

from app.analysis.schemas import (
    DefectAnalysis,
    FailureAnalysis,
    FlakyTestAnalysis,
    ResultIntelligenceReport,
    RootCauseAnalysis,
)
from app.quality.schemas import QualityGateReport
from app.reports.schemas import TestReport

SourceType = Literal["srs", "sdd", "source_code", "ai_inference"]

class RequirementInfo(BaseModel):
    id: str = Field(..., description="Unique requirement ID (e.g. REQ-001)")
    description: str = Field(..., description="Details of the requirement")
    category: str = Field(..., description="Functional, Non-Functional, Security, etc.")
    source: SourceType = Field(..., description="The backing source of this requirement")

class RiskInfo(BaseModel):
    risk_id: str = Field(..., description="Unique risk ID (e.g. RSK-001)")
    requirement_id: Optional[str] = Field(None, description="Mapped requirement ID if applicable")
    description: str = Field(..., description="Details of the potential failure")
    severity: Literal["High", "Medium", "Low"] = Field(..., description="Severity of the risk")
    likelihood: Literal["High", "Medium", "Low"] = Field(..., description="Likelihood of occurrence")
    mitigation: str = Field(..., description="Proposed test-level mitigation")
    source: SourceType = Field(..., description="Backing source or ai_inference")

class ChangeImpactInfo(BaseModel):
    has_changes: bool = Field(..., description="Whether real changes are detected")
    changed_files: List[str] = Field(default_factory=list, description="List of files that were changed")
    changed_functions: List[str] = Field(default_factory=list, description="List of functions that were changed")
    impacted_requirements: List[str] = Field(default_factory=list, description="IDs of requirements affected by these changes")
    regression_risk: Literal["High", "Medium", "Low", "None"] = Field(..., description="Regression risk level")
    message: str = Field(..., description="Explanation of impact or 'change information unavailable'")
    source: SourceType = Field(..., description="Backing source of impact information")

class CoverageInfo(BaseModel):
    mapped_requirements: List[str] = Field(default_factory=list, description="IDs of covered requirements")
    uncovered_requirements: List[str] = Field(default_factory=list, description="IDs of uncovered requirements")
    coverage_percentage: float = Field(..., ge=0.0, le=100.0, description="Percentage of requirements mapped to code/endpoints")
    source: SourceType = Field(..., description="Source of coverage mapping")

class TestStrategyInfo(BaseModel):
    __test__ = False  # Prevent Pytest from trying to collect this as a test class
    unit_tests: List[str] = Field(..., description="Suggested unit test targets and mocks")
    integration_tests: List[str] = Field(..., description="Suggested integration test targets")
    api_tests: List[str] = Field(..., description="Suggested API/Contract verification steps")
    tools: List[str] = Field(..., description="Recommended tools e.g. pytest, httpx")
    environments: List[str] = Field(..., description="Target environment configs")
    source: SourceType = Field(..., description="Source of the strategy compilation")


TestType = Literal["unit", "integration", "api", "ui", "security", "regression"]
TestCategory = Literal["positive", "negative", "boundary", "edge", "happy_path"]
TestDataCategory = Literal["valid", "invalid", "boundary", "edge"]
TestPriority = Literal["High", "Medium", "Low"]


class TestCaseInfo(BaseModel):
    __test__ = False
    test_case_id: str = Field(..., description="Unique test case ID (e.g. TC-001)")
    title: str = Field(..., description="Short descriptive title")
    test_type: TestType = Field(..., description="Type of test")
    test_category: TestCategory = Field(..., description="Category of test")
    requirement_id: str = Field(..., description="Linked requirement ID")
    risk_id: Optional[str] = Field(None, description="Linked risk ID if applicable")
    design_component: str = Field(..., description="Design component under test")
    code_target: str = Field(..., description="Function, endpoint, or module target")
    description: str = Field(..., description="Detailed test description")
    preconditions: List[str] = Field(default_factory=list, description="Preconditions before execution")
    steps: List[str] = Field(default_factory=list, description="Ordered test steps")
    assertions: List[str] = Field(default_factory=list, description="Verification assertions")
    expected_result: str = Field(..., description="Expected outcome")
    mocks_required: List[str] = Field(default_factory=list, description="Mocks or stubs required")
    test_data_ids: List[str] = Field(default_factory=list, description="Linked test data IDs")
    priority: TestPriority = Field(..., description="Execution priority")
    source: SourceType = Field(..., description="Source of this test specification")

    # Optional structured UI actions for Phase 4 Selenium executor.
    # Each action should be a structured dict describing `action`, selector strategy,
    # selector/value, and optional condition/timeout where applicable.
    ui_actions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Optional structured UI actions for Selenium executor (open/click/input/wait/select)",
    )


class TestScenarioInfo(BaseModel):
    __test__ = False
    scenario_id: str = Field(..., description="Unique scenario ID (e.g. SCN-001)")
    title: str = Field(..., description="Scenario title")
    description: str = Field(..., description="Business scenario description")
    flow_steps: List[str] = Field(default_factory=list, description="Ordered business flow steps")
    requirement_ids: List[str] = Field(default_factory=list, description="Linked requirement IDs")
    related_test_case_ids: List[str] = Field(default_factory=list, description="Related test case IDs")
    source: SourceType = Field(..., description="Source of this scenario")


class TestDataField(BaseModel):
    __test__ = False
    name: str = Field(..., description="Field name")
    value: Any = Field(..., description="Field value")
    description: str = Field(..., description="Why this value is meaningful for the test")


class GeneratedTestDataInfo(BaseModel):
    data_id: str = Field(..., description="Unique test data ID (e.g. TD-001)")
    category: TestDataCategory = Field(..., description="Data category")
    description: str = Field(..., description="Purpose of this test data")
    linked_test_case_ids: List[str] = Field(default_factory=list, description="Test cases using this data")
    fields: List[TestDataField] = Field(default_factory=list, description="Structured field values")
    source: SourceType = Field(..., description="Source of this test data")


class TraceabilityEntry(BaseModel):
    requirement_id: str = Field(..., description="Requirement ID")
    risk_id: Optional[str] = Field(None, description="Risk ID if applicable")
    design_component: Optional[str] = Field(None, description="Design component")
    code_target: Optional[str] = Field(None, description="Code target")
    scenario_id: str = Field(..., description="Linked scenario ID")
    test_case_id: str = Field(..., description="Linked test case ID")
    test_data_ids: List[str] = Field(default_factory=list, description="Linked test data IDs")
    test_result_id: Optional[str] = Field(None, description="Phase 4: test result ID")
    defect_id: Optional[str] = Field(None, description="Phase 4: defect ID")


class TraceabilityMap(BaseModel):
    entries: List[TraceabilityEntry] = Field(default_factory=list, description="Traceability chain entries")
    uncovered_requirements: List[str] = Field(default_factory=list, description="Requirements without test cases")
    orphaned_test_cases: List[str] = Field(default_factory=list, description="Test cases without traceability")
    orphaned_test_data: List[str] = Field(default_factory=list, description="Test data not linked to any case")
    source: SourceType = Field(default="ai_inference", description="Source of traceability mapping")


class TestingState(TypedDict):
    __test__ = False  # Prevent Pytest from trying to collect this as a test class

    # Required inputs
    project_id: str
    srs: Dict[str, Any]
    sdd: Dict[str, Any]
    source_code: Dict[str, Any]

    # Optional inputs
    api_docs: Optional[Dict[str, Any]]
    database_schema: Optional[Dict[str, Any]]
    test_data: Optional[Dict[str, Any]]
    environment: Optional[Dict[str, Any]]

    # Workflow output and tracking fields
    validation_status: str       # "passed", "failed", or "pending"
    validation_errors: List[str]
    context: Dict[str, Any]      # Structured testing context loaded from the inputs
    workflow_status: str         # "pending", "running", "completed", or "failed"
    human_feedback: Optional[str]

    # Phase 2 output fields
    requirements: List[RequirementInfo]
    risks: List[RiskInfo]
    change_impact: Optional[ChangeImpactInfo]
    coverage: Optional[CoverageInfo]
    test_strategy: Optional[TestStrategyInfo]

    # Phase 3 output fields
    test_cases: List[TestCaseInfo]
    test_scenarios: List[TestScenarioInfo]
    generated_test_data: List[GeneratedTestDataInfo]
    traceability: Optional[TraceabilityMap]
    test_design_warnings: List[str]
    # Phase 4 execution fields
    execution_status: Optional[str]
    execution_results: List[Dict[str, Any]]
    execution_summary: Optional[Dict[str, Any]]

    # Phase 6 result intelligence fields
    result_intelligence: Optional[ResultIntelligenceReport]
    failure_analyses: List[FailureAnalysis]
    root_cause_analyses: List[RootCauseAnalysis]
    defect_analyses: List[DefectAnalysis]
    flaky_analyses: List[FlakyTestAnalysis]

    # Phase 7 quality gate / release readiness fields
    quality_gate_report: Optional[QualityGateReport]
    quality_score: Optional[float]
    release_readiness: Optional[str]

    # Phase 8 report generation fields
    report: Optional[TestReport]

    # Phase 8 human approval fields
    approval_status: Optional[str]  # "pending", "approved", "rejected"
    approved_by: Optional[str]      # Reviewer identifier
    approval_comment: Optional[str] # Rejection reason or approval notes
    approval_timestamp: Optional[str] # ISO 8601 timestamp
