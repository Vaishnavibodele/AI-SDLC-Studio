import os
import pytest
from app.services.llm import GeminiService, RequirementsWrapper, RisksWrapper
from app.models.state import TestingState, ChangeImpactInfo, CoverageInfo, TestStrategyInfo
from app.agents.requirement_analyzer import analyze_requirements
from app.agents.risk_analyzer import analyze_risks
from app.agents.impact_analyzer import analyze_impact
from app.agents.coverage_analyzer import analyze_coverage
from app.agents.strategy_planner import plan_strategy

def test_gemini_service_missing_api_key_raises_error():
    """
    Verify that GeminiService raises a ValueError if LLM_MODE=gemini
    but GEMINI_API_KEY is missing.
    """
    # Temporarily force gemini mode and clear api key
    os.environ["LLM_MODE"] = "gemini"
    original_key = os.environ.get("GEMINI_API_KEY")
    if "GEMINI_API_KEY" in os.environ:
        del os.environ["GEMINI_API_KEY"]

    try:
        with pytest.raises(ValueError) as excinfo:
            GeminiService()
        assert "GEMINI_API_KEY environment variable is missing" in str(excinfo.value)
    finally:
        # Restore environment
        os.environ["LLM_MODE"] = "mock"
        if original_key:
            os.environ["GEMINI_API_KEY"] = original_key


def test_requirement_analyzer_node():
    """
    Verify that the Requirement Analyzer node generates requirements using the mock client.
    """
    state: TestingState = {
        "project_id": "test-project",
        "srs": {"title": "SRS"},
        "sdd": {"architecture": "Microservices"},
        "source_code": {},
        "api_docs": None,
        "database_schema": None,
        "test_data": None,
        "environment": None,
        "validation_status": "passed",
        "validation_errors": [],
        "context": {
            "requirements_context": {"title": "SRS"},
            "design_context": {"architecture": "Microservices"}
        },
        "workflow_status": "running",
        "human_feedback": None,
        "requirements": [],
        "risks": [],
        "change_impact": None,
        "coverage": None,
        "test_strategy": None,
        "test_cases": [],
        "test_scenarios": [],
        "generated_test_data": [],
        "traceability": None,
        "test_design_warnings": [],
    }
    
    result = analyze_requirements(state)
    assert "requirements" in result
    assert len(result["requirements"]) > 0
    assert result["requirements"][0].id == "REQ-001"
    assert result["requirements"][0].source in ["srs", "sdd", "ai_inference"]


def test_risk_analyzer_node():
    """
    Verify that the Risk Analyzer node generates risks using mock configuration.
    """
    # Create valid mock requirements first
    requirements_mock = GeminiService()._generate_mock_output(RequirementsWrapper).requirements

    state: TestingState = {
        "project_id": "test-project",
        "srs": {},
        "sdd": {},
        "source_code": {},
        "api_docs": None,
        "database_schema": None,
        "test_data": None,
        "environment": None,
        "validation_status": "passed",
        "validation_errors": [],
        "context": {},
        "workflow_status": "running",
        "human_feedback": None,
        "requirements": requirements_mock,
        "risks": [],
        "change_impact": None,
        "coverage": None,
        "test_strategy": None,
        "test_cases": [],
        "test_scenarios": [],
        "generated_test_data": [],
        "traceability": None,
        "test_design_warnings": [],
    }
    
    result = analyze_risks(state)
    assert "risks" in result
    assert len(result["risks"]) > 0
    assert result["risks"][0].risk_id == "RSK-001"
    assert result["risks"][0].severity in ["High", "Medium", "Low"]


