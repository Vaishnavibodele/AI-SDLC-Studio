import os
import logging
from typing import List, Tuple, Set, Optional

from app.models.state import (
    TestCaseInfo,
    TestScenarioInfo,
    GeneratedTestDataInfo,
    TraceabilityEntry,
    TraceabilityMap,
    ChangeImpactInfo,
    RequirementInfo,
    RiskInfo,
)

logger = logging.getLogger(__name__)

PRIORITY_ORDER = {"High": 0, "Medium": 1, "Low": 2}


def get_max_test_cases() -> int:
    return int(os.getenv("MAX_TEST_CASES", "50"))


def _normalize_key(title: str, requirement_id: str, test_type: str, test_category: str) -> str:
    return f"{title.strip().lower()}|{requirement_id}|{test_type}|{test_category}"


def validate_and_filter_test_cases(
    test_cases: List[TestCaseInfo],
    requirements: List[RequirementInfo],
    risks: List[RiskInfo],
    change_impact: Optional[ChangeImpactInfo],
) -> Tuple[List[TestCaseInfo], List[str]]:
    """
    Deterministically validate, deduplicate, filter regression cases,
    and enforce MAX_TEST_CASES on test case lists.
    """
    warnings: List[str] = []
    valid_req_ids: Set[str] = {req.id for req in requirements}
    valid_risk_ids: Set[str] = {risk.risk_id for risk in risks}

    allow_regression = (
        change_impact is not None
        and change_impact.has_changes
        and change_impact.message != "change information unavailable"
    )

    filtered: List[TestCaseInfo] = []
    seen_ids: Set[str] = set()
    seen_semantic: Set[str] = set()

    for case in test_cases:
        if case.test_type == "regression" and not allow_regression:
            warnings.append(
                f"Removed regression test case '{case.test_case_id}' — no real change metadata available."
            )
            continue

        if case.requirement_id not in valid_req_ids:
            warnings.append(
                f"Removed test case '{case.test_case_id}' — invalid requirement_id '{case.requirement_id}'."
            )
            continue

        if case.risk_id is not None and case.risk_id not in valid_risk_ids:
            warnings.append(
                f"Cleared invalid risk_id on test case '{case.test_case_id}' — "
                f"'{case.risk_id}' not found."
            )
            case = case.model_copy(update={"risk_id": None})

        if case.test_case_id in seen_ids:
            warnings.append(f"Removed duplicate test_case_id '{case.test_case_id}'.")
            continue

        semantic_key = _normalize_key(
            case.title, case.requirement_id, case.test_type, case.test_category
        )
        if semantic_key in seen_semantic:
            warnings.append(
                f"Removed semantic duplicate test case '{case.test_case_id}' ({case.title})."
            )
            continue

        seen_ids.add(case.test_case_id)
        seen_semantic.add(semantic_key)
        filtered.append(case)

    max_cases = get_max_test_cases()
    if len(filtered) > max_cases:
        filtered.sort(key=lambda c: PRIORITY_ORDER.get(c.priority, 99))
        truncated = len(filtered) - max_cases
        filtered = filtered[:max_cases]
        warnings.append(
            f"Truncated {truncated} test case(s) due to MAX_TEST_CASES limit ({max_cases})."
        )

    return filtered, warnings


def merge_test_cases(
    existing: List[TestCaseInfo],
    new_cases: List[TestCaseInfo],
    requirements: List[RequirementInfo],
    risks: List[RiskInfo],
    change_impact: Optional[ChangeImpactInfo],
) -> Tuple[List[TestCaseInfo], List[str]]:
    """Merge two test case lists with full validation."""
    combined = existing + new_cases
    return validate_and_filter_test_cases(combined, requirements, risks, change_impact)


def validate_test_data(
    test_data: List[GeneratedTestDataInfo],
    test_cases: List[TestCaseInfo],
) -> Tuple[List[GeneratedTestDataInfo], List[str]]:
    """Validate test data IDs and linked test case references."""
    warnings: List[str] = []
    valid_case_ids: Set[str] = {c.test_case_id for c in test_cases}
    seen_data_ids: Set[str] = set()
    filtered: List[GeneratedTestDataInfo] = []

    for data in test_data:
        if data.data_id in seen_data_ids:
            warnings.append(f"Removed duplicate test data ID '{data.data_id}'.")
            continue

        valid_links = [cid for cid in data.linked_test_case_ids if cid in valid_case_ids]
        if len(valid_links) != len(data.linked_test_case_ids):
            invalid = set(data.linked_test_case_ids) - valid_case_ids
            warnings.append(
                f"Removed invalid linked_test_case_ids from '{data.data_id}': {sorted(invalid)}."
            )

        if not valid_links:
            warnings.append(
                f"Removed test data '{data.data_id}' — no valid linked test cases."
            )
            continue

        seen_data_ids.add(data.data_id)
        filtered.append(data.model_copy(update={"linked_test_case_ids": valid_links}))

    return filtered, warnings


