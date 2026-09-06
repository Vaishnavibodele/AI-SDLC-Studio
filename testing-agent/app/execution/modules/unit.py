"""Unit test executor that runs pytest for a referenced test node when available.

Expectations:
- If `code_target` is provided and matches a pytest nodeid or path, run it via
  subprocess using the current Python interpreter and capture result.
- If no runnable target is present, return SKIPPED.
"""

from typing import Dict, Any
import subprocess
import sys
import time
import logging

logger = logging.getLogger(__name__)


def run(test_case: Dict[str, Any]) -> Dict[str, Any]:
    nodeid = test_case.get("code_target") or test_case.get("test_target")
    if not nodeid or not isinstance(nodeid, str):
        return {"status": "SKIPPED", "details": "No pytest nodeid/code_target provided"}

    # Run pytest for the given node id with a single test run
    cmd = [sys.executable, "-m", "pytest", nodeid, "-q", "--maxfail=1"]
    start = time.time()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        duration = time.time() - start
        out = proc.stdout + "\n" + proc.stderr
        if proc.returncode == 0:
            return {"status": "PASS", "details": out, "duration": duration}
        else:
            return {"status": "FAIL", "details": out, "duration": duration}
    except subprocess.TimeoutExpired as e:
        logger.exception("Pytest run timed out")
        return {"status": "ERROR", "details": f"Timeout: {str(e)}"}
    except Exception as e:
        logger.exception("Pytest execution failed")
        return {"status": "ERROR", "details": str(e)}
