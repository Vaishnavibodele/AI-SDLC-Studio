"""Phase 6 root cause analyzer.

Infers a probable root cause for each `FailureAnalysis`. Inference is
deterministic and evidence bound: when the failure could not be classified, the
root cause is reported as `UNKNOWN_ROOT_CAUSE` with LOW confidence.
"""
from typing import List, Optional, Tuple

from app.analysis.failure_analyzer import extract_status_codes
from app.analysis.schemas import (
    UNKNOWN_ROOT_CAUSE,
    Confidence,
    FailureAnalysis,
    FailureType,
    RootCauseAnalysis,
    RootCauseCategory,
)

_CAUSES = {
    FailureType.BROWSER_NETWORK_ERROR: (
        "Target host could not be resolved or reached from the execution environment",
        RootCauseCategory.ENVIRONMENT,
        Confidence.HIGH,
    ),
    FailureType.INVALID_PYTEST_TARGET: (
        "Generated pytest target is invalid or unavailable in the execution workspace",
        RootCauseCategory.CONFIGURATION,
        Confidence.HIGH,
    ),
    FailureType.SELECTOR_NOT_FOUND: (
        "Selector mismatch or changed UI structure",
        RootCauseCategory.TEST_CODE,
        Confidence.MEDIUM,
    ),
    FailureType.TIMEOUT: (
        "Target did not respond within the configured timeout window",
        RootCauseCategory.ENVIRONMENT,
        Confidence.MEDIUM,
    ),
    FailureType.ENDPOINT_UNAVAILABLE: (
        "Target endpoint is down, unreachable, or not deployed in this environment",
        RootCauseCategory.ENVIRONMENT,
        Confidence.MEDIUM,
    ),
    FailureType.INTEGRATION_TARGET_UNAVAILABLE: (
        "Integration dependency is unavailable or the configured target cannot be invoked",
        RootCauseCategory.ENVIRONMENT,
        Confidence.MEDIUM,
    ),
    FailureType.AUTHENTICATION_FAILURE: (
        "Request was not authenticated; credentials or auth token are missing or invalid",
        RootCauseCategory.CONFIGURATION,
        Confidence.MEDIUM,
    ),
    FailureType.AUTHORIZATION_FAILURE: (
        "Authenticated principal lacks the permissions required by the endpoint",
        RootCauseCategory.CONFIGURATION,
        Confidence.MEDIUM,
    ),
    FailureType.ASSERTION_FAILURE: (
        "Observed behaviour differs from the asserted expectation",
        RootCauseCategory.APPLICATION_CODE,
        Confidence.MEDIUM,
    ),
    FailureType.UNKNOWN: (
        UNKNOWN_ROOT_CAUSE,
        RootCauseCategory.UNKNOWN,
        Confidence.LOW,
    ),
}


def _http_cause(
    expected: Optional[int],
    actual: Optional[int],
) -> Tuple[str, RootCauseCategory, Confidence]:
    if actual is not None and actual >= 500:
        if expected in (401, 403):
            return (
                "Server returned an unexpected authentication/authorization response "
                f"(expected {expected}, received {actual})",
                RootCauseCategory.APPLICATION_CODE,
                Confidence.MEDIUM,
            )
        detail = f"(expected {expected}, received {actual})" if expected else f"(received {actual})"
        return (
            f"Server returned a server-side error instead of the expected response {detail}",
            RootCauseCategory.APPLICATION_CODE,
            Confidence.HIGH if expected is not None else Confidence.MEDIUM,
        )

    if actual in (400, 422):
        return (
            f"Endpoint rejected the request payload with {actual}; the supplied test data is likely invalid",
            RootCauseCategory.TEST_DATA,
            Confidence.MEDIUM,
        )

    if expected is not None and actual is not None:
        return (
            f"Endpoint responded with {actual} while the test expected {expected}; "
            "request contract or endpoint behaviour differs",
            RootCauseCategory.APPLICATION_CODE,
            Confidence.MEDIUM,
        )

    return (
        "HTTP response status differed from the expectation encoded in the test case",
        RootCauseCategory.UNKNOWN,
        Confidence.LOW,
    )


def analyze_failure(analysis: FailureAnalysis) -> RootCauseAnalysis:
    """Infer the probable root cause for a single failure analysis."""
    if analysis.failure_type is FailureType.HTTP_STATUS_MISMATCH:
        expected, actual = extract_status_codes(" \n".join(analysis.evidence).lower())
        cause, category, confidence = _http_cause(expected, actual)
    else:
        cause, category, confidence = _CAUSES[analysis.failure_type]

    if not analysis.evidence:
        cause, category, confidence = UNKNOWN_ROOT_CAUSE, RootCauseCategory.UNKNOWN, Confidence.LOW

    return RootCauseAnalysis(
        test_case_id=analysis.test_case_id,
        probable_root_cause=cause,
        affected_component=analysis.module,
        category=category,
        evidence=analysis.evidence,
        confidence=confidence,
        failure_type=analysis.failure_type,
        run_id=analysis.run_id,
    )


def analyze_failures(analyses: List[FailureAnalysis]) -> List[RootCauseAnalysis]:
    return [analyze_failure(a) for a in analyses or []]
