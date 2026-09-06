import logging
from typing import Dict, Any

from app.models.state import TestingState
from app.services.llm import gemini_service, TestDataWrapper
from app.services.test_design_validator import validate_test_data

logger = logging.getLogger(__name__)


def generate_test_data(state: TestingState) -> Dict[str, Any]:
    """
    Test Data Generator Node.
    Generates meaningful test data linked to test cases.
    """
    logger.info("Executing Test Data Generator Node")

    test_cases = state.get("test_cases") or []
    requirements = state.get("requirements") or []
    context = state.get("context") or {}

    case_dumps = [c.model_dump() for c in test_cases]
    req_dumps = [req.model_dump() for req in requirements]

    prompt = f"""
    You are an expert QA Test Data Designer.
    Generate meaningful, project-specific test data linked to test cases.

    Test Cases:
    {case_dumps}

    Requirements:
    {req_dumps}

    Database Context:
    {context.get("database_context", {})}

    API Context:
    {context.get("api_context", {})}

    Existing Test Data Context:
    {context.get("test_data_context", {})}

    Rules:
    - Each data record must have a unique data_id (TD-001, TD-002, ...).
    - category must be one of: valid, invalid, boundary, edge.
    - linked_test_case_ids must reference valid test case IDs from the test cases list.
    - fields must contain meaningful, project-specific values — not random meaningless data.
    - Values must relate to the requirement, acceptance criteria, or test case purpose.
    - Do NOT generate executable code or scripts.
    - Use source: ai_inference.
    """

    system_instruction = (
        "You are a test data generator. Create structured, meaningful test data "
        "linked to specific test cases. No executable code."
    )

    try:
        wrapper: TestDataWrapper = gemini_service.generate_structured_output(
            prompt=prompt,
            response_schema=TestDataWrapper,
            system_instruction=system_instruction,
        )

        filtered, warnings = validate_test_data(
            wrapper.generated_test_data, test_cases
        )

        logger.info(f"Generated {len(filtered)} test data records.")

        return {
            "generated_test_data": filtered,
            "test_design_warnings": (state.get("test_design_warnings") or []) + warnings,
        }

    except Exception as e:
        logger.error(f"Error in Test Data Generator node: {str(e)}", exc_info=True)
        raise e
