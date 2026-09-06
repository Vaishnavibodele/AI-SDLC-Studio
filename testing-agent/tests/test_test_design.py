import os
import pytest

from app.models.state import (
    RequirementInfo,
    RiskInfo,
    ChangeImpactInfo,
    TestCaseInfo,
    TestScenarioInfo,
    GeneratedTestDataInfo,
    TestDataField,
    TestingState,
)
from app.services.llm import (
    GeminiService,
    RequirementsWrapper,
    RisksWrapper,
    TestCasesWrapper,
    TestScenariosWrapper,
    TestDataWrapper,
    NegativeBoundaryTestCasesWrapper,
)
from app.models.state import TestStrategyInfo
from app.services.test_design_validator import (
    validate_and_filter_test_cases,
    merge_test_cases,
    validate_test_data,
    validate_scenarios,
    build_traceability_map,
    get_max_test_cases,
)
from app.agents.test_case_generator import generate_test_cases
from app.agents.scenario_builder import build_scenarios
from app.agents.negative_boundary_generator import generate_negative_boundary_cases
from app.agents.test_data_generator import generate_test_data
from app.agents.traceability_mapper import map_traceability


def _base_state(**overrides) -> TestingState:
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
            "requirements_context": {"title": "SRS", "features": ["F1"]},
            "design_context": {"architecture": "Microservices", "components": ["Telemetry Collector"]},
            "code_context": {"files": ["telemetry.py"]},
            "api_context": {"endpoints": ["POST /telemetry"]},
            "database_context": {"tables": ["telemetry"]},
            "test_data_context": {},
            "environment_context": {"env_name": "staging"},
        },
        "workflow_status": "running",
        "human_feedback": None,
        "requirements": GeminiService()._generate_mock_output(RequirementsWrapper).requirements,
        "risks": GeminiService()._generate_mock_output(RisksWrapper).risks,
        "change_impact": None,
        "coverage": None,
        "test_strategy": GeminiService()._generate_mock_output(TestStrategyInfo),
        "test_cases": [],
        "test_scenarios": [],
        "generated_test_data": [],
        "traceability": None,
        "test_design_warnings": [],
    }
    state.update(overrides)
    return state


def _sample_requirements():
    return [
        RequirementInfo(id="REQ-001", description="R1", category="Functional", source="srs"),
        RequirementInfo(id="REQ-002", description="R2", category="Functional", source="srs"),
    ]


def _sample_risks():
    return [
        RiskInfo(
            risk_id="RSK-001",
            requirement_id="REQ-001",
            description="Risk 1",
            severity="High",
            likelihood="Medium",
            mitigation="Mitigate",
            source="ai_inference",
        )
    ]


def _sample_case(case_id="TC-001", req_id="REQ-001", test_type="api", category="positive"):
    return TestCaseInfo(
        test_case_id=case_id,
        title=f"Test {case_id}",
        test_type=test_type,
        test_category=category,
        requirement_id=req_id,
        risk_id=None,
        design_component="Component",
        code_target="target",
        description="Desc",
        preconditions=["Pre"],
        steps=["Step"],
        assertions=["Assert"],
        expected_result="Expected",
        priority="High",
        source="ai_inference",
    )


# --- GeminiService mock tests ---

def test_gemini_mock_test_cases_wrapper():
    wrapper = GeminiService()._generate_mock_output(TestCasesWrapper)
    assert len(wrapper.test_cases) >= 2
    assert wrapper.test_cases[0].test_case_id == "TC-001"
    assert wrapper.test_cases[0].test_category in ["positive", "happy_path"]


def test_gemini_mock_negative_boundary_wrapper():
    wrapper = GeminiService()._generate_mock_output(NegativeBoundaryTestCasesWrapper)
    categories = {c.test_category for c in wrapper.test_cases}
    assert "negative" in categories or "boundary" in categories


def test_gemini_mock_scenarios_wrapper():
    wrapper = GeminiService()._generate_mock_output(TestScenariosWrapper)
    assert len(wrapper.test_scenarios) >= 1
    assert wrapper.test_scenarios[0].scenario_id.startswith("SCN-")


