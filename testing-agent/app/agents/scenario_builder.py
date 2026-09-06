import logging
from typing import Dict, Any

from app.models.state import TestingState
from app.services.llm import gemini_service, TestScenariosWrapper
from app.services.test_design_validator import validate_scenarios

logger = logging.getLogger(__name__)


def build_scenarios(state: TestingState) -> Dict[str, Any]:
    """
    Scenario Builder Node.
    Generates higher-level business scenarios from requirements and test strategy.
    """
    logger.info("Executing Scenario Builder Node")

    requirements = state.get("requirements") or []
    test_strategy = state.get("test_strategy")
    test_cases = state.get("test_cases") or []
    context = state.get("context") or {}

    req_dumps = [req.model_dump() for req in requirements]
    case_dumps = [c.model_dump() for c in test_cases]
    strategy_dump = test_strategy.model_dump() if test_strategy else {}

    prompt = f"""
    You are an expert QA Business Analyst.
    Generate higher-level business test scenarios from the requirements and test strategy.

    Requirements:
    {req_dumps}

    Test Strategy:
    {strategy_dump}

    Existing Test Cases:
    {case_dumps}

    Requirements Context:
    {context.get("requirements_context", {})}

    Design Context:
    {context.get("design_context", {})}

    Rules:
    - Each scenario must have a unique scenario_id (SCN-001, SCN-002, ...).
    - flow_steps must describe an ordered business flow (e.g. Login → Action → Verify).
    - requirement_ids must reference valid requirement IDs from the requirements list.
    - related_test_case_ids should reference test cases that validate this scenario.
    - Scenarios must be project-specific, not generic placeholders.
    - Use source: ai_inference.
    """

    system_instruction = (
        "You are a business scenario builder. Create end-to-end business flow scenarios "
        "linked to requirements and test cases. No executable code."
    )

    try:
        wrapper: TestScenariosWrapper = gemini_service.generate_structured_output(
            prompt=prompt,
            response_schema=TestScenariosWrapper,
            system_instruction=system_instruction,
        )

        filtered, warnings = validate_scenarios(
            wrapper.test_scenarios, requirements, test_cases
        )

        logger.info(f"Generated {len(filtered)} test scenarios.")

        return {
            "test_scenarios": filtered,
            "test_design_warnings": (state.get("test_design_warnings") or []) + warnings,
        }

    except Exception as e:
        logger.error(f"Error in Scenario Builder node: {str(e)}", exc_info=True)
        raise e
