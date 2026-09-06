"""Phase 4: Execution controller package.

This package provides a single testing agent / execution controller that can
dispatch test case specifications to simple execution modules (unit, api, ui,
integration, security, regression). Modules are intentionally lightweight and
deterministic to allow local validation and to avoid external runtime
dependencies.
"""

from .controller import ExecutionController

__all__ = ["ExecutionController"]
