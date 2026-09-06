import logging
from typing import Dict, Any

from app.models.state import TestingState
from app.services.test_design_validator import build_traceability_map

logger = logging.getLogger(__name__)


def map_traceability(state: TestingState) -> Dict[str, Any]:
    """
    Traceability Mapper Node.
    Deterministically builds requirement → scenario → test case → test data traceability.
    """
    logger.info("Executing Traceability Mapper Node")

    requirements = state.get("requirements") or []
    risks = state.get("risks") or []
    test_cases = state.get("test_cases") or []
    test_scenarios = state.get("test_scenarios") or []
    generated_test_data = state.get("generated_test_data") or []

    traceability = build_traceability_map(
        requirements=requirements,
        risks=risks,
        test_cases=test_cases,
        test_scenarios=test_scenarios,
        generated_test_data=generated_test_data,
    )

    warnings = list(state.get("test_design_warnings") or [])

    if traceability.uncovered_requirements:
        warnings.append(
            f"Uncovered requirements (no test cases): "
            f"{', '.join(traceability.uncovered_requirements)}."
        )

    if traceability.orphaned_test_cases:
        warnings.append(
            f"Orphaned test cases (no traceability entry): "
            f"{', '.join(traceability.orphaned_test_cases)}."
        )

    if traceability.orphaned_test_data:
        warnings.append(
            f"Orphaned test data (not linked): "
            f"{', '.join(traceability.orphaned_test_data)}."
        )

    logger.info(
        f"Traceability mapping completed. "
        f"{len(traceability.entries)} entries, "
        f"{len(traceability.uncovered_requirements)} uncovered requirements."
    )

    return {
        "traceability": traceability,
        "test_design_warnings": warnings,
    }
