import re
import time
from datetime import datetime
from typing import Dict, Any, List
from ..development_state import DevelopmentAgentState

def api_integration_agent_node(state: DevelopmentAgentState) -> Dict[str, Any]:
    start_time = datetime.utcnow()
    project_id = state.get("project_id")
    backend_out = state.get("backend_output") or {}
    frontend_out = state.get("frontend_output") or {}
    database_out = state.get("database_output") or {}
    
    time.sleep(1.0)
    
    print(f"[API Integration Agent] Running contract validation checks for project {project_id}...")
    
    backend_files = backend_out.get("raw_files") or backend_out.get("files", {})
    frontend_files = frontend_out.get("raw_files") or frontend_out.get("files", {})
    database_schema = database_out.get("database_schema", {})
    
    # 1. Extract Backend Routes with Methods
    backend_routes = []
    for path, content in backend_files.items():
        if path.endswith(".py"):
            # Matches @app.get("/path"), @app.post("/path"), etc.
            routes = re.findall(r'@app\.(get|post|put|delete)\(\s*["\']([^"\']+)["\']', content)
            for m, r in routes:
                backend_routes.append({
                    "method": m.upper(),
                    "path": r
                })
                
    mismatches = []
    warnings = []
    
    # 2. Extract Frontend API Calls and Validate
    for path, content in frontend_files.items():
        if path.endswith(".html") or path.endswith(".js") or path.endswith(".tsx"):
            # Look for fetch('/api/path', { method: 'POST' }) or similar
            fetch_matches = re.findall(r'fetch\(\s*["\']([^"\']+)["\'](?:\s*,\s*\{\s*method:\s*["\']([^"\']+)["\'])?', content, re.IGNORECASE)
            for route, method in fetch_matches:
                method = (method or "GET").upper()
                if route.startswith("/api"):
                    match_found = False
                    method_matched = False
                    matched_backend_method = "NONE"
                    
                    for br in backend_routes:
                        br_path = br["path"]
                        # Normalize dynamic parameters (e.g. {id} or :id or UUIDs)
                        norm_br = re.sub(r'\{[^\}]+\}', '*', br_path)
                        norm_route = re.sub(r':[a-zA-Z0-9_]+', '*', route)
                        norm_route = re.sub(r'\/[0-9a-fA-F\-]{36}', '/*', norm_route)
                        
                        if norm_br == norm_route or br_path == route:
                            match_found = True
                            if br["method"] == method:
                                method_matched = True
                                break
                            else:
                                matched_backend_method = br["method"]
                                
                    if not match_found:
                        mismatches.append({
                            "endpoint": route,
                            "frontend_method": method,
                            "backend_method": "NONE",
                            "description": "Endpoint path not found in backend routes"
                        })
                    elif not method_matched:
                        mismatches.append({
                            "endpoint": route,
                            "frontend_method": method,
                            "backend_method": matched_backend_method,
                            "description": "HTTP method mismatch"
                        })
                        
    # 3. DB Schema Integration Warning check
    tables = database_schema.get("tables", [])
    if not tables:
        warnings.append("Database schema table definitions are missing or empty.")
        
    status = "FAIL" if mismatches else "PASS"
    
    api_integration_output = {
        "status": status,
        "mismatches": mismatches,
        "warnings": warnings,
        "backend_routes": [br["path"] for br in backend_routes]
    }
    
    from ..orchestrator import record_node_execution
    record_node_execution(
        project_id=project_id,
        agent_name="APIIntegrationAgent",
        stage="6",
        node_name="run_api_integration_agent",
        start_time=start_time,
        status="FAILED" if mismatches else "SUCCESS",
        task_id="TASK-API-001",
        files_generated=[]
    )
    
    validation_errors = []
    for m in mismatches:
        validation_errors.append({
            "agent": "APIIntegrationAgent",
            "stage": "6",
            "error_type": "API_CONTRACT_MISMATCH",
            "error": f"API_CONTRACT_MISMATCH: {m['description']} at {m['endpoint']} ({m['frontend_method']} vs {m['backend_method']})"
        })
        
    return {
        "api_integration_output": api_integration_output,
        "api_contract_results": api_integration_output,
        "validation_errors": validation_errors,
        "errors": validation_errors
    }
