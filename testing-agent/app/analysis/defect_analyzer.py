"""Phase 6 defect classification.

A failing test is not automatically a product defect. Classification is derived
from the failure type plus the execution evidence; `defect_detected` is only
true for `product_defect` / `product_defect_candidate`.

No ticketing system is involved: this module only classifies.
"""
from typing import List, Optional, Tuple

from app.analysis.failure_analyzer import extract_status_codes
from app.analysis.schemas import (
    INSUFFICIENT_EVIDENCE_SUMMARY,
    Confidence,
    DefectAnalysis,
    DefectClassification,
    FailureAnalysis,
    FailureType,
    Priority,
    RootCauseAnalysis,
    Severity,
)

_PRODUCT_CLASSES = {
    DefectClassification.PRODUCT_DEFECT,
    DefectClassification.PRODUCT_DEFECT_CANDIDATE,
}

# failure_type -> (classification, title, description, severity, priority, confidence, recommendations)
_STATIC_MAP = {
    FailureType.BROWSER_NETWORK_ERROR: (
        DefectClassification.ENVIRONMENT_ISSUE,
        "Browser could not reach the target host",
        "The browser reported a network/DNS error, so product behaviour was never exercised.",
        Severity.MEDIUM,
        Priority.P3,
        Confidence.HIGH,
        ["Verify the target host is resolvable and reachable from the execution environment"],
    ),
    FailureType.ENDPOINT_UNAVAILABLE: (
        DefectClassification.ENVIRONMENT_ISSUE,
        "Target endpoint unreachable",
        "The endpoint could not be contacted, so no product behaviour was observed.",
        Severity.MEDIUM,
        Priority.P3,
        Confidence.MEDIUM,
        ["Confirm the service is deployed and listening in the target environment"],
    ),
    FailureType.INTEGRATION_TARGET_UNAVAILABLE: (
        DefectClassification.ENVIRONMENT_ISSUE,
        "Integration dependency unavailable",
        "The configured integration target was unavailable or could not be invoked.",
        Severity.MEDIUM,
        Priority.P3,
        Confidence.MEDIUM,
        ["Provision or stub the integration dependency before re-running the suite"],
    ),
    FailureType.TIMEOUT: (
        DefectClassification.ENVIRONMENT_ISSUE,
        "Execution timed out",
        "Execution exceeded the configured timeout; without a response the failure cannot be attributed to the product.",
        Severity.MEDIUM,
        Priority.P3,
        Confidence.LOW,
        ["Re-run with an increased timeout to determine whether the target is slow or unresponsive"],
    ),
    FailureType.INVALID_PYTEST_TARGET: (
        DefectClassification.TEST_CONFIGURATION_ISSUE,
        "Configured pytest target does not exist",
        "Pytest could not collect the configured node/target, so the suite configuration is at fault.",
        Severity.MEDIUM,
        Priority.P2,
        Confidence.HIGH,
        ["Point the generated test case at an existing pytest node id or generate the test file"],
    ),
    FailureType.SELECTOR_NOT_FOUND: (
        DefectClassification.TEST_DEFECT,
        "UI selector no longer matches the application",
        "The element could not be located, indicating an outdated selector in the test asset.",
        Severity.MEDIUM,
        Priority.P3,
        Confidence.MEDIUM,
        ["Update the selector to match the current UI structure"],
    ),
    FailureType.AUTHENTICATION_FAILURE: (
        DefectClassification.TEST_CONFIGURATION_ISSUE,
        "Request was not authenticated",
        "The request was rejected as unauthenticated; test credentials or auth configuration are likely missing.",
        Severity.MEDIUM,
        Priority.P2,
        Confidence.MEDIUM,
        ["Supply valid test credentials or an auth token to the execution configuration"],
    ),
    FailureType.AUTHORIZATION_FAILURE: (
        DefectClassification.TEST_CONFIGURATION_ISSUE,
        "Request lacked required permissions",
        "The request was rejected as unauthorized; the test principal is likely misconfigured.",
        Severity.MEDIUM,
        Priority.P2,
        Confidence.MEDIUM,
        ["Grant the test principal the permissions required by the endpoint"],
    ),
    FailureType.ASSERTION_FAILURE: (
        DefectClassification.PRODUCT_DEFECT_CANDIDATE,
        "Assertion on observed behaviour failed",
        "An assertion failed against real execution output; product behaviour may deviate from the specification.",
        Severity.HIGH,
        Priority.P2,
        Confidence.MEDIUM,
        ["Review the assertion against the requirement to confirm whether the product or the test is wrong"],
    ),
    FailureType.UNKNOWN: (
        DefectClassification.UNKNOWN,
        INSUFFICIENT_EVIDENCE_SUMMARY,
        INSUFFICIENT_EVIDENCE_SUMMARY,
        Severity.LOW,
        Priority.P4,
        Confidence.LOW,
        ["Capture richer execution evidence (details/logs) to enable classification"],
    ),
}