def test_gemini_mock_test_data_wrapper():
    wrapper = GeminiService()._generate_mock_output(TestDataWrapper)
    assert len(wrapper.generated_test_data) >= 1
    assert wrapper.generated_test_data[0].data_id.startswith("TD-")


def test_gemini_mock_includes_ui_test_case():
    wrapper = GeminiService()._generate_mock_output(TestCasesWrapper)
    ui_cases = [c for c in wrapper.test_cases if c.test_type == "ui"]
    assert len(ui_cases) >= 1
    ui_case = ui_cases[0]
    assert hasattr(ui_case, "ui_actions")
    assert isinstance(ui_case.ui_actions, list)
    assert len(ui_case.ui_actions) >= 1
    # First action should include an action key (e.g., open)
    assert "action" in ui_case.ui_actions[0]


# --- Validator unit tests ---

def test_validate_rejects_invalid_requirement_id():
    cases = [_sample_case(req_id="REQ-999")]
    filtered, warnings = validate_and_filter_test_cases(cases, _sample_requirements(), [], None)
    assert len(filtered) == 0
    assert any("invalid requirement_id" in w for w in warnings)


def test_validate_clears_invalid_risk_id():
    case = _sample_case()
    case = case.model_copy(update={"risk_id": "RSK-999"})
    filtered, warnings = validate_and_filter_test_cases(
        [case], _sample_requirements(), _sample_risks(), None
    )
    assert len(filtered) == 1
    assert filtered[0].risk_id is None
    assert any("invalid risk_id" in w for w in warnings)


def test_validate_removes_duplicate_test_case_id():
    cases = [_sample_case("TC-001"), _sample_case("TC-001")]
    filtered, warnings = validate_and_filter_test_cases(cases, _sample_requirements(), [], None)
    assert len(filtered) == 1
    assert any("duplicate test_case_id" in w for w in warnings)


def test_validate_removes_semantic_duplicate():
    c1 = _sample_case("TC-001")
    c2 = _sample_case("TC-002")
    c2 = c2.model_copy(update={"title": c1.title})
    filtered, warnings = validate_and_filter_test_cases(
        [c1, c2], _sample_requirements(), [], None
    )
    assert len(filtered) == 1
    assert any("semantic duplicate" in w for w in warnings)


def test_validate_strips_regression_without_change_metadata():
    case = _sample_case(test_type="regression")
    filtered, warnings = validate_and_filter_test_cases(
        [case], _sample_requirements(), [], None
    )
    assert len(filtered) == 0
    assert any("regression" in w for w in warnings)


def test_validate_allows_regression_with_change_metadata():
    case = _sample_case(test_type="regression")
    impact = ChangeImpactInfo(
        has_changes=True,
        changed_files=["telemetry.py"],
        changed_functions=["parse"],
        impacted_requirements=["REQ-001"],
        regression_risk="Medium",
        message="Changes detected",
        source="source_code",
    )
    filtered, warnings = validate_and_filter_test_cases(
        [case], _sample_requirements(), [], impact
    )
    assert len(filtered) == 1
    assert filtered[0].test_type == "regression"


def test_validate_enforces_max_test_cases(monkeypatch):
    monkeypatch.setenv("MAX_TEST_CASES", "2")
    cases = [
        _sample_case(f"TC-{i:03d}", req_id="REQ-001" if i % 2 else "REQ-002")
        for i in range(5)
    ]
    filtered, warnings = validate_and_filter_test_cases(
        cases, _sample_requirements(), [], None
    )
    assert len(filtered) == 2
    assert any("MAX_TEST_CASES" in w for w in warnings)


def test_validate_test_data_invalid_linked_case():
    cases = [_sample_case("TC-001")]
    data = GeneratedTestDataInfo(
        data_id="TD-001",
        category="valid",
        description="Data",
        linked_test_case_ids=["TC-999"],
        fields=[TestDataField(name="x", value=1, description="d")],
        source="ai_inference",
    )
    filtered, warnings = validate_test_data([data], cases)
    assert len(filtered) == 0
    assert any("invalid linked_test_case_ids" in w for w in warnings)