def validate_scenarios(
    scenarios: List[TestScenarioInfo],
    requirements: List[RequirementInfo],
    test_cases: List[TestCaseInfo],
) -> Tuple[List[TestScenarioInfo], List[str]]:
    """Validate scenario requirement and test case references."""
    warnings: List[str] = []
    valid_req_ids: Set[str] = {req.id for req in requirements}
    valid_case_ids: Set[str] = {c.test_case_id for c in test_cases}
    seen_ids: Set[str] = set()
    filtered: List[TestScenarioInfo] = []

    for scenario in scenarios:
        if scenario.scenario_id in seen_ids:
            warnings.append(f"Removed duplicate scenario_id '{scenario.scenario_id}'.")
            continue

        valid_reqs = [rid for rid in scenario.requirement_ids if rid in valid_req_ids]
        if not valid_reqs:
            warnings.append(
                f"Removed scenario '{scenario.scenario_id}' — no valid requirement_ids."
            )
            continue

        if len(valid_reqs) != len(scenario.requirement_ids):
            invalid = set(scenario.requirement_ids) - valid_req_ids
            warnings.append(
                f"Removed invalid requirement_ids from scenario '{scenario.scenario_id}': "
                f"{sorted(invalid)}."
            )

        valid_cases = [
            cid for cid in scenario.related_test_case_ids if cid in valid_case_ids
        ]

        seen_ids.add(scenario.scenario_id)
        filtered.append(
            scenario.model_copy(
                update={
                    "requirement_ids": valid_reqs,
                    "related_test_case_ids": valid_cases,
                }
            )
        )

    return filtered, warnings


def build_traceability_map(
    requirements: List[RequirementInfo],
    risks: List[RiskInfo],
    test_cases: List[TestCaseInfo],
    test_scenarios: List[TestScenarioInfo],
    generated_test_data: List[GeneratedTestDataInfo],
) -> TraceabilityMap:
    """
    Deterministically build requirement → scenario → test case → test data traceability.
    """
    req_ids = {req.id for req in requirements}
    covered_reqs: Set[str] = set()
    entries: List[TraceabilityEntry] = []
    linked_data_ids: Set[str] = set()
    linked_case_ids: Set[str] = set()

    risk_by_req = {}
    for risk in risks:
        if risk.requirement_id:
            risk_by_req.setdefault(risk.requirement_id, risk.risk_id)

    data_by_case: dict = {}
    for data in generated_test_data:
        for case_id in data.linked_test_case_ids:
            data_by_case.setdefault(case_id, []).append(data.data_id)

    for case in test_cases:
        scenario_id = _find_scenario_for_case(case, test_scenarios)
        if not scenario_id:
            scenario_id = _fallback_scenario_id(case.requirement_id, test_scenarios)

        data_ids = list(case.test_data_ids) if case.test_data_ids else data_by_case.get(case.test_case_id, [])

        entries.append(
            TraceabilityEntry(
                requirement_id=case.requirement_id,
                risk_id=case.risk_id or risk_by_req.get(case.requirement_id),
                design_component=case.design_component,
                code_target=case.code_target,
                scenario_id=scenario_id,
                test_case_id=case.test_case_id,
                test_data_ids=data_ids,
            )
        )
        covered_reqs.add(case.requirement_id)
        linked_case_ids.add(case.test_case_id)
        linked_data_ids.update(data_ids)

    uncovered = sorted(req_ids - covered_reqs)
    orphaned_cases = sorted(
        {c.test_case_id for c in test_cases} - linked_case_ids
    )
    orphaned_data = sorted(
        {d.data_id for d in generated_test_data} - linked_data_ids
    )

    return TraceabilityMap(
        entries=entries,
        uncovered_requirements=uncovered,
        orphaned_test_cases=orphaned_cases,
        orphaned_test_data=orphaned_data,
        source="ai_inference",
    )


def _find_scenario_for_case(
    case: TestCaseInfo, scenarios: List[TestScenarioInfo]
) -> Optional[str]:
    for scenario in scenarios:
        if case.test_case_id in scenario.related_test_case_ids:
            return scenario.scenario_id
        if case.requirement_id in scenario.requirement_ids:
            return scenario.scenario_id
    return None


def _fallback_scenario_id(
    requirement_id: str, scenarios: List[TestScenarioInfo]
) -> str:
    for scenario in scenarios:
        if requirement_id in scenario.requirement_ids:
            return scenario.scenario_id
    return "SCN-UNMAPPED"
