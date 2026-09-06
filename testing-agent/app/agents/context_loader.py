import logging
from typing import Dict, Any
from app.models.state import TestingState

logger = logging.getLogger(__name__)

def load_context(state: TestingState) -> Dict[str, Any]:
    """
    Normalizes the input artifacts into a structured testing context
    and updates the state context and workflow status.
    """
    logger.info("Executing Context Loader Agent Node")

    srs = state.get("srs") or {}
    sdd = state.get("sdd") or {}
    source_code = state.get("source_code") or {}
    api_docs = state.get("api_docs")
    database_schema = state.get("database_schema")
    test_data = state.get("test_data")
    environment = state.get("environment")

    # Construct the Requirements Context
    requirements_context = {
        "title": srs.get("title") or "Unnamed Requirements Spec",
        "version": srs.get("version") or "1.0.0",
        "features": srs.get("features") or [],
        "raw_srs": srs
    }

    # Construct the Design Context
    design_context = {
        "architecture_pattern": sdd.get("architecture") or sdd.get("pattern") or "Unspecified",
        "components": sdd.get("components") or [],
        "interfaces": sdd.get("interfaces") or [],
        "raw_sdd": sdd
    }

    # Construct the Code Context
    code_context = {
        "repository": source_code.get("repository") or "Local / Unknown",
        "branch": source_code.get("branch") or "main",
        "language": source_code.get("language") or "Python",
        "file_structure": source_code.get("files") or [],
        "raw_source_code": source_code
    }

    # Construct API Context if available
    api_context = {}
    if api_docs is not None:
        api_context = {
            "base_url": api_docs.get("base_url") or "",
            "endpoints": api_docs.get("endpoints") or [],
            "raw_api_docs": api_docs
        }

    # Construct Database Context if available
    database_context = {}
    if database_schema is not None:
        database_context = {
            "dialect": database_schema.get("dialect") or "SQL",
            "tables": database_schema.get("tables") or [],
            "raw_database_schema": database_schema
        }

    # Construct Test Data Context if available
    test_data_context = {}
    if test_data is not None:
        test_data_context = {
            "fixtures": test_data.get("fixtures") or [],
            "raw_test_data": test_data
        }

    # Construct Environment Context if available
    environment_context = {}
    if environment is not None:
        environment_context = {
            "env_name": environment.get("name") or "dev",
            "variables": environment.get("variables") or {},
            "raw_environment": environment
        }

    # Assemble structured testing context
    structured_context = {
        "requirements_context": requirements_context,
        "design_context": design_context,
        "code_context": code_context,
        "api_context": api_context,
        "database_context": database_context,
        "test_data_context": test_data_context,
        "environment_context": environment_context
    }

    logger.info("Structured testing context constructed successfully")

    return {
        "context": structured_context,
        "workflow_status": "completed"
    }
