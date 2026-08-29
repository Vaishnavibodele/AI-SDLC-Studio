import json
from typing import Dict, Any, List
from .development_state import DevelopmentAgentState
from ...services.llm_provider import get_llm

def planning_engine_node(state: DevelopmentAgentState) -> Dict[str, Any]:
    project_id = state.get("project_id")
    context = state.get("development_context", {})
    
    # Check for mock planning fail keyword
    approved_srs = state.get("approved_srs") or {}
    srs_summary = approved_srs.get("executive_summary", "")
    project_metadata = state.get("project_metadata") or {}
    desc = approved_srs.get("summary") or project_metadata.get("description") or ""
    if "planning-fail" in desc.lower() or "planning-fail" in srs_summary.lower():
        raise Exception("Mock Planning Engine Failure Exception")

    print(f"[Planning Engine] Running plan analysis for project {project_id}...")
    
    # 1. Project Analyzer & Module Planner: define standard structured tasks traced to requirements/design specs
    tasks = [
        {
            "task_id": "TASK-DB-001",
            "path": "app/database.py",
            "module": "database",
            "owner_agent": "DatabaseDeveloperAgent",
            "purpose": "Initialize SQLite/Postgres connection pooling and SQLAlchemy tables definitions.",
            "depends_on": "",
            "priority": 1,
            "language": "python",
            "security_sensitive": False,
            "estimated_tokens": 600,
            "requirement_id": "REQ-DATA-001",
            "design_section_id": "SEC-DB-DESIGN"
        },
        {
            "task_id": "TASK-BE-002",
            "path": "app/main.py",
            "module": "backend",
            "owner_agent": "BackendDeveloperAgent",
            "purpose": "Construct FastAPI endpoints, JWT security middlewares, and validation error handlers.",
            "depends_on": "app/database.py",
            "priority": 2,
            "language": "python",
            "security_sensitive": True,
            "estimated_tokens": 1200,
            "requirement_id": "REQ-AUTH-002",
            "design_section_id": "SEC-API-ROUTING"
        },
        {
            "task_id": "TASK-FE-003",
            "path": "frontend/index.html",
            "module": "frontend",
            "owner_agent": "FrontendDeveloperAgent",
            "purpose": "Build React app client entry point index layout linked to backend API controllers.",
            "depends_on": "app/main.py",
            "priority": 3,
            "language": "html",
            "security_sensitive": False,
            "estimated_tokens": 500,
            "requirement_id": "REQ-UI-003",
            "design_section_id": "SEC-UI-LAYOUT"
        },
        {
            "task_id": "TASK-INTEG-004",
            "path": "api_integration.json",
            "module": "api",
            "owner_agent": "APIIntegrationAgent",
            "purpose": "Validate and map integration endpoint models consistency between frontend and backend.",
            "depends_on": "app/main.py",
            "priority": 4,
            "language": "json",
            "security_sensitive": False,
            "estimated_tokens": 300,
            "requirement_id": "REQ-INTEG-004",
            "design_section_id": "SEC-CONTRACT-VERIFY"
        },
        {
            "task_id": "TASK-DOC-005",
            "path": "README.md",
            "module": "doc",
            "owner_agent": "DocumentationAgent",
            "purpose": "Compose setup guidelines, run requirements, and installation procedures.",
            "depends_on": "frontend/index.html",
            "priority": 5,
            "language": "markdown",
            "security_sensitive": False,
            "estimated_tokens": 400,
            "requirement_id": "REQ-DOC-005",
            "design_section_id": "SEC-INSTALLATION"
        }
    ]
    
    # 2. Dependency Analyzer: build task dependencies dictionary
    task_dependencies = {
        "DatabaseDeveloperAgent": [],
        "BackendDeveloperAgent": ["DatabaseDeveloperAgent"],
        "FrontendDeveloperAgent": ["BackendDeveloperAgent"],
        "APIIntegrationAgent": ["BackendDeveloperAgent", "FrontendDeveloperAgent"],
        "DocumentationAgent": ["FrontendDeveloperAgent"]
    }
    
    plan = {
        "modules": ["database", "backend", "frontend", "api", "doc"],
        "dependency_graph": task_dependencies,
        "traceability_map": {t["task_id"]: {"req": t["requirement_id"], "design": t["design_section_id"]} for t in tasks}
    }
    
    return {
        "plan": plan,
        "tasks": tasks,
        "task_dependencies": task_dependencies,
        "current_stage": "3",
        "current_agent": "PlanningEngine",
        "current_task": "Project planning and module dependencies analyzed.",
        "progress_percentage": 30
    }