def test_change_impact_analyzer_deterministic_short_circuit():
    """
    Verify that the Change Impact Analyzer returns an explicit "change information unavailable"
    state when source_code changes metadata is absent, without calling Gemini.
    """
    state: TestingState = {
        "project_id": "test-project",
        "srs": {},
        "sdd": {},
        "source_code": {"repository": "git@github.com"},  # no 'changes' key
        "api_docs": None,
        "database_schema": None,
        "test_data": None,
        "environment": None,
        "validation_status": "passed",
        "validation_errors": [],
        "context": {},
        "workflow_status": "running",
        "human_feedback": None,
        "requirements": [],
        "risks": [],
        "change_impact": None,
        "coverage": None,
        "test_strategy": None,
        "test_cases": [],
        "test_scenarios": [],
        "generated_test_data": [],
        "traceability": None,
        "test_design_warnings": [],
    }
    
    result = analyze_impact(state)
    assert "change_impact" in result
    impact: ChangeImpactInfo = result["change_impact"]
    assert impact.has_changes is False
    assert impact.message == "change information unavailable"
    assert len(impact.changed_files) == 0


def test_change_impact_analyzer_with_changes():
    """
    Verify that the Change Impact Analyzer node parses changes correctly when change info is present.
    """
    state: TestingState = {
        "project_id": "test-project",
        "srs": {},
        "sdd": {},
        "source_code": {
            "repository": "git@github.com",
            "changes": {
                "changed_files": ["app/services/telemetry.py"],
                "changed_functions": ["parse_sensor_reading"]
            }
        },
        "api_docs": None,
        "database_schema": None,
        "test_data": None,
        "environment": None,
        "validation_status": "passed",
        "validation_errors": [],
        "context": {},
        "workflow_status": "running",
        "human_feedback": None,
        "requirements": [],
        "risks": [],
        "change_impact": None,
        "coverage": None,
        "test_strategy": None,
        "test_cases": [],
        "test_scenarios": [],
        "generated_test_data": [],
        "traceability": None,
        "test_design_warnings": [],
    }
    
    result = analyze_impact(state)
    assert "change_impact" in result
    impact: ChangeImpactInfo = result["change_impact"]
    assert impact.has_changes is True
    assert "app/services/telemetry.py" in impact.changed_files
    assert impact.regression_risk in ["High", "Medium", "Low", "None"]


def test_coverage_analyzer_requirement_coverage():
    """
    Verify that the Coverage Analyzer correctly yields requirement-based coverage gaps.
    """
    state: TestingState = {
        "project_id": "test-project",
        "srs": {},
        "sdd": {},
        "source_code": {},
        "api_docs": None,
        "database_schema": None,
        "test_data": None,
        "environment": None,
        "validation_status": "passed",
        "validation_errors": [],
        "context": {},
        "workflow_status": "running",
        "human_feedback": None,
        "requirements": [],
        "risks": [],
        "change_impact": None,
        "coverage": None,
        "test_strategy": None,
        "test_cases": [],
        "test_scenarios": [],
        "generated_test_data": [],
        "traceability": None,
        "test_design_warnings": [],
    }
    
    result = analyze_coverage(state)
    assert "coverage" in result
    cov: CoverageInfo = result["coverage"]
    assert cov.coverage_percentage >= 0.0
    assert cov.coverage_percentage <= 100.0
    assert cov.source == "ai_inference"


def test_test_strategy_planner_node():
    """
    Verify that the Test Strategy Planner node synthesizes findings into a test strategy.
    """
    state: TestingState = {
        "project_id": "test-project",
        "srs": {},
        "sdd": {},
        "source_code": {},
        "api_docs": None,
        "database_schema": None,
        "test_data": None,
        "environment": None,
        "validation_status": "passed",
        "validation_errors": [],
        "context": {},
        "workflow_status": "running",
        "human_feedback": None,
        "requirements": [],
        "risks": [],
        "change_impact": None,
        "coverage": None,
        "test_strategy": None,
        "test_cases": [],
        "test_scenarios": [],
        "generated_test_data": [],
        "traceability": None,
        "test_design_warnings": [],
    }
    
    result = plan_strategy(state)
    assert "test_strategy" in result
    strat: TestStrategyInfo = result["test_strategy"]
    assert len(strat.unit_tests) > 0
    assert "pytest" in strat.tools
