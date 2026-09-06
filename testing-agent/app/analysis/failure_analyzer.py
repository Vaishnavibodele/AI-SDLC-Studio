"""Phase 6 failure analyzer.

Deterministically classifies FAILED and ERRORED Phase 5 execution results using
only the evidence present in the execution result (`details`, `attempts_detail`,
`logs`). No evidence is invented: when a result carries no usable detail the
analysis is reported as `unknown` / `Insufficient execution evidence`.

PASS and SKIPPED results are never treated as failures.
"""
from typing import Any, Dict, List, Optional, Tuple
import re

from app.analysis.schemas import (
    INSUFFICIENT_EVIDENCE_SUMMARY,
    Confidence,
    FailureAnalysis,
    FailureType,
)

FAILING_STATUSES = {"FAIL", "ERROR"}

# "Expected status 200, got 500" / "Expected 200 but received 500"
_EXPECTED_ACTUAL_RE = re.compile(
    r"expected\s+(?:status\s+(?:code\s+)?)?(\d{3})\b[^\d]{0,40}?(\d{3})\b",
    re.IGNORECASE,
)
_HTTP_STATUS_RE = re.compile(r"\bhttp\s*(\d{3})\b", re.IGNORECASE)

_BROWSER_NETWORK_MARKERS = (
    "err_name_not_resolved",
    "err_internet_disconnected",
    "err_connection_refused",
    "err_connection_reset",
    "err_connection_timed_out",
    "err_address_unreachable",
    "net::",
    "webdriverexception",
    "chrome not reachable",
    "session not created",
)
_INVALID_PYTEST_MARKERS = (
    "file or directory not found",
    "no tests ran",
    "error: not found",
    "usage: pytest",
    "no pytest nodeid",
)
_SELECTOR_MARKERS = (
    "no such element",
    "unable to locate element",
    "element not found",
    "nosuchelementexception",
    "elementnotinteractable",
    "selector not found",
)
_TIMEOUT_MARKERS = (
    "timeout",
    "timed out",
    "timeoutexpired",
    "timeoutexception",
    "readtimeout",
)
_CONNECTION_MARKERS = (
    "connection refused",
    "connection error",
    "connecterror",
    "failed to establish",
    "name or service not known",
    "nodename nor servname",
    "max retries exceeded",
    "getaddrinfo failed",
    "connection aborted",
)
_ASSERTION_MARKERS = (
    "assertionerror",
    "assertion failed",
    "assert ",
    "expected text not found",
)
_AUTHN_MARKERS = ("401", "unauthorized", "invalid credentials", "authentication failed")
_AUTHZ_MARKERS = ("403", "forbidden", "permission denied", "not authorized")

_SUMMARIES = {
    FailureType.BROWSER_NETWORK_ERROR: "Browser reported a network/environment error while loading the target",
    FailureType.INVALID_PYTEST_TARGET: "Pytest could not collect the configured test target",
    FailureType.HTTP_STATUS_MISMATCH: "HTTP response status did not match the expected status",
    FailureType.SELECTOR_NOT_FOUND: "UI element could not be located with the configured selector",
    FailureType.TIMEOUT: "Execution exceeded the configured timeout",
    FailureType.ENDPOINT_UNAVAILABLE: "Target endpoint could not be reached",
    FailureType.INTEGRATION_TARGET_UNAVAILABLE: "Integration target was unavailable or could not be invoked",
    FailureType.AUTHENTICATION_FAILURE: "Request was rejected as unauthenticated",
    FailureType.AUTHORIZATION_FAILURE: "Request was rejected as unauthorized",
    FailureType.ASSERTION_FAILURE: "Assertion did not hold during execution",
    FailureType.UNKNOWN: INSUFFICIENT_EVIDENCE_SUMMARY,
}


