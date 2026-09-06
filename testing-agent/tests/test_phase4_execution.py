import pytest

from app.execution.controller import ExecutionController
from app.execution.modules import unit as unit_module
from app.execution.modules import api as api_module
from app.execution.modules import ui as ui_module
from app.execution.modules import integration as integration_module
from app.execution.modules import security as security_module
from app.execution.modules import regression as regression_module


VALID_STATUSES = {"PASS", "FAIL", "ERROR", "SKIPPED"}


def test_unit_module_behaviour_monkeypatched(monkeypatch):
    # Mock subprocess.run to simulate pytest outcomes
    class Proc:
        def __init__(self, returncode, out):
            self.returncode = returncode
            self.stdout = out
            self.stderr = ""

    def fake_run_success(cmd, capture_output, text, timeout):
        return Proc(0, "ok")

    def fake_run_fail(cmd, capture_output, text, timeout):
        return Proc(1, "failed")

    def fake_run_timeout(cmd, capture_output, text, timeout):
        raise unit_module.subprocess.TimeoutExpired(cmd, timeout)

    # Success
    monkeypatch.setattr(unit_module, "subprocess", unit_module.subprocess)
    monkeypatch.setattr(unit_module.subprocess, "run", fake_run_success)
    assert unit_module.run({"code_target": "tests/test_dummy.py::test_dummy"})["status"] == "PASS"

    # Fail
    monkeypatch.setattr(unit_module.subprocess, "run", fake_run_fail)
    assert unit_module.run({"code_target": "tests/test_dummy.py::test_dummy"})["status"] == "FAIL"

    # Timeout -> ERROR
    monkeypatch.setattr(unit_module.subprocess, "run", fake_run_timeout)
    res = unit_module.run({"code_target": "tests/test_dummy.py::test_dummy"})
    assert res["status"] == "ERROR"


def test_api_module_behaviour_mocked(monkeypatch):
    # Ensure HAS_HTTPX True and mock httpx.request
    monkeypatch.setattr(api_module, "HAS_HTTPX", True)

    class FakeResp:
        def __init__(self, status_code, text=""):
            self.status_code = status_code
            self.text = text

    def fake_request(method, url, headers=None, params=None, json=None, timeout=None):
        if "ok" in url:
            return FakeResp(200, "success")
        if "fail" in url:
            return FakeResp(400, "bad")
        raise api_module.httpx.RequestError("conn")

    # Inject fake httpx namespace
    monkeypatch.setattr(api_module, "httpx", type("H", (), {"request": staticmethod(fake_request), "RequestError": Exception}))

    # Absolute url success
    assert api_module.run({"code_target": "GET https://example.com/ok", "expected_result": ""})["status"] == "PASS"
    # Expected status mismatch -> FAIL
    assert api_module.run({"code_target": "GET https://example.com/fail", "expected_result": "status:200"})["status"] == "FAIL"
    # Request error -> ERROR
    assert api_module.run({"code_target": "GET https://example.com/error"})["status"] == "ERROR"


def test_ui_module_skipped_when_no_selenium(monkeypatch):
    # Simulate selenium not installed
    monkeypatch.setattr(ui_module, "HAS_SELENIUM", False)
    assert ui_module.run({})["status"] == "SKIPPED"


def test_ui_module_actions_with_mock_driver(monkeypatch):
    # Ensure selenium appears available
    monkeypatch.setattr(ui_module, "HAS_SELENIUM", True)

    class FakeElement:
        def click(self):
            return None

        def clear(self):
            return None

        def send_keys(self, v):
            return None

    class FakeDriver:
        def __init__(self, options=None):
            self.closed = False

        def get(self, url):
            self._url = url

        def quit(self):
            self.closed = True

    class FakeWebDriverWait:
        def __init__(self, driver, timeout):
            self.driver = driver

        def until(self, cond):
            return FakeElement()

    # Fake expected_conditions object
    class FakeEC:
        @staticmethod
        def element_to_be_clickable(arg):
            return lambda d: True

    # Provide a minimal By
    class FakeBy:
        CSS_SELECTOR = "css selector"

    # Monkeypatch selenium imports used in module
    monkeypatch.setattr(ui_module, "webdriver", type("W", (), {"ChromeOptions": lambda: type("O", (), {"add_argument": lambda self, a: None})(), "Chrome": FakeDriver}))
    monkeypatch.setattr(ui_module, "WebDriverWait", FakeWebDriverWait)
    monkeypatch.setattr(ui_module, "EC", FakeEC)
    monkeypatch.setattr(ui_module, "By", FakeBy)

    actions = [
        {"action": "open", "url": "https://example.com"},
        {"action": "click", "selector": "#btn"},
        {"action": "input", "selector": "#f", "value": "x"},
    ]

    res = ui_module.run({"ui_actions": actions})
    assert res["status"] in {"PASS", "ERROR"}


def test_integration_module_callable_and_http(monkeypatch):
    # Mock python callable invocation
    def fake_callable():
        return True

    monkeypatch.setattr(integration_module, "_call_python_target", lambda t: True)
    assert integration_module.run({"code_target": "some.module:callable"})["status"] == "PASS"

    # Mock httpx
    monkeypatch.setattr(integration_module, "HAS_HTTPX", True)
    class FakeResp:
        def __init__(self, status_code):
            self.status_code = status_code

    monkeypatch.setattr(integration_module, "httpx", type("H", (), {"get": staticmethod(lambda url, timeout: FakeResp(200))}))
    assert integration_module.run({"code_target": "http://example.com/ok"})["status"] == "PASS"


