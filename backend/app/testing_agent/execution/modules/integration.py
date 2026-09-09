"""Integration executor that can call a local callable or perform HTTP checks.

If `code_target` is a Python callable path (module:callable), it will be
imported and invoked. If it's an HTTP endpoint, it will attempt an httpx call
if available. Otherwise SKIPPED.
"""

from typing import Dict, Any
import logging
import importlib

logger = logging.getLogger(__name__)

try:
    import httpx
    HAS_HTTPX = True
except Exception:
    HAS_HTTPX = False


def _call_python_target(target: str):
    # target like package.module:callable
    if ":" not in target:
        raise ValueError("Invalid python callable target")
    mod_name, call_name = target.split(":", 1)
    mod = importlib.import_module(mod_name)
    fn = getattr(mod, call_name)
    return fn()


def run(test_case: Dict[str, Any]) -> Dict[str, Any]:
    target = test_case.get("code_target") or ""
    if not target:
        return {"status": "SKIPPED", "details": "No integration target provided"}

    # If it's a python callable
    if ":" in target:
        try:
            res = _call_python_target(target)
            return {"status": "PASS" if res else "FAIL", "details": "Callable returned truthy"}
        except Exception as e:
            logger.exception("Integration callable failed")
            return {"status": "ERROR", "details": str(e)}

    # If it's an HTTP endpoint
    if target.startswith("http") and HAS_HTTPX:
        try:
            resp = httpx.get(target, timeout=10)
            if 200 <= resp.status_code < 300:
                return {"status": "PASS", "details": f"HTTP {resp.status_code}"}
            return {"status": "FAIL", "details": f"HTTP {resp.status_code}"}
        except Exception as e:
            logger.exception("Integration HTTP check failed")
            return {"status": "ERROR", "details": str(e)}

    return {"status": "SKIPPED", "details": "Unsupported integration target or missing httpx"}
