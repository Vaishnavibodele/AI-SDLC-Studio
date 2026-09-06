import logging
from typing import Literal
from langgraph.graph import StateGraph, START, END

from app.models.state import TestingState
from app.agents.input_validator import validate_input
from app.agents.context_loader import load_context
from app.agents.requirement_analyzer import analyze_requirements
from app.agents.risk_analyzer import analyze_risks
from app.agents.impact_analyzer import analyze_impact
from app.agents.coverage_analyzer import analyze_coverage
from app.agents.strategy_planner import plan_strategy
from app.agents.test_case_generator import generate_test_cases
from app.agents.scenario_builder import build_scenarios
from app.agents.negative_boundary_generator import generate_negative_boundary_cases
from app.agents.test_data_generator import generate_test_data
from app.agents.traceability_mapper import map_traceability

logger = logging.getLogger(__name__)

def check_validation_status(state: TestingState) -> Literal["continue", "end"]:
    """
    Conditional router to check if validation passed.
    """
    status = state.get("validation_status")
    logger.info(f"Conditional Router checking validation status: {status}")
    if status == "passed":
        return "continue"
    return "end"

# Initialize StateGraph with the TestingState model
workflow = StateGraph(TestingState)

# Add all nodes in the workflow pipeline
workflow.add_node("input_validation", validate_input)
workflow.add_node("context_loader", load_context)
workflow.add_node("requirement_analyzer", analyze_requirements)
workflow.add_node("risk_analyzer", analyze_risks)
workflow.add_node("impact_analyzer", analyze_impact)
workflow.add_node("coverage_analyzer", analyze_coverage)
workflow.add_node("strategy_planner", plan_strategy)
workflow.add_node("test_case_generator", generate_test_cases)
workflow.add_node("scenario_builder", build_scenarios)
workflow.add_node("negative_boundary_generator", generate_negative_boundary_cases)
workflow.add_node("test_data_generator", generate_test_data)
workflow.add_node("traceability_mapper", map_traceability)

# Set the flow starting at input validation
workflow.add_edge(START, "input_validation")

# Add conditional edge based on validation outcome
workflow.add_conditional_edges(
    "input_validation",
    check_validation_status,
    {
        "continue": "context_loader",
        "end": END
    }
)

# Connect nodes sequentially
workflow.add_edge("context_loader", "requirement_analyzer")
workflow.add_edge("requirement_analyzer", "risk_analyzer")
workflow.add_edge("risk_analyzer", "impact_analyzer")
workflow.add_edge("impact_analyzer", "coverage_analyzer")
workflow.add_edge("coverage_analyzer", "strategy_planner")
workflow.add_edge("strategy_planner", "test_case_generator")
workflow.add_edge("test_case_generator", "scenario_builder")
workflow.add_edge("scenario_builder", "negative_boundary_generator")
workflow.add_edge("negative_boundary_generator", "test_data_generator")
workflow.add_edge("test_data_generator", "traceability_mapper")
workflow.add_edge("traceability_mapper", END)

# Compile the workflow
testing_workflow = workflow.compile()
