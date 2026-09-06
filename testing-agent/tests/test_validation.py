import pytest
from app.agents.input_validator import validate_input
from app.models.state import TestingState

def test_valid_input_passes():
    """
    Verify that when all required fields are present and valid,
    validation passes and there are no validation errors.
    """
    state: TestingState = {
        "project_id": "smart-building-001",
        "srs": {"title": "SRS Doc", "version": "1.0"},
        "sdd": {"architecture": "MVC"},
        "source_code": {"repository": "github.com/test/repo"},
        "api_docs": None,
        "database_schema": None,
        "test_data": None,
        "environment": None,
        "validation_status": "pending",
        "validation_errors": [],
        "context": {},
        "workflow_status": "pending",
        "human_feedback": None
    }
    
    result = validate_input(state)
    assert result["validation_status"] == "passed"
    assert len(result["validation_errors"]) == 0
    assert result["workflow_status"] == "running"

def test_missing_srs_fails():
    """
    Verify that a missing srs field results in a validation failure.
    """
    state: TestingState = {
        "project_id": "smart-building-001",
        "sdd": {"architecture": "MVC"},
        "source_code": {"repository": "github.com/test/repo"},
        # srs is missing or None
        "srs": None,
        "api_docs": None,
        "database_schema": None,
        "test_data": None,
        "environment": None,
        "validation_status": "pending",
        "validation_errors": [],
        "context": {},
        "workflow_status": "pending",
        "human_feedback": None
    }
    
    result = validate_input(state)
    assert result["validation_status"] == "failed"
    assert "srs is required" in result["validation_errors"]
    assert result["workflow_status"] == "failed"

def test_empty_required_fields_fails():
    """
    Verify that empty dictionaries or empty strings for required fields result in failure.
    """
    state: TestingState = {
        "project_id": "   ",  # empty/whitespace
        "srs": {},  # empty dict
        "sdd": {},  # empty dict
        "source_code": {},  # empty dict
        "api_docs": None,
        "database_schema": None,
        "test_data": None,
        "environment": None,
        "validation_status": "pending",
        "validation_errors": [],
        "context": {},
        "workflow_status": "pending",
        "human_feedback": None
    }
    
    result = validate_input(state)
    assert result["validation_status"] == "failed"
    assert "project_id cannot be empty" in result["validation_errors"]
    assert "srs cannot be empty" in result["validation_errors"]
    assert "sdd cannot be empty" in result["validation_errors"]
    assert "source_code cannot be empty" in result["validation_errors"]

def test_missing_optional_fields_passes():
    """
    Verify that missing optional fields (like api_docs, environment) still pass validation.
    """
    state: TestingState = {
        "project_id": "smart-building-001",
        "srs": {"features": ["F1"]},
        "sdd": {"components": ["C1"]},
        "source_code": {"files": ["main.py"]},
        # optional fields are explicitly absent
        "api_docs": None,
        "database_schema": None,
        "test_data": None,
        "environment": None,
        "validation_status": "pending",
        "validation_errors": [],
        "context": {},
        "workflow_status": "pending",
        "human_feedback": None
    }
    
    result = validate_input(state)
    assert result["validation_status"] == "passed"
    assert len(result["validation_errors"]) == 0
