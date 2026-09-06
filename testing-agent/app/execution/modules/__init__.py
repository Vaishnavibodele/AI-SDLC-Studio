"""Execution modules package.

Each module must expose a `run(test_case)` function that returns a dict
containing at least `status` and `details` keys.
"""

from . import unit, api, ui, integration, security, regression

__all__ = ["unit", "api", "ui", "integration", "security", "regression"]
