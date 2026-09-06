import logging
from typing import Dict, Any
from app.models.state import TestingState, CoverageInfo
from app.services.llm import gemini_service

logger = logging.getLogger(__name__)

def analyze_coverage(state: TestingState) -> Dict[str, Any]:
    """
    Coverage Analyzer Node.
    Maps requirements to developed source code and APIs to evaluate requirement coverage.
    Does not run dynamic code execution coverage, but maps static design/endpoint structures.
    """
    logger.info("Executing Coverage Analyzer Node")

    requirements = state.get("requirements") or []
    context = state.get("context") or {}
    code_ctx = context.get("code_context") or {}
    api_ctx = context.get("api_context") or {}

    prompt = f"""
    You are an expert QA Analyst.
    Perform a requirement coverage analysis. Map the extracted requirements to the source code files
    and API endpoints that implement them.
    
    Requirements:
    {[req.model_dump() for req in requirements]}

    Code Structure:
    {code_ctx}

    API Docs / Endpoints:
    {api_ctx}

    For the response, determine:
    - Which requirement IDs have implementation support (mapped_requirements)
    - Which requirement IDs have no implementation support yet (uncovered_requirements)
    - The percentage of requirements covered (coverage_percentage)
    - The source of this analysis. Use 'ai_inference'.
    """

    system_instruction = (
        "You are a test coverage analyzer. Map functional requirements to existing source code "
        "and API endpoint listings. Calculate coverage percentage based on this mapping. "
        "Use 'ai_inference' as the source."
    )

    try:
        coverage_info: CoverageInfo = gemini_service.generate_structured_output(
            prompt=prompt,
            response_schema=CoverageInfo,
            system_instruction=system_instruction
        )

        logger.info(f"Requirement coverage analysis completed. Percentage: {coverage_info.coverage_percentage}%")

        return {
            "coverage": coverage_info
        }

    except Exception as e:
        logger.error(f"Error in Coverage Analyzer node: {str(e)}", exc_info=True)
        raise e
