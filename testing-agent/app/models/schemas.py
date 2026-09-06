from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from enum import Enum
from app.analysis.schemas import ResultIntelligenceReport
from app.quality.schemas import QualityGateReport
from app.reports.schemas import TestReport
from app.models.state import (
    RequirementInfo,
    RiskInfo,
    ChangeImpactInfo,
    CoverageInfo,
    TestStrategyInfo,
    TestCaseInfo,
    TestScenarioInfo,
    GeneratedTestDataInfo,
    TraceabilityMap,
)

class TestingStartRequest(BaseModel):
    """
    Request model for starting the Testing Agent flow.
    """
    project_id: str = Field(..., description="Unique identifier for the project")
    srs: Dict[str, Any] = Field(..., description="Software Requirement Specification document/metadata")
    sdd: Dict[str, Any] = Field(..., description="Software Design Document/metadata")
    source_code: Dict[str, Any] = Field(..., description="Developed source code info/metadata")
    
    # Optional inputs
    api_docs: Optional[Dict[str, Any]] = Field(default=None, description="API documentation metadata")
    database_schema: Optional[Dict[str, Any]] = Field(default=None, description="Database schema metadata")
    test_data: Optional[Dict[str, Any]] = Field(default=None, description="Test data/fixtures metadata")
    environment: Optional[Dict[str, Any]] = Field(default=None, description="Target environment metadata")
    test_case_ids: Optional[List[str]] = Field(default=None, description="Optional list of specific test case IDs to run")
    retry: Optional[bool] = Field(default=False, description="Flag indicating retry of failed test cases")

    model_config = {
        "json_schema_extra": {
            "example": {
                "project_id": "smart-building-001",
                "srs": {"title": "Smart Building SRS", "version": "1.0"},
                "sdd": {"architecture": "Microservices", "components": []},
                "source_code": {"repository": "github.com/org/repo", "language": "Python"},
                "api_docs": {"base_url": "https://api.building.com"},
                "database_schema": {"tables": ["rooms", "sensors"]},
                "test_data": {"users": []},
                "environment": {"name": "staging"}
            }
        }
    }

class IntelligenceSummary(BaseModel):
    """
    Summary of the AI analysis generated during the workflow execution.
    """
    requirements: List[RequirementInfo] = Field(default_factory=list, description="Extracted testable requirement specifications")
    risks: List[RiskInfo] = Field(default_factory=list, description="Software risks mapped to requirements")
    change_impact: Optional[ChangeImpactInfo] = Field(default=None, description="Change impact analysis regression report")
    coverage: Optional[CoverageInfo] = Field(default=None, description="Requirements mapping coverage details")
    test_strategy: Optional[TestStrategyInfo] = Field(default=None, description="Recommended test execution blueprint")

class TestDesignSummary(BaseModel):
    """
    Summary of Phase 3 test design and data intelligence artifacts.
    """
    test_cases: List[TestCaseInfo] = Field(default_factory=list, description="Structured test case specifications")
    test_scenarios: List[TestScenarioInfo] = Field(default_factory=list, description="Business test scenarios")
    generated_test_data: List[GeneratedTestDataInfo] = Field(default_factory=list, description="Generated test data linked to test cases")
    traceability: Optional[TraceabilityMap] = Field(default=None, description="Requirement-to-test traceability map")
    warnings: List[str] = Field(default_factory=list, description="Test design validation warnings")


class TestExecutionResult(BaseModel):
    test_case_id: str
    name: Optional[str] = None
    status: str
    details: Optional[str] = None
    module: Optional[str] = None
    duration: Optional[float] = None
    attempts: Optional[int] = None
    logs: List[Dict[str, Any]] = Field(default_factory=list)
    artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    screenshot: Optional[str] = None
    # New Phase 5 structured extensions (backwards-compatible additions)
    attempts_detail: Optional[List[Dict[str, Any]]] = Field(default=None, description="Structured attempt entries with timestamps, durations, and details")
    artifacts_meta: Optional[List[Dict[str, Any]]] = Field(default=None, description="Structured artifact metadata for each artifact")
    screenshot_meta: Optional[Dict[str, Any]] = Field(default=None, description="Structured screenshot metadata (path, captured_at, etc.)")