def _classify_http(expected: Optional[int], actual: Optional[int]) -> Tuple:
    if actual is not None and actual >= 500:
        return (
            DefectClassification.PRODUCT_DEFECT_CANDIDATE,
            f"Server returned {actual} for a served request",
            f"The request reached the service but it responded {actual}; server-side behaviour requires investigation.",
            Severity.CRITICAL if actual >= 500 else Severity.HIGH,
            Priority.P1,
            Confidence.MEDIUM if expected is None else Confidence.HIGH,
            ["Inspect server logs for the failing request and reproduce against the implementation"],
        )
    if actual in (400, 422):
        return (
            DefectClassification.TEST_DATA_ISSUE,
            f"Endpoint rejected the request payload with {actual}",
            f"The endpoint responded {actual}, indicating the request data supplied by the test is likely invalid.",
            Severity.MEDIUM,
            Priority.P3,
            Confidence.MEDIUM,
            ["Correct the generated test data / request payload to satisfy the endpoint contract"],
        )
    if actual in (401, 403):
        return (
            DefectClassification.TEST_CONFIGURATION_ISSUE,
            f"Endpoint responded {actual}",
            f"The endpoint responded {actual}; the test authentication/authorization configuration is likely incomplete.",
            Severity.MEDIUM,
            Priority.P2,
            Confidence.MEDIUM,
            ["Provide the credentials/permissions the endpoint requires"],
        )
    if actual == 404:
        return (
            DefectClassification.PRODUCT_DEFECT_CANDIDATE,
            "Endpoint responded 404",
            "The route may be missing from the product, or the configured test target is stale.",
            Severity.MEDIUM,
            Priority.P2,
            Confidence.LOW,
            ["Confirm the route exists in the deployed build and that the test target is current"],
        )
    if actual is not None:
        return (
            DefectClassification.PRODUCT_DEFECT_CANDIDATE,
            f"Endpoint responded {actual} instead of the expected status",
            f"Observed HTTP {actual}" + (f" while {expected} was expected." if expected else "."),
            Severity.MEDIUM,
            Priority.P3,
            Confidence.LOW,
            ["Compare the endpoint contract with the expectation encoded in the test case"],
        )
    return _STATIC_MAP[FailureType.UNKNOWN]


def analyze_failure(
    analysis: FailureAnalysis,
    root_cause: Optional[RootCauseAnalysis] = None,
) -> DefectAnalysis:
    """Classify a single failure into a defect category."""
    if analysis.failure_type is FailureType.HTTP_STATUS_MISMATCH:
        expected, actual = extract_status_codes(" \n".join(analysis.evidence).lower())
        entry = _classify_http(expected, actual)
    else:
        entry = _STATIC_MAP[analysis.failure_type]

    if not analysis.evidence:
        entry = _STATIC_MAP[FailureType.UNKNOWN]

    classification, title, description, severity, priority, confidence, recommendations = entry

    evidence = list(analysis.evidence)
    if root_cause is not None and root_cause.probable_root_cause not in evidence:
        evidence.append(f"root_cause: {root_cause.probable_root_cause}")

    return DefectAnalysis(
        test_case_id=analysis.test_case_id,
        defect_detected=classification in _PRODUCT_CLASSES,
        classification=classification,
        severity=severity,
        priority=priority,
        title=title,
        description=description,
        affected_component=(root_cause.affected_component if root_cause else analysis.module),
        evidence=evidence,
        confidence=confidence,
        recommendations=list(recommendations),
        failure_type=analysis.failure_type,
        run_id=analysis.run_id,
    )


def analyze_failures(
    analyses: List[FailureAnalysis],
    root_causes: Optional[List[RootCauseAnalysis]] = None,
) -> List[DefectAnalysis]:
    by_case = {rc.test_case_id: rc for rc in root_causes or []}
    return [analyze_failure(a, by_case.get(a.test_case_id)) for a in analyses or []]
