"""Regression executor that delegates to other executors and uses change-impact metadata.

Behavior:
- If `regression_disabled` present -> SKIPPED
- If `original_test_type` present, delegate to that executor. Otherwise delegate
  based on `test_type`.
"""

from typing import Dict, Any
import logging

from app.execution.modules import unit as unit_module
from app.execution.modules import api as api_module
from app.execution.modules import ui as ui_module
from app.execution.modules import integration as integration_module
from app.execution.modules import security as security_module

logger = logging.getLogger(__name__)

DELEGATE = {
    "unit": unit_module,
    "api": api_module,
    "ui": ui_module,
    "integration": integration_module,
    "security": security_module,
}


def run(test_case: Dict[str, Any]) -> Dict[str, Any]:
    if test_case.get("regression_disabled"):
        return {"status": "SKIPPED", "details": "Regression disabled for this case"}

    target = test_case.get("original_test_type") or test_case.get("test_type")
    module = DELEGATE.get(target)
    if not module:
        return {"status": "SKIPPED", "details": f"No executor for regression target '{target}'"}

    try:
        return module.run(test_case)
    except Exception as e:
        logger.exception("Regression delegated execution failed")
        return {"status": "ERROR", "details": str(e)}
