import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.workflow.testing_workflow import testing_workflow
from app.models.state import TestingState

client = TestClient(app)

# --- Workflow (LangGraph) Tests ---

def test_workflow_successful_execution():
    """
    Verify that a valid state runs through validation -> context_loader -> intelligence nodes -> END.
    """
    initial_state: TestingState = {
        "project_id": "proj-123",
        "srs": {"title": "Smart Building SRS", "version": "1.2", "features": ["F1", "F2"]},
        "sdd": {"architecture": "Hexagonal", "components": ["Sensor Service"]},
        "source_code": {"repository": "github.com/example/repo", "language": "Python"},
        "api_docs": {"base_url": "http://localhost:8000"},
        "database_schema": {"dialect": "PostgreSQL", "tables": ["alerts"]},
        "test_data": {"fixtures": ["test_sensors.json"]},
        "environment": {"name": "staging", "variables": {"DEBUG": "True"}},
        
        "validation_status": "pending",
        "validation_errors": [],
        "context": {},
        "workflow_status": "pending",
        "human_feedback": None,
        
        # Initialize Phase 2 fields
        "requirements": [],
        "risks": [],
        "change_impact": None,
        "coverage": None,
        "test_strategy": None,

        # Initialize Phase 3 fields
        "test_cases": [],
        "test_scenarios": [],
        "generated_test_data": [],
        "traceability": None,
        "test_design_warnings": [],
    }

    result = testing_workflow.invoke(initial_state)

    # Assert validation succeeded
    assert result["validation_status"] == "passed"
    assert len(result["validation_errors"]) == 0
    assert result["workflow_status"] == "completed"

    # Assert context loader compiled context correctly
    context = result["context"]
    assert "requirements_context" in context
    assert context["requirements_context"]["title"] == "Smart Building SRS"
    
    # Assert Phase 2 intelligence fields are populated
    assert len(result["requirements"]) > 0
    assert len(result["risks"]) > 0
    assert result["change_impact"] is not None
    assert result["coverage"] is not None
    assert result["test_strategy"] is not None

    # Assert Phase 3 test design fields are populated
    assert len(result["test_cases"]) > 0
    assert len(result["test_scenarios"]) > 0
    assert len(result["generated_test_data"]) > 0
    assert result["traceability"] is not None
    # Assert correct type validation on Phase 2 output models
    assert result["requirements"][0].id == "REQ-001"
    assert result["risks"][0].risk_id == "RSK-001"
    assert result["coverage"].coverage_percentage == 66.7
    assert result["test_strategy"].source == "ai_inference"


def test_workflow_failed_execution():
    """
    Verify that an invalid state fails validation and short-circuits directly to END (bypassing context loader & intelligence nodes).
    """
    initial_state: TestingState = {
        "project_id": "proj-123",
        "srs": {},  # empty - should fail
        "sdd": {"architecture": "MVC"},
        "source_code": {"repository": "github.com/example/repo"},
        "api_docs": None,
        "database_schema": None,
        "test_data": None,
        "environment": None,
        
        "validation_status": "pending",
        "validation_errors": [],
        "context": {},
        "workflow_status": "pending",
        "human_feedback": None,
        
        "requirements": [],
        "risks": [],
        "change_impact": None,
        "coverage": None,
        "test_strategy": None
    }

    result = testing_workflow.invoke(initial_state)

    # Assert validation failed
    assert result["validation_status"] == "failed"
    assert "srs cannot be empty" in result["validation_errors"]
    assert result["workflow_status"] == "failed"
    
    # Assert context & intelligence remain empty/None
    assert result["context"] == {}
    assert len(result["requirements"]) == 0
    assert len(result["risks"]) == 0
    assert result["change_impact"] is None


# --- FastAPI Endpoint Integration Tests ---

