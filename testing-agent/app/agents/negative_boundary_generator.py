import logging
from typing import Dict, Any

from app.models.state import TestingState
from app.services.llm import gemini_service, NegativeBoundaryTestCasesWrapper
from app.services.test_design_validator import merge_test_cases

logger = logging.getLogger(__name__)


def generate_negative_boundary_cases(state: TestingState) -> Dict[str, Any]:
    """
    Negative/Boundary Test Generator Node.
    Generates negative, boundary, and edge test cases based on requirements, risks,
    acceptance criteria, architecture, and test strategy.
    """
    logger.info("Executing Negative/Boundary Generator Node")

    requirements = state.get("requirements") or []
    risks = state.get("risks") or []
    change_impact = state.get("change_impact")
    test_strategy = state.get("test_strategy")
    existing_cases = state.get("test_cases") or []
    context = state.get("context") or {}

    req_dumps = [req.model_dump() for req in requirements]
    risk_dumps = [risk.model_dump() for risk in risks]
    strategy_dump = test_strategy.model_dump() if test_strategy else {}
    impact_dump = change_impact.model_dump() if change_impact else {}

    prompt = f"""
    You are an expert QA Test Designer specializing in negative, boundary, and edge case testing.
    Generate structured test case SPECIFICATIONS (not executable code).

    Requirements:
    {req_dumps}

    Risks:
    {risk_dumps}

    Change Impact:
    {impact_dump}

    Test Strategy:
    {strategy_dump}

    Requirements Context (acceptance criteria):
    {context.get("requirements_context", {})}

    Design Context (architecture):
    {context.get("design_context", {})}

    Existing Test Cases (avoid duplicating these):
    {[c.model_dump() for c in existing_cases]}

    Rules:
    - Generate ONLY test_category: negative, boundary, or edge.
    - Each case must reference a valid requirement_id from the requirements list.
    - Cases must be derived from actual requirements, risks, acceptance criteria, or architecture.
    - Do NOT generate generic unrelated cases.
    - Do NOT generate regression tests unless change impact shows has_changes=true.
    - Do NOT generate Pytest, Selenium, Playwright, or executable code.
    - Assign new unique test_case_id values continuing from existing cases.
    - Use test_type from: unit, integration, api, ui, security, regression.
    - Use source: ai_inference.
    """

    system_instruction = (
        "You are a negative/boundary/edge test case generator. Output structured specifications only. "
        "Cases must be project-specific and reference known requirement IDs."
    )

    try:
        wrapper: NegativeBoundaryTestCasesWrapper = gemini_service.generate_structured_output(
            prompt=prompt,
            response_schema=NegativeBoundaryTestCasesWrapper,
            system_instruction=system_instruction,
        )

        merged, warnings = merge_test_cases(
            existing_cases,
            wrapper.test_cases,
            requirements,
            risks,
            change_impact,
        )

        logger.info(
            f"Added negative/boundary/edge cases. Total test cases: {len(merged)}."
        )

        return {
            "test_cases": merged,
            "test_design_warnings": (state.get("test_design_warnings") or []) + warnings,
        }

    except Exception as e:
        logger.error(f"Error in Negative/Boundary Generator node: {str(e)}", exc_info=True)
        raise e
