"""Phase 6 — Result Intelligence / Failure Analysis schemas.

These models are *additive* and describe the analysis layer that runs AFTER
Phase 5 execution. They never replace or redefine the Phase 4/5 execution
result contract (see `app/execution/controller.py` and
`app/models/schemas.TestExecutionResult`).
"""
from __future__ import annotations

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class Confidence(str, Enum):
    """Confidence attached to any inferred (non-deterministic) statement."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class FailureType(str, Enum):
    """Deterministically derived failure categories."""
    ASSERTION_FAILURE = "assertion_failure"
    HTTP_STATUS_MISMATCH = "http_status_mismatch"
    ENDPOINT_UNAVAILABLE = "endpoint_unavailable"
    TIMEOUT = "timeout"
    SELECTOR_NOT_FOUND = "selector_not_found"
    BROWSER_NETWORK_ERROR = "browser_network_error"
    INVALID_PYTEST_TARGET = "invalid_pytest_target"
    AUTHENTICATION_FAILURE = "authentication_failure"
    AUTHORIZATION_FAILURE = "authorization_failure"
    INTEGRATION_TARGET_UNAVAILABLE = "integration_target_unavailable"
    UNKNOWN = "unknown"


class RootCauseCategory(str, Enum):
    """High-level area the probable root cause belongs to."""
    ENVIRONMENT = "environment"
    APPLICATION_CODE = "application_code"
    TEST_CODE = "test_code"
    TEST_DATA = "test_data"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"


class DefectClassification(str, Enum):
    """A failing test is NOT automatically a product defect."""
    PRODUCT_DEFECT = "product_defect"
    PRODUCT_DEFECT_CANDIDATE = "product_defect_candidate"
    TEST_DEFECT = "test_defect"
    TEST_CONFIGURATION_ISSUE = "test_configuration_issue"
    ENVIRONMENT_ISSUE = "environment_issue"
    TEST_DATA_ISSUE = "test_data_issue"
    UNKNOWN = "unknown"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Priority(str, Enum):
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"


INSUFFICIENT_EVIDENCE_SUMMARY = "Insufficient execution evidence"
UNKNOWN_ROOT_CAUSE = "Unknown / insufficient evidence"
INSUFFICIENT_HISTORY_REASON = "insufficient_history"


class FailureAnalysis(BaseModel):
    """Structured analysis of a single FAILED / ERROR execution result."""
    __test__ = False

    test_case_id: str = Field(..., description="Test case identifier from the execution result")
    failure_type: FailureType = Field(FailureType.UNKNOWN, description="Deterministically classified failure type")
    failure_summary: str = Field(..., description="Short human readable failure summary")
    observed_behavior: Optional[str] = Field(None, description="What actually happened, taken from execution evidence")
    expected_behavior: Optional[str] = Field(None, description="What was expected, when such evidence exists")
    evidence: List[str] = Field(default_factory=list, description="Raw execution evidence used for this analysis")
    confidence: Confidence = Field(Confidence.LOW, description="Confidence of the classification")
    # Context preserved from the execution result (never re-derived)
    status: Optional[str] = Field(None, description="Actual deterministic execution status (PASS/FAIL/ERROR/SKIPPED)")
    module: Optional[str] = Field(None, description="Execution module that produced the result")
    run_id: Optional[str] = Field(None, description="Execution run identifier if available")
    llm_explanation: Optional[str] = Field(None, description="Optional LLM explanation; never overrides status")


class RootCauseAnalysis(BaseModel):
    """Probable root cause inferred from real execution evidence only."""
    __test__ = False

    test_case_id: str
    probable_root_cause: str = Field(..., description="Hypothesis of the underlying cause")
    affected_component: Optional[str] = Field(None, description="Component or target most likely involved")
    category: RootCauseCategory = Field(RootCauseCategory.UNKNOWN, description="Root cause category")
    evidence: List[str] = Field(default_factory=list)
    confidence: Confidence = Field(Confidence.LOW)
    failure_type: FailureType = Field(FailureType.UNKNOWN, description="Failure type this root cause was derived from")
    run_id: Optional[str] = None


class DefectAnalysis(BaseModel):
    """Defect classification — a failing test may not be a product defect."""
    __test__ = False

    test_case_id: str
    defect_detected: bool = Field(False, description="True only for product defect / product defect candidate")
    classification: DefectClassification = Field(DefectClassification.UNKNOWN)
    severity: Severity = Field(Severity.LOW)
    priority: Priority = Field(Priority.P4)
    title: str = Field(..., description="Concise defect title")
    description: str = Field(..., description="Evidence-based description")
    affected_component: Optional[str] = None
    evidence: List[str] = Field(default_factory=list)
    confidence: Confidence = Field(Confidence.LOW)
    recommendations: List[str] = Field(default_factory=list, description="Structured, actionable recommendations")
    failure_type: FailureType = Field(FailureType.UNKNOWN)
    run_id: Optional[str] = None


class FlakyTestAnalysis(BaseModel):
    """Flakiness assessment. Never inferred from a single deterministic result."""
    __test__ = False

    test_case_id: str
    flaky: bool = Field(False, description="True only when inconsistent outcomes are actually observed")
    confidence: Confidence = Field(Confidence.LOW)
    reason: str = Field(..., description="Why the test is (or is not) considered flaky")
    evidence: List[str] = Field(default_factory=list)
    observed_statuses: List[str] = Field(default_factory=list, description="Statuses actually observed (attempts / history)")
    run_id: Optional[str] = None


class ResultIntelligenceReport(BaseModel):
    """Aggregated Phase 6 report derived from a Phase 5 execution report."""
    __test__ = False

    run_id: Optional[str] = Field(None, description="Run identifier from the execution report if present")
    analyzed_count: int = Field(0, description="Number of execution results inspected")
    failures_analyzed: int = Field(0, description="Number of FAILED/ERROR results analyzed")
    defects_detected: int = Field(0, description="Number of product defects / candidates detected")
    flaky_tests_detected: int = Field(0, description="Number of tests flagged as potentially flaky")
    failures: List[FailureAnalysis] = Field(default_factory=list)
    root_causes: List[RootCauseAnalysis] = Field(default_factory=list)
    defects: List[DefectAnalysis] = Field(default_factory=list)
    flaky_tests: List[FlakyTestAnalysis] = Field(default_factory=list)