def test_api_start_success():
    """
    Test POST /testing/start with valid payload returns HTTP 200 and passes.
    """
    payload = {
        "project_id": "smart-building-001",
        "srs": {"title": "SRS Specs"},
        "sdd": {"architecture": "Event-driven"},
        "source_code": {"repository": "git@github.com:example/repo.git"},
        "api_docs": {"base_url": "http://localhost"},
        "database_schema": {"tables": ["devices"]},
        "test_data": {"fixtures": []},
        "environment": {"name": "production"}
    }
    
    response = client.post("/testing/start", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    assert data["project_id"] == "smart-building-001"
    assert data["validation_status"] == "passed"
    assert data["workflow_status"] == "completed"
    
    # Verify the response format matches encapsulation (intelligence field exists instead of context)
    assert "context" not in data
    assert "intelligence" in data
    assert data["intelligence"] is not None
    assert len(data["intelligence"]["requirements"]) > 0
    assert data["intelligence"]["requirements"][0]["id"] == "REQ-001"
    assert data["intelligence"]["risks"][0]["severity"] in ["High", "Medium", "Low"]
    assert data["intelligence"]["test_strategy"]["source"] == "ai_inference"

    # Verify Phase 3 test_design field
    assert "test_design" in data
    assert data["test_design"] is not None
    assert len(data["test_design"]["test_cases"]) > 0
    assert len(data["test_design"]["test_scenarios"]) > 0
    assert len(data["test_design"]["generated_test_data"]) > 0
    assert data["test_design"]["traceability"] is not None
    assert data["test_design"]["test_cases"][0]["test_case_id"] == "TC-001"


def test_api_start_validation_failure():
    """
    Test POST /testing/start with empty fields (which pass FastAPI schema check but fail Validator Node).
    """
    payload = {
        "project_id": "smart-building-001",
        "srs": {},  # Invalid - empty
        "sdd": {"architecture": "Event-driven"},
        "source_code": {}  # Invalid - empty
    }
    
    response = client.post("/testing/start", json=payload)
    assert response.status_code == 200
    
    data = response.json()
    assert data["validation_status"] == "failed"
    assert "srs cannot be empty" in data["validation_errors"]
    assert "source_code cannot be empty" in data["validation_errors"]
    assert data["workflow_status"] == "failed"
    
    # Intelligence container must be null/None on validation failure
    assert data["intelligence"] is None
    assert data["test_design"] is None


def test_api_start_malformed_request():
    """
    Test POST /testing/start with missing required field (triggers Pydantic schema validation failure / HTTP 422).
    """
    payload = {
        "project_id": "smart-building-001",
        # "srs" is missing
        "sdd": {"architecture": "Event-driven"},
        "source_code": {"repository": "git@github.com:example/repo.git"}
    }
    
    response = client.post("/testing/start", json=payload)
    assert response.status_code == 422  # Unprocessable Entity
    
    data = response.json()
    assert "detail" in data


def test_api_execute_flow(monkeypatch):
    """
    Test full execute flow: LangGraph -> ExecutionController -> aggregated results -> API response
    ExecutionController.execute_test_suite is mocked to avoid external calls.
    """
    from app.api import testing as testing_api
    # Mock ExecutionController.execute_test_suite to return a deterministic report
    def fake_execute(self, cases):
        return {
            "results": [
                {"test_case_id": "TC-001", "status": "PASS", "details": "ok", "module": "api"},
                {"test_case_id": "TC-007", "status": "SKIPPED", "details": "selenium missing", "module": "ui"},
            ],
            "summary": {"total": 2, "pass": 1, "fail": 0, "error": 0, "skipped": 1},
        }

    monkeypatch.setattr(testing_api.ExecutionController, "execute_test_suite", fake_execute)

    payload = {
        "project_id": "exec-flow-001",
        "srs": {"title": "SRS"},
        "sdd": {"architecture": "Service"},
        "source_code": {"repository": "git@github.com:example/repo.git"},
    }

    response = client.post("/testing/execute", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == "exec-flow-001"
    assert data["execution_status"] == "completed"
    assert data["execution_summary"]["total"] == 2
    assert data["execution_summary"]["passed"] == 1
    assert len(data["results"]) == 2


def test_api_execute_no_tests(monkeypatch):
    """
    If the workflow produces zero test cases, API should return execution_status='no_tests' and zero summary.
    """
    # Prepare a final_state that mimics a successful workflow but no test cases
    final_state = {
        "project_id": "no-tests-001",
        "validation_status": "passed",
        "validation_errors": [],
        "workflow_status": "completed",
        "requirements": [],
        "risks": [],
        "change_impact": None,
        "coverage": None,
        "test_strategy": None,
        "test_cases": [],
        "test_scenarios": [],
        "generated_test_data": [],
        "traceability": None,
        "test_design_warnings": [],
    }

    # Monkeypatch the workflow invoke to return our final_state
    monkeypatch.setattr(testing_workflow, "invoke", lambda s: final_state)

    payload = {
        "project_id": "no-tests-001",
        "srs": {"title": "SRS"},
        "sdd": {"architecture": "Service"},
        "source_code": {"repository": "git@github.com:example/repo.git"},
    }

    response = client.post("/testing/execute", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["project_id"] == "no-tests-001"
    assert data["execution_status"] == "no_tests"
    assert data["execution_summary"]["total"] == 0
    assert data["execution_summary"]["passed"] == 0
    assert len(data["results"]) == 0
