import logging
from typing import Dict, Any
from app.models.state import TestingState, ChangeImpactInfo
from app.services.llm import gemini_service

logger = logging.getLogger(__name__)

def analyze_impact(state: TestingState) -> Dict[str, Any]:
    """
    Change Impact Analyzer Node.
    Analyzes code change metadata against requirements to assess regression risk.
    If no change metadata is provided, reports 'change information unavailable'.
    """
    logger.info("Executing Change Impact Analyzer Node")

    source_code = state.get("source_code") or {}
    requirements = state.get("requirements") or []

    # Deterministic check: verify if change metadata is present
    changes = source_code.get("changes")
    
    if not changes:
        logger.info("No change metadata found. Short-circuiting with change information unavailable.")
        # Return explicit "change information unavailable" state without LLM call
        impact_info = ChangeImpactInfo(
            has_changes=False,
            changed_files=[],
            changed_functions=[],
            impacted_requirements=[],
            regression_risk="None",
            message="change information unavailable",
            source="source_code"
        )
        return {"change_impact": impact_info}

    # If changes are present, proceed with LLM analysis
    logger.info("Change metadata detected. Invoking LLM for regression analysis.")
    
    changed_files = changes.get("changed_files") or []
    changed_functions = changes.get("changed_functions") or []
    git_diff = changes.get("diff") or ""

    prompt = f"""
    You are an expert software developer and QA lead.
    Assess the impact of the following code changes on the project requirements.
    
    Requirements:
    {[req.model_dump() for req in requirements]}

    Changes metadata:
    - Changed Files: {changed_files}
    - Changed Functions: {changed_functions}
    - Git Diff: {git_diff}
    
    Determine:
    - If there are real changes (has_changes)
    - The regression risk level ('High', 'Medium', 'Low', 'None')
    - Which requirement IDs are directly or indirectly impacted by these changes
    - A detailed message summarizing the impact or warning about potential regressions
    - The source of this analysis. Use 'source_code' since it evaluates code changes.
    """

    system_instruction = (
        "You are a code change impact analyst. Identify regression risks in requirements "
        "impacted by code diffs and file changes."
    )

    try:
        impact_info: ChangeImpactInfo = gemini_service.generate_structured_output(
            prompt=prompt,
            response_schema=ChangeImpactInfo,
            system_instruction=system_instruction
        )
        
        # Ensure files and functions from state are preserved/filled in if Gemini leaves them empty
        if not impact_info.changed_files:
            impact_info.changed_files = changed_files
        if not impact_info.changed_functions:
            impact_info.changed_functions = changed_functions

        logger.info(f"Change impact analysis completed. Risk: {impact_info.regression_risk}")

        return {
            "change_impact": impact_info
        }

    except Exception as e:
        logger.error(f"Error in Change Impact Analyzer node: {str(e)}", exc_info=True)
        raise e