class TestExecutionSummary(BaseModel):
    total: int
    passed: int
    failed: int
    errors: int
    skipped: int


class TestExecutionResponse(BaseModel):
    project_id: str
    execution_status: Optional[str] = Field(default=None, description="Execution lifecycle status: completed, no_tests, skipped, error")
    execution_summary: TestExecutionSummary
    results: List[TestExecutionResult] = Field(default_factory=list)
    # Run-level Phase 5 metadata (optional, backwards-compatible)
    run_id: Optional[str] = Field(default=None, description="Unique identifier for this execution run")
    started_at: Optional[str] = Field(default=None, description="Run start timestamp (ISO8601)")
    completed_at: Optional[str] = Field(default=None, description="Run completion timestamp (ISO8601)")
    duration: Optional[float] = Field(default=None, description="Total run duration in seconds")
    platform: Optional[str] = Field(default=None, description="Host platform info")
    python_version: Optional[str] = Field(default=None, description="Python interpreter version used")
    max_retries: Optional[int] = Field(default=None, description="Default max retries applied by the controller")
    max_workers: Optional[int] = Field(default=None, description="Max worker threads used for this run")
    # Phase 6 result intelligence (optional, backwards-compatible)
    analysis: Optional[ResultIntelligenceReport] = Field(default=None, description="Aggregated Phase 6 result intelligence for this run")
    # Phase 7 quality gate / release readiness (optional, backwards-compatible)
    quality_gate: Optional[QualityGateReport] = Field(default=None, description="Phase 7 quality gate and release readiness decision for this run")
    # Phase 8 report generation (optional, backwards-compatible)
    report: Optional[TestReport] = Field(default=None, description="Phase 8 comprehensive test report")


class TestingStartResponse(BaseModel):
    """
    Response model returning the results of the Testing Agent workflow execution.
    """
    project_id: str
    validation_status: str
    validation_errors: List[str]
    workflow_status: str
    intelligence: Optional[IntelligenceSummary] = Field(default=None, description="Encapsulated quality and testing intelligence report")
    test_design: Optional[TestDesignSummary] = Field(default=None, description="Phase 3 test design and data intelligence")
    # Phase 8 report generation (optional, backwards-compatible)
    report: Optional[TestReport] = Field(default=None, description="Phase 8 comprehensive test report")


class ApprovalStatus(str, Enum):
    """Human approval status for test reports."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ApprovalRequest(BaseModel):
    """
    Request model for approving or rejecting a test report.
    """
    project_id: str = Field(..., description="Project identifier")
    report_id: str = Field(..., description="Report ID to approve/reject")
    approved_by: str = Field(..., description="Reviewer identifier")
    comment: Optional[str] = Field(default=None, description="Optional comment/reason")

    model_config = {
        "json_schema_extra": {
            "example": {
                "project_id": "smart-building-001",
                "report_id": "RPT-ABC123",
                "approved_by": "john.doe",
                "comment": "All tests passed, ready for release"
            }
        }
    }


class ApprovalResponse(BaseModel):
    """
    Response model for approval operations.
    """
    project_id: str = Field(..., description="Project identifier")
    report_id: str = Field(..., description="Report ID")
    approval_status: ApprovalStatus = Field(..., description="Current approval status")
    approved_by: Optional[str] = Field(default=None, description="Reviewer identifier")
    approval_timestamp: Optional[str] = Field(default=None, description="ISO 8601 timestamp of approval/rejection")
    comment: Optional[str] = Field(default=None, description="Reviewer comment")
    release_allowed: bool = Field(..., description="Whether deployment can proceed")
    quality_gate_status: Optional[str] = Field(default=None, description="Quality gate status for context")
    release_readiness: Optional[str] = Field(default=None, description="Release readiness for context")
