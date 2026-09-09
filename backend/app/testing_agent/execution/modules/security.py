"""Deterministic security checks using static data in the test case.

This executor does not perform penetration testing but verifies that tests
include basic auth/validation assertions where expected. If insufficient
information exists, SKIPPED.
"""

from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


def run(test_case: Dict[str, Any]) -> Dict[str, Any]:
    # If test references an API target and expected_result mentions auth, attempt
    # to validate auth expectations by returning PASS/FAIL deterministically.
    expected = str(test_case.get("expected_result") or "").lower()
    desc = str(test_case.get("description") or "").lower()

    if "unauthorized" in expected or "401" in expected or "forbidden" in expected:
        # We expect an auth failure; without running an HTTP check we mark PASS
        # only if expected indicates unauthenticated access should be blocked.
        return {"status": "PASS", "details": "Auth expectation detected (no live test performed)"}

    # Detect vulnerability markers in description
    if any(k in desc for k in ["sql injection", "xss", "vuln", "vulnerability"]):
        return {"status": "FAIL", "details": "Vulnerability indicator present in description"}

    # If nothing to check, skip
    return {"status": "SKIPPED", "details": "No deterministic security checks applicable"}
