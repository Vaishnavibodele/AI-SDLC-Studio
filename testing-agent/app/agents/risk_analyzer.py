import logging
from typing import Dict, Any
from app.models.state import TestingState
from app.services.llm import gemini_service, RisksWrapper

logger = logging.getLogger(__name__)

def analyze_risks(state: TestingState) -> Dict[str, Any]:
    """
    Risk Analyzer Node.
    Analyzes architectural design, potential failure points, and maps them to extracted requirements.
    """
    logger.info("Executing Risk Analyzer Node")

    requirements = state.get("requirements") or []
    context = state.get("context") or {}
    design_ctx = context.get("design_context") or {}

    prompt = f"""
    You are an expert QA and Systems Reliability Engineer.
    Based on the extracted requirements and design specifications, identify potential software risks,
    security flaws, and operational bottlenecks.
    
    Requirements:
    {[req.model_dump() for req in requirements]}

    Design Context:
    {design_ctx}

    For each risk, provide:
    - A unique risk ID (e.g., RSK-001, RSK-002)
    - The requirement ID (e.g. REQ-001) that this risk maps to (optional, but prefer mapping if related)
    - Description of the failure scenario
    - Severity ('High', 'Medium', or 'Low')
    - Likelihood ('High', 'Medium', or 'Low')
    - Mitigation (test strategy/assertions to mitigate this risk)
    - Source. Use 'sdd' if the risk was explicitly discussed in the design docs, or 'ai_inference' if reasoned by you.
    """

    system_instruction = (
        "You are a systems risk assessor. Identify software reliability risks and recommend test mitigations. "
        "Each risk must match a valid severity, likelihood, and source ('sdd' or 'ai_inference')."
    )

    try:
        wrapper: RisksWrapper = gemini_service.generate_structured_output(
            prompt=prompt,
            response_schema=RisksWrapper,
            system_instruction=system_instruction
        )

        logger.info(f"Identified {len(wrapper.risks)} risks.")

        return {
            "risks": wrapper.risks
        }

    except Exception as e:
        logger.error(f"Error in Risk Analyzer node: {str(e)}", exc_info=True)
        raise e
