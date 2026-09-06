"""API test executor using httpx for real requests when sufficient info exists.

Behavior:
- If `code_target` is an absolute URL, use it. If it's in the form "METHOD /path",
  and `api_base_url` is present in the test_case, the request will be sent to
  api_base_url + path.
- Heuristics for expected_result: if it contains `status:XXX` will assert status,
  if contains `body_contains:TEXT` will assert substring in response body.
- If insufficient information to perform a real HTTP request, returns SKIPPED.
"""

from typing import Dict, Any
import logging
import re

logger = logging.getLogger(__name__)

try:
    import httpx
    HAS_HTTPX = True
except Exception:
    HAS_HTTPX = False


STATUS_RE = re.compile(r"status\s*:\s*(\d{3})", re.IGNORECASE)
BODY_RE = re.compile(r"body_contains\s*:\s*(.+)", re.IGNORECASE)


def _parse_method_and_path(code_target: str):
    if not code_target:
        return None, None
    parts = code_target.strip().split(maxsplit=1)
    if len(parts) == 2 and parts[0].upper() in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
        return parts[0].upper(), parts[1]
    # If it's an absolute URL without method, default to GET
    if code_target.startswith("http://") or code_target.startswith("https://"):
        return "GET", code_target
    return None, code_target


def run(test_case: Dict[str, Any]) -> Dict[str, Any]:
    if not HAS_HTTPX:
        return {"status": "SKIPPED", "details": "httpx not installed"}

    code_target = test_case.get("code_target") or ""
    api_base = test_case.get("api_base_url") or test_case.get("api_base")

    method, path = _parse_method_and_path(code_target)
    if method is None and not path:
        return {"status": "SKIPPED", "details": "No API target provided"}

    # Resolve URL
    if path and not path.startswith("http"):
        if not api_base:
            return {"status": "SKIPPED", "details": "Relative path provided but no api_base_url present"}
        url = api_base.rstrip("/") + "/" + path.lstrip("/")
    else:
        url = path

    try:
        timeout = test_case.get("timeout", 10)
        headers = test_case.get("headers") or {}
        params = test_case.get("params") or {}
        body = test_case.get("body")

        resp = httpx.request(method, url, headers=headers, params=params, json=body, timeout=timeout)

        expected = str(test_case.get("expected_result") or "")
        m = STATUS_RE.search(expected)
        if m:
            expected_code = int(m.group(1))
            if resp.status_code != expected_code:
                return {"status": "FAIL", "details": f"Expected status {expected_code}, got {resp.status_code}"}

        m2 = BODY_RE.search(expected)
        if m2:
            if m2.group(1) not in resp.text:
                return {"status": "FAIL", "details": "Expected text not found in response body"}

        if 200 <= resp.status_code < 300:
            return {"status": "PASS", "details": f"HTTP {resp.status_code}"}
        return {"status": "FAIL", "details": f"HTTP {resp.status_code}"}

    except httpx.RequestError as e:
        logger.exception("HTTP request failed")
        return {"status": "ERROR", "details": str(e)}
