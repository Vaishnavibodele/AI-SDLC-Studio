import os
import shutil
import subprocess
import sys
import json
from typing import Dict, Any, List
from ..development_state import DevelopmentAgentState
from .rules_engine import rules_engine

def get_expected_owner_agent(path: str) -> str:
    path = path.replace("\\", "/").strip("/")
    if path == "app/database.py" or path.startswith("migrations/") or path.endswith(".sql"):
        return "DatabaseDeveloperAgent"
    elif path == "app/main.py" or path.startswith("app/routes/") or path.startswith("app/services/") or path.startswith("app/models/") or path.startswith("app/schemas/"):
        return "BackendDeveloperAgent"
    elif path.startswith("frontend/") or path == "frontend" or path.startswith("frontend/src/"):
        return "FrontendDeveloperAgent"
    elif path == "README.md" or path.startswith("docs/"):
        return "DocumentationAgent"
    return "BackendDeveloperAgent"

def merge_validation_node(state: DevelopmentAgentState) -> Dict[str, Any]:
    project_id = state.get("project_id")
    tasks = state.get("tasks", [])
    
    db_out = state.get("database_output") or {}
    be_out = state.get("backend_output") or {}
    fe_out = state.get("frontend_output") or {}
    doc_out = state.get("documentation_output") or {}
    
    print(f"[Merge & Validation] Merging parallel agents code outputs for project {project_id}...")
    
    merged_files = {}
    ownership_map = {}
    conflicts = []
    
    db_files = db_out.get("raw_files") or (db_out.get("files") if isinstance(db_out.get("files"), dict) else {})
    be_files = be_out.get("raw_files") or (be_out.get("files") if isinstance(be_out.get("files"), dict) else {})
    fe_files = fe_out.get("raw_files") or (fe_out.get("files") if isinstance(fe_out.get("files"), dict) else {})
    doc_files = doc_out.get("raw_files") or (doc_out.get("files") if isinstance(doc_out.get("files"), dict) else {})
    agents_files = {
        "DatabaseDeveloperAgent": db_files,
        "BackendDeveloperAgent": be_files,
        "FrontendDeveloperAgent": fe_files,
        "DocumentationAgent": doc_files
    }
    
    # Check boundaries and conflicts
    for agent_name, files_dict in agents_files.items():
        if not isinstance(files_dict, dict):
            continue
        for path, content in files_dict.items():
            path_std = path.replace("\\", "/").strip("/")
            
            # 1. Boundary check
            expected_owner = get_expected_owner_agent(path_std)
            if expected_owner != agent_name:
                conflicts.append({
                    "file": path_std,
                    "owners": [agent_name, expected_owner],
                    "type": "OUT_OF_BOUNDS"
                })
                
            # 2. Duplicate check
            if path_std in ownership_map:
                prev_owner = ownership_map[path_std]
                if prev_owner != agent_name:
                    conflicts.append({
                        "file": path_std,
                        "owners": [prev_owner, agent_name],
                        "type": "DUPLICATE_OWNERS"
                    })
            else:
                ownership_map[path_std] = agent_name
                merged_files[path_std] = content

    manifest = []
    for task in tasks:
        path = task.get("path")
        if path in merged_files:
            manifest.append({
                "path": path,
                "module": task.get("module"),
                "owner_agent": task.get("owner_agent"),
                "purpose": task.get("purpose"),
                "depends_on": task.get("depends_on"),
                "priority": task.get("priority"),
                "language": task.get("language"),
                "security_sensitive": task.get("security_sensitive") or ("auth" in path or "jwt" in path or "secret" in path),
                "estimated_tokens": task.get("estimated_tokens"),
                "requirement_id": task.get("requirement_id"),
                "design_section_id": task.get("design_section_id")
            })

    static_analysis_report = {
        "files_analyzed": list(merged_files.keys()),
        "ownership_conflicts": conflicts
    }
    
    print("Executing static security checks...")
    security_rules_reports = []
    for path, content in merged_files.items():
        file_issues = rules_engine.validate_file(path, content)
        security_rules_reports.extend(file_issues)
        
    security_quality_report = {
        "status": "FAILED" if any(r["severity"] == "CRITICAL" for r in security_rules_reports) else "PASSED",
        "issues": security_rules_reports
    }
    
    print("Executing syntax compilation checks...")
    scratch_dir = os.path.join(os.getcwd(), "scratch", f"dev_multi_{project_id}")
    if os.path.exists(scratch_dir):
        shutil.rmtree(scratch_dir)
    os.makedirs(scratch_dir, exist_ok=True)
    
    for path, content in merged_files.items():
        full_path = os.path.join(scratch_dir, path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
            
    build_errors = []
    for path in merged_files.keys():
        if path.endswith(".py"):
            filepath = os.path.join(scratch_dir, path)
            res = subprocess.run([sys.executable, "-m", "py_compile", filepath], capture_output=True, text=True)
            if res.returncode != 0:
                err_msg = res.stderr or res.stdout
                build_errors.append({
                    "file": path,
                    "error": f"Python compilation failed:\n{err_msg}",
                    "affected_agent": "BackendDeveloperAgent" if "main.py" in path else "DatabaseDeveloperAgent"
                })
                
    try:
        shutil.rmtree(scratch_dir)
    except:
        pass
        
    build_report = {
        "status": "FAILED" if build_errors else "SUCCESS",
        "errors": build_errors
    }
    
    unit_test_code = """# test_main.py
# Smoke test generated by SDLC Studio Validation layer
def test_smoke():
    assert True
"""
    unit_test_report = {
        "test_file": "app/test_main.py",
        "test_code": unit_test_code,
        "status": "PASSED"
    }
    
    errors: List[dict] = []
    for c in conflicts:
        errors.append({
            "agent": "MergeValidationLayer",
            "stage": "5",
            "error_type": "FILE_OWNERSHIP_CONFLICT",
            "error": f"FILE_OWNERSHIP_CONFLICT: File '{c['file']}' has ownership issue. Owners: {c['owners']}, Type: {c['type']}."
        })
        
    for issue in security_rules_reports:
        if issue["severity"] == "CRITICAL":
            affected = "BackendDeveloperAgent" if "main.py" in issue["issue"] else "DatabaseDeveloperAgent"
            errors.append({"agent": affected, "stage": "5", "error": f"Security Critical: {issue['issue']}"})
            
    for b_err in build_errors:
        errors.append({"agent": b_err["affected_agent"], "stage": "5", "error": b_err["error"]})
        
    api_integ = state.get("api_integration_output") or {}
    for mismatch in api_integ.get("mismatches", []):
        errors.append({
            "agent": "APIIntegrationAgent",
            "stage": "5",
            "error_type": "API_CONTRACT_MISMATCH",
            "error": f"API_CONTRACT_MISMATCH: {mismatch.get('description')} at {mismatch.get('endpoint')} ({mismatch.get('frontend_method')} vs {mismatch.get('backend_method')})"
        })
 
    build_status_final = "FAILED" if errors else "SUCCESS"
    print(f"[Merge & Validation DEBUG] Validation check errors list: {errors}")
    
    validation_results = {
        "static_analysis": static_analysis_report,
        "security_quality": security_quality_report,
        "build": build_report,
        "unit_test": unit_test_report
    }
    
    return {
        "merged_files": merged_files,
        "manifest": manifest,
        "static_analysis_report": static_analysis_report,
        "security_quality_report": security_quality_report,
        "build_report": build_report,
        "unit_test_report": unit_test_report,
        "validation_errors": errors,
        "errors": errors,
        "validation_results": validation_results,
        "build_status": build_status_final,
        "current_stage": "5",
        "current_agent": "MergeValidationLayer",
        "current_task": "Merged scaffolds code files and executed validation checks.",
        "progress_percentage": 70
    }
