import logging
from typing import Dict, Any, List

from app.models.state import TestingState
from app.services.llm import gemini_service, TestCasesWrapper
from app.services.test_design_validator import validate_and_filter_test_cases

logger = logging.getLogger(__name__)


def generate_test_cases(state: TestingState) -> Dict[str, Any]:
    """
    Test Case Generator Node.
    Generates structured positive/happy-path/core test specifications from Phase 2 outputs.
    Does NOT generate executable test code.
    """
    logger.info("Executing Test Case Generator Node")

    requirements = state.get("requirements") or []
    risks = state.get("risks") or []
    change_impact = state.get("change_impact")
    coverage = state.get("coverage")
    test_strategy = state.get("test_strategy")
    context = state.get("context") or {}

    req_dumps = [req.model_dump() for req in requirements]
    risk_dumps = [risk.model_dump() for risk in risks]
    impact_dump = change_impact.model_dump() if change_impact else {}
    coverage_dump = coverage.model_dump() if coverage else {}
    strategy_dump = test_strategy.model_dump() if test_strategy else {}

    prompt = f"""
    You are an expert QA Test Designer for a single unified Testing Agent.
    Generate structured test case SPECIFICATIONS (not executable code) based on the analysis below.

    Requirements:
    {req_dumps}

    Risks:
    {risk_dumps}

    Change Impact:
    {impact_dump}

    Coverage:
    {coverage_dump}

    Test Strategy:
    {strategy_dump}

    Design Context:
    {context.get("design_context", {})}

    Code Context:
    {context.get("code_context", {})}

    API Context:
    {context.get("api_context", {})}

    Rules:
    - Generate positive, happy_path, and core functional test cases only (NOT negative/boundary/edge).
    - Each test case must reference a valid requirement_id from the requirements list.
    - Use test_type from: unit, integration, api, ui, security, regression.
    - Use test_category from: positive, happy_path (only these categories in this step).
    - Do NOT generate regression tests unless change impact shows has_changes=true.
    - Do NOT generate Pytest, Selenium, Playwright, or any executable code.
    - Assign unique test_case_id values (TC-001, TC-002, ...).
    - Include meaningful preconditions, steps, assertions, and expected_result.
    - Link risk_id only when a matching risk exists.
    - Cover high-risk and complex requirements with multiple tests where justified.
    - Use source: ai_inference.
    """

    system_instruction = (
        "You are a test case specification generator. Output structured test specifications only. "
        "No executable code. Reference only known requirement and risk IDs."
    )

    try:
        wrapper: TestCasesWrapper = gemini_service.generate_structured_output(
            prompt=prompt,
            response_schema=TestCasesWrapper,
            system_instruction=system_instruction,
        )

        filtered, warnings = validate_and_filter_test_cases(
            wrapper.test_cases, requirements, risks, change_impact
        )

        logger.info(f"Generated {len(filtered)} test case specifications.")

        return {
            "test_cases": filtered,
            "test_design_warnings": (state.get("test_design_warnings") or []) + warnings,
        }

    except Exception as e:
        logger.error(f"Error in Test Case Generator node: {str(e)}", exc_info=True)
        raise e
