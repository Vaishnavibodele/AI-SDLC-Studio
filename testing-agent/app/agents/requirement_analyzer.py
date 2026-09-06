import logging
from typing import Dict, Any
from app.models.state import TestingState
from app.services.llm import gemini_service, RequirementsWrapper

logger = logging.getLogger(__name__)

def analyze_requirements(state: TestingState) -> Dict[str, Any]:
    """
    Requirement Analyzer Node.
    Extracts structured, testable functional and non-functional requirements
    from the raw SRS and SDD contexts.
    """
    logger.info("Executing Requirement Analyzer Node")

    context = state.get("context") or {}
    requirements_ctx = context.get("requirements_context") or {}
    design_ctx = context.get("design_context") or {}

    prompt = f"""
    You are an expert Quality Assurance Engineer.
    Extract a list of testable functional and non-functional requirements from the following metadata.
    Each requirement must have:
    - A unique requirement ID (e.g. REQ-001, REQ-002, etc.)
    - A detailed description of what is to be verified.
    - A category (e.g., 'Functional', 'Non-Functional', 'Security', 'Performance').
    - A source indicating where this requirement was found. Use 'srs' if it comes from the Requirements,
      'sdd' if it comes from the Design, or 'ai_inference' if inferred based on QA requirements.

    Requirements Context (SRS):
    {requirements_ctx}

    Design Context (SDD):
    {design_ctx}
    """

    system_instruction = (
        "You are a test requirement extractor. Extract testable assertions from project documentation. "
        "Each requirement must have a category and a clear source ('srs', 'sdd', or 'ai_inference')."
    )

    try:
        # Call the shared Gemini Service
        wrapper: RequirementsWrapper = gemini_service.generate_structured_output(
            prompt=prompt,
            response_schema=RequirementsWrapper,
            system_instruction=system_instruction
        )

        logger.info(f"Extracted {len(wrapper.requirements)} testable requirements.")

        return {
            "requirements": wrapper.requirements
        }

    except Exception as e:
        logger.error(f"Error in Requirement Analyzer node: {str(e)}", exc_info=True)
        raise e
