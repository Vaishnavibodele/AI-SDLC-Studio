import time
import os
import sys
import tempfile
import types
import pytest
from app.execution.controller import ExecutionController
from app.execution.modules import unit as unit_module
from app.execution.modules import ui as ui_module


def test_parallel_execution(monkeypatch):
    controller = ExecutionController()
    controller.max_workers = 5

    # Make unit.run sleep to simulate I/O-bound work
    def slow_run(tc):
        time.sleep(0.25)
        return {"status": "PASS", "details": "ok"}

    monkeypatch.setattr(unit_module, "run", slow_run)

    cases = [{"test_case_id": f"T{i}", "test_type": "unit"} for i in range(5)]

    start = time.time()
    report = controller.execute_test_suite(cases)
    elapsed = time.time() - start

    # If parallel, elapsed should be less than sequential total (5 * 0.25)
    assert elapsed < 5 * 0.25
    assert report["summary"]["total"] == 5
    # run-level metadata should be present
    assert report.get("run_id") is not None
    assert report.get("started_at") is not None
    assert report.get("completed_at") is not None
    assert report.get("duration") is not None
    for r in report["results"]:
        assert r["status"] == "PASS"
        assert "duration" in r and r["duration"] >= 0


def test_retry_logic(monkeypatch):
    controller = ExecutionController()
    # Make a run that fails first two times then succeeds
    state = {"count": 0}

    def flaky(tc):
        state["count"] += 1
        if state["count"] < 3:
            return {"status": "ERROR", "details": "transient"}
        return {"status": "PASS", "details": "ok"}

    monkeypatch.setattr(unit_module, "run", flaky)

    case = {"test_case_id": "R1", "test_type": "unit", "retry": 2}
    res = controller.execute_test_case(case)
    assert res["status"] == "PASS"
    assert res["attempts"] == 3
    assert isinstance(res["logs"], list) and len(res["logs"]) == 3
    # structured attempts detail preserved
    assert isinstance(res.get("attempts_detail"), list) and len(res.get("attempts_detail")) == 3
    assert res.get("run_id") is not None


def test_execution_logs_and_duration(monkeypatch):
    controller = ExecutionController()

    def quick(tc):
        return {"status": "PASS", "details": "ok"}

    monkeypatch.setattr(unit_module, "run", quick)
    res = controller.execute_test_case({"test_case_id": "L1", "test_type": "unit"})
    assert "logs" in res
    assert isinstance(res["logs"], list)
    assert res["duration"] >= 0
    assert res.get("run_id") is not None


def test_ui_failure_captures_screenshot(monkeypatch, tmp_path):
    controller = ExecutionController()

    # Make ui.run return ERROR
    monkeypatch.setattr(ui_module, "run", lambda tc: {"status": "ERROR", "details": "boom"})

    # Create fake selenium.webdriver with Chrome.save_screenshot
    fake_selenium = types.SimpleNamespace()
    class FakeDriver:
        def __init__(self, options=None):
            self._path = None
        def get(self, url):
            self._url = url
        def save_screenshot(self, path):
            open(path, 'wb').write(b'\x89PNG')
            return True
        def quit(self):
            return None

    fake_webdriver = types.SimpleNamespace(Chrome=FakeDriver, ChromeOptions=lambda: types.SimpleNamespace(add_argument=lambda *a, **k: None))
    fake_selenium.webdriver = fake_webdriver

    sys.modules['selenium'] = fake_selenium
    sys.modules['selenium.webdriver'] = fake_webdriver

    case = {"test_case_id": "UI1", "test_type": "ui", "ui_actions": [{"action":"open","url":"http://example.local/"}]}

    res = controller.execute_test_case(case)
    # cleanup fake module
    sys.modules.pop('selenium', None)
    sys.modules.pop('selenium.webdriver', None)

    assert res["status"] == "ERROR"
    # screenshot path may be present in artifacts or screenshot
    assert (res.get("screenshot") is not None) or (len(res.get("artifacts", [])) > 0)
    if res.get("screenshot"):
        assert os.path.exists(res.get("screenshot"))
        # screenshot_meta should reflect the capture
        assert res.get("screenshot_meta") is None or isinstance(res.get("screenshot_meta"), dict)
    else:
        # check artifact path
        ap = res.get("artifacts", [])[0]["path"]
        assert os.path.exists(ap)
    # artifacts_meta should exist when artifacts present
    if res.get("artifacts"):
        assert res.get("artifacts_meta") is None or isinstance(res.get("artifacts_meta"), list)
    assert res.get("run_id") is not None