def test_validate_test_data_linkage_success():
    cases = [_sample_case("TC-001")]
    data = GeneratedTestDataInfo(
        data_id="TD-001",
        category="valid",
        description="Data",
        linked_test_case_ids=["TC-001"],
        fields=[TestDataField(name="x", value=1, description="d")],
        source="ai_inference",
    )
    filtered, warnings = validate_test_data([data], cases)
    assert len(filtered) == 1
    assert filtered[0].linked_test_case_ids == ["TC-001"]


def test_build_traceability_map():
    reqs = _sample_requirements()
    cases = [_sample_case("TC-001", "REQ-001"), _sample_case("TC-002", "REQ-002")]
    scenarios = [
        TestScenarioInfo(
            scenario_id="SCN-001",
            title="S1",
            description="D",
            flow_steps=["A", "B"],
            requirement_ids=["REQ-001"],
            related_test_case_ids=["TC-001"],
            source="ai_inference",
        )
    ]
    data = [
        GeneratedTestDataInfo(
            data_id="TD-001",
            category="valid",
            description="D",
            linked_test_case_ids=["TC-001"],
            fields=[],
            source="ai_inference",
        )
    ]
    trace = build_traceability_map(reqs, _sample_risks(), cases, scenarios, data)
    assert len(trace.entries) == 2
    assert "REQ-002" not in trace.uncovered_requirements or len(trace.entries) >= 1


def test_build_traceability_uncovered_requirements():
    reqs = _sample_requirements()
    cases = [_sample_case("TC-001", "REQ-001")]
    trace = build_traceability_map(reqs, [], cases, [], [])
    assert "REQ-002" in trace.uncovered_requirements


# --- Node unit tests ---

def test_test_case_generator_node():
    state = _base_state()
    result = generate_test_cases(state)
    assert "test_cases" in result
    assert len(result["test_cases"]) > 0
    assert result["test_cases"][0].requirement_id in ["REQ-001", "REQ-002", "REQ-003"]


def test_scenario_builder_node():
    state = _base_state()
    state["test_cases"] = generate_test_cases(state)["test_cases"]
    result = build_scenarios(state)
    assert "test_scenarios" in result
    assert len(result["test_scenarios"]) > 0
    assert result["test_scenarios"][0].scenario_id.startswith("SCN-")


def test_negative_boundary_generator_node():
    state = _base_state()
    state["test_cases"] = generate_test_cases(state)["test_cases"]
    result = generate_negative_boundary_cases(state)
    assert "test_cases" in result
    categories = {c.test_category for c in result["test_cases"]}
    assert "negative" in categories or "boundary" in categories or "edge" in categories


def test_test_data_generator_node():
    state = _base_state()
    state["test_cases"] = generate_test_cases(state)["test_cases"]
    state["test_cases"] = generate_negative_boundary_cases(state)["test_cases"]
    result = generate_test_data(state)
    assert "generated_test_data" in result
    assert len(result["generated_test_data"]) > 0


def test_traceability_mapper_node():
    state = _base_state()
    state["test_cases"] = generate_test_cases(state)["test_cases"]
    state["test_scenarios"] = build_scenarios(state)["test_scenarios"]
    state["test_cases"] = generate_negative_boundary_cases(state)["test_cases"]
    state["generated_test_data"] = generate_test_data(state)["generated_test_data"]
    result = map_traceability(state)
    assert result["traceability"] is not None
    assert len(result["traceability"].entries) > 0


def test_regression_filtered_when_no_changes():
    state = _base_state(change_impact=ChangeImpactInfo(
        has_changes=False,
        changed_files=[],
        changed_functions=[],
        impacted_requirements=[],
        regression_risk="None",
        message="change information unavailable",
        source="source_code",
    ))
    state["test_cases"] = generate_test_cases(state)["test_cases"]
    result = generate_negative_boundary_cases(state)
    regression_cases = [c for c in result["test_cases"] if c.test_type == "regression"]
    assert len(regression_cases) == 0


def test_get_max_test_cases_default():
    assert get_max_test_cases() == 50