def _attempt_entries(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    entries = result.get("attempts_detail") or result.get("logs") or []
    return [e for e in entries if isinstance(e, dict)]


def collect_evidence(result: Dict[str, Any]) -> List[str]:
    """Collect verbatim evidence strings from a Phase 5 execution result."""
    evidence: List[str] = []
    details = result.get("details")
    if isinstance(details, str) and details.strip():
        evidence.append(details.strip())

    for entry in _attempt_entries(result):
        entry_details = entry.get("details")
        if isinstance(entry_details, str) and entry_details.strip():
            text = entry_details.strip()
            if text not in evidence:
                evidence.append(text)
    return evidence


def extract_status_codes(text: str) -> Tuple[Optional[int], Optional[int]]:
    """Extract (expected, actual) HTTP status codes from evidence text."""
    match = _EXPECTED_ACTUAL_RE.search(text)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None


def _classify(text: str, module: Optional[str]) -> Tuple[FailureType, Confidence]:
    if any(marker in text for marker in _BROWSER_NETWORK_MARKERS):
        return FailureType.BROWSER_NETWORK_ERROR, Confidence.HIGH

    if any(marker in text for marker in _INVALID_PYTEST_MARKERS):
        return FailureType.INVALID_PYTEST_TARGET, Confidence.HIGH

    expected, actual = extract_status_codes(text)
    if expected is not None and actual is not None and expected != actual:
        return FailureType.HTTP_STATUS_MISMATCH, Confidence.HIGH

    if any(marker in text for marker in _SELECTOR_MARKERS):
        return FailureType.SELECTOR_NOT_FOUND, Confidence.HIGH

    if any(marker in text for marker in _TIMEOUT_MARKERS):
        return FailureType.TIMEOUT, Confidence.HIGH

    if any(marker in text for marker in _CONNECTION_MARKERS):
        if module == "integration":
            return FailureType.INTEGRATION_TARGET_UNAVAILABLE, Confidence.HIGH
        return FailureType.ENDPOINT_UNAVAILABLE, Confidence.HIGH

    if any(marker in text for marker in _AUTHZ_MARKERS):
        return FailureType.AUTHORIZATION_FAILURE, Confidence.MEDIUM

    if any(marker in text for marker in _AUTHN_MARKERS):
        return FailureType.AUTHENTICATION_FAILURE, Confidence.MEDIUM

    if any(marker in text for marker in _ASSERTION_MARKERS):
        return FailureType.ASSERTION_FAILURE, Confidence.MEDIUM

    http_match = _HTTP_STATUS_RE.search(text)
    if http_match:
        code = int(http_match.group(1))
        if code >= 500:
            return FailureType.HTTP_STATUS_MISMATCH, Confidence.MEDIUM
        if code == 403:
            return FailureType.AUTHORIZATION_FAILURE, Confidence.MEDIUM
        if code == 401:
            return FailureType.AUTHENTICATION_FAILURE, Confidence.MEDIUM
        if code >= 400:
            return FailureType.HTTP_STATUS_MISMATCH, Confidence.LOW

    if module == "integration" and "no integration target" in text:
        return FailureType.INTEGRATION_TARGET_UNAVAILABLE, Confidence.MEDIUM

    return FailureType.UNKNOWN, Confidence.LOW


def _behaviors(
    failure_type: FailureType,
    expected: Optional[int],
    actual: Optional[int],
    evidence: List[str],
) -> Tuple[Optional[str], Optional[str]]:
    """Derive observed/expected behaviour statements from real evidence only."""
    observed = evidence[0] if evidence else None
    expected_behavior = None
    if failure_type is FailureType.HTTP_STATUS_MISMATCH:
        if expected is not None:
            expected_behavior = f"HTTP {expected}"
        if actual is not None:
            observed = f"HTTP {actual}"
    return observed, expected_behavior


def analyze_result(result: Dict[str, Any]) -> Optional[FailureAnalysis]:
    """Analyze one Phase 5 execution result.

    Returns `None` for PASS / SKIPPED results, which are out of scope.
    """
    status = str(result.get("status") or "").upper()
    if status not in FAILING_STATUSES:
        return None

    test_case_id = str(result.get("test_case_id") or "unknown")
    module = result.get("module")
    run_id = result.get("run_id")
    evidence = collect_evidence(result)
    text = " \n".join(evidence).lower()

    if not text.strip():
        return FailureAnalysis(
            test_case_id=test_case_id,
            failure_type=FailureType.UNKNOWN,
            failure_summary=INSUFFICIENT_EVIDENCE_SUMMARY,
            evidence=[],
            confidence=Confidence.LOW,
            status=status,
            module=module,
            run_id=run_id,
        )

    failure_type, confidence = _classify(text, module)
    expected: Optional[int] = None
    actual: Optional[int] = None
    if failure_type is FailureType.HTTP_STATUS_MISMATCH:
        expected, actual = extract_status_codes(text)
        if actual is None:
            http_match = _HTTP_STATUS_RE.search(text)
            actual = int(http_match.group(1)) if http_match else None

    observed_behavior, expected_behavior = _behaviors(failure_type, expected, actual, evidence)

    return FailureAnalysis(
        test_case_id=test_case_id,
        failure_type=failure_type,
        failure_summary=_SUMMARIES[failure_type],
        observed_behavior=observed_behavior,
        expected_behavior=expected_behavior,
        evidence=evidence,
        confidence=confidence,
        status=status,
        module=module,
        run_id=run_id,
    )


def analyze_results(results: List[Dict[str, Any]]) -> List[FailureAnalysis]:
    """Analyze every failing result of a Phase 5 execution report."""
    analyses: List[FailureAnalysis] = []
    for result in results or []:
        if not isinstance(result, dict):
            continue
        analysis = analyze_result(result)
        if analysis is not None:
            analyses.append(analysis)
    return analyses