def test_security_module_behaviour():
    tc_pass = {"expected_result": "401 unauthorized"}
    tc_fail = {"description": "contains sql injection vulnerability"}
    tc_skip = {"description": "nothing to check"}

    assert security_module.run(tc_pass)["status"] == "PASS"
    assert security_module.run(tc_fail)["status"] == "FAIL"
    assert security_module.run(tc_skip)["status"] == "SKIPPED"


def test_regression_module_delegation(monkeypatch):
    # Delegate to unit module
    monkeypatch.setattr(regression_module, "DELEGATE", {"unit": unit_module})
    monkeypatch.setattr(unit_module, "run", lambda tc: {"status": "PASS"})
    assert regression_module.run({"test_type": "regression", "original_test_type": "unit"})["status"] == "PASS"


def test_execution_controller_routing_and_normalized_results(monkeypatch):
    controller = ExecutionController()

    # Monkeypatch module runs to deterministic returns
    monkeypatch.setattr(unit_module, "run", lambda tc: {"test_case_id": tc.get("test_case_id"), "status": "PASS", "details": "", "module": "unit"})
    monkeypatch.setattr(api_module, "run", lambda tc: {"test_case_id": tc.get("test_case_id"), "status": "PASS", "details": "", "module": "api"})
    monkeypatch.setattr(ui_module, "run", lambda tc: {"test_case_id": tc.get("test_case_id"), "status": "PASS", "details": "", "module": "ui"})
    monkeypatch.setattr(integration_module, "run", lambda tc: {"test_case_id": tc.get("test_case_id"), "status": "PASS", "details": "", "module": "integration"})
    monkeypatch.setattr(security_module, "run", lambda tc: {"test_case_id": tc.get("test_case_id"), "status": "PASS", "details": "", "module": "security"})
    monkeypatch.setattr(regression_module, "run", lambda tc: {"test_case_id": tc.get("test_case_id"), "status": "PASS", "details": "", "module": "regression"})

    cases = [
        {"test_case_id": "TC-U-001", "test_type": "unit"},
        {"test_case_id": "TC-A-001", "test_type": "api"},
        {"test_case_id": "TC-UI-001", "test_type": "ui"},
        {"test_case_id": "TC-I-001", "test_type": "integration"},
        {"test_case_id": "TC-S-001", "test_type": "security"},
        {"test_case_id": "TC-R-001", "test_type": "regression"},
    ]

    for c in cases:
        res = controller.execute_test_case(c)
        assert res["test_case_id"] == c["test_case_id"]
        assert res["status"] in VALID_STATUSES
        if c["test_type"] in controller.MODULE_MAP:
            assert res["module"] == c["test_type"]


def test_execution_controller_accepts_generated_ui_case(monkeypatch):
    from app.services.llm import GeminiService, TestCasesWrapper

    wrapper = GeminiService()._generate_mock_output(TestCasesWrapper)
    ui_cases = [c for c in wrapper.test_cases if c.test_type == "ui"]
    assert len(ui_cases) >= 1
    ui_case = ui_cases[0].model_dump()

    received = {}

    def fake_ui_run(tc):
        received['tc'] = tc
        return {"status": "SKIPPED", "details": "mocked"}

    monkeypatch.setattr(ui_module, "run", fake_ui_run)
    controller = ExecutionController()
    res = controller.execute_test_case(ui_case)
    assert res["test_case_id"] == ui_case.get("test_case_id")
    assert received.get('tc') is not None
    assert 'ui_actions' in received['tc']


def test_execution_controller_aggregation_and_unknown_type(monkeypatch):
    controller = ExecutionController()

    # Monkeypatch to yield specific statuses
    monkeypatch.setattr(unit_module, "run", lambda tc: {"test_case_id": tc.get("test_case_id"), "status": "PASS", "module": "unit"} if tc.get("test_case_id") == "T1" else {"test_case_id": tc.get("test_case_id"), "status": "FAIL", "module": "unit"})
    monkeypatch.setattr(api_module, "run", lambda tc: {"test_case_id": tc.get("test_case_id"), "status": "ERROR", "module": "api"})
    monkeypatch.setattr(regression_module, "run", lambda tc: {"test_case_id": tc.get("test_case_id"), "status": "SKIPPED", "module": None})

    mixed = [
        {"test_case_id": "T1", "test_type": "unit"},
        {"test_case_id": "T2", "test_type": "unit"},
        {"test_case_id": "T3", "test_type": "api"},
        {"test_case_id": "T4", "test_type": "regression"},
        {"test_case_id": "T5", "test_type": "unknown"},
    ]

    report = controller.execute_test_suite(mixed)
    results = report.get("results", [])
    summary = report.get("summary", {})

    assert summary["total"] == len(results)
    counts = {"PASS": 0, "FAIL": 0, "ERROR": 0, "SKIPPED": 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    assert summary.get("pass", 0) == counts.get("PASS", 0)
    assert summary.get("fail", 0) == counts.get("FAIL", 0)
    assert summary.get("error", 0) == counts.get("ERROR", 0)
    assert summary.get("skipped", 0) == counts.get("SKIPPED", 0)

    unknown_res = next((r for r in results if r["test_case_id"] == "T5"), None)
    assert unknown_res is not None
    assert unknown_res["status"] == "SKIPPED"
    assert unknown_res["module"] is None
