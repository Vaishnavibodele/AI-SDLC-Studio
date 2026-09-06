import logging
from typing import Dict, Any
from app.models.state import TestingState, TestStrategyInfo
from app.services.llm import gemini_service

logger = logging.getLogger(__name__)

def plan_strategy(state: TestingState) -> Dict[str, Any]:
    """
    Test Strategy Planner Node.
    Synthesizes requirements, risks, coverage, and code change impact to recommend
    a test plan outlining unit, integration, API verification targets, tools, and environments.
    """
    logger.info("Executing Test Strategy Planner Node")

    requirements = state.get("requirements") or []
    risks = state.get("risks") or []
    change_impact = state.get("change_impact")
    coverage = state.get("coverage")
    context = state.get("context") or {}
    env_ctx = context.get("environment_context") or {}

    # Serialize objects for prompt injection
    req_dumps = [req.model_dump() for req in requirements]
    risk_dumps = [risk.model_dump() for risk in risks]
    impact_dump = change_impact.model_dump() if change_impact else {}
    coverage_dump = coverage.model_dump() if coverage else {}

    prompt = f"""
    You are an expert Test Architect.
    Based on the extracted requirements, identified risks, coverage mappings, and code change impact analysis,
    formulate a detailed Test Strategy for the project.
    
    Requirements:
    {req_dumps}

    System Risks & Mitigations:
    {risk_dumps}

    Change Impact Analysis:
    {impact_dump}

    Ingestion Coverage Assessment:
    {coverage_dump}

    Target Environment Context:
    {env_ctx}

    Your strategy should provide:
    - Target unit tests (assertions, mocks required)
    - Target integration tests (service-to-service checks)
    - Target API/Contract tests (endpoint URL specs, validation expectations)
    - Recommended tools (e.g., pytest, httpx, pytest-mock)
    - Recommended test environments (e.g. local, staging, dev)
    - Source. Use 'ai_inference'.
    """

    system_instruction = (
        "You are a test architect. Generate a structured test strategy mapping out unit, "
        "integration, and API contract test actions. Recommend appropriate tools and environments. "
        "Use 'ai_inference' as the source."
    )

    try:
        strategy_info: TestStrategyInfo = gemini_service.generate_structured_output(
            prompt=prompt,
            response_schema=TestStrategyInfo,
            system_instruction=system_instruction
        )

        logger.info("Test Strategy planning completed.")

        return {
            "test_strategy": strategy_info
        }

    except Exception as e:
        logger.error(f"Error in Test Strategy Planner node: {str(e)}", exc_info=True)
        raise e
