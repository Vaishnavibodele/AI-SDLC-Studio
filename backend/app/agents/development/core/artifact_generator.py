import os
import json
import zipfile
import hashlib
from datetime import datetime
from typing import Dict, Any
from sqlalchemy.orm import Session
from ..development_state import DevelopmentAgentState
from ....database import SessionLocal
from ....services import project_service

def generate_folder_structure_json(merged_files: Dict[str, str]) -> Dict[str, Any]:
    tree = {}
    for path in merged_files.keys():
        parts = path.split('/')
        current = tree
        for i, part in enumerate(parts):
            if i == len(parts) - 1:
                current[part] = "file"
            else:
                if part not in current or current[part] == "file":
                    current[part] = {}
                current = current[part]
    return tree

def artifact_generator_node(state: DevelopmentAgentState, db: Session = None) -> Dict[str, Any]:
    project_id = state.get("project_id")
    merged_files = state.get("merged_files", {})
    manifest = state.get("manifest", [])
    validation_attempts = state.get("validation_attempts", 0)
    quality_score = state.get("quality_score", 90.0)
    security_score = state.get("security_score", 95.0)
    
    # Check for mock artifact fail keyword
    approved_srs = state.get("approved_srs") or {}
    if hasattr(approved_srs, "dict"):
        srs_dict = approved_srs.dict()
    elif isinstance(approved_srs, dict):
        srs_dict = approved_srs
    else:
        srs_dict = {}

    srs_summary = srs_dict.get("executive_summary", "") or srs_dict.get("project_summary", "") or ""
    project_metadata = state.get("project_metadata") or {}
    desc = srs_dict.get("summary") or project_metadata.get("description") or ""
    
    if "artifact-fail" in str(desc).lower() or "artifact-fail" in str(srs_summary).lower():
        raise Exception("Mock Artifact Generation Failure Exception")

    print(f"[Artifact Generator] Compiling version artifact packages for project {project_id}...")
    
    should_close = False
    if db is None:
        db = SessionLocal()
        should_close = True
    parent_version_num = None
    parent_contents = {}
    try:
        last_dev_ver = db.query(project_service.models.DevelopmentVersion).filter(
            project_service.models.DevelopmentVersion.project_id == project_id
        ).order_by(project_service.models.DevelopmentVersion.version_num.desc()).first()
        
        version_num = (last_dev_ver.version_num + 1) if last_dev_ver else 1
        if last_dev_ver:
            parent_version_num = last_dev_ver.version_num
            try:
                parent_manifest_payload = json.loads(last_dev_ver.raw_manifest)
                parent_contents = parent_manifest_payload.get("contents", {})
            except Exception:
                parent_contents = {}
    finally:
        if should_close:
            db.close()
        
    version_dir_name = f"{project_id}_v{version_num}"
    artifacts_root = os.path.join(os.getcwd(), "scratch", "dev_zips", version_dir_name)
    os.makedirs(artifacts_root, exist_ok=True)
    
    # Define exact 10 file paths requested (Objective Section 10)
    zip_path = os.path.join(artifacts_root, "Source.zip")
    manifest_json_path = os.path.join(artifacts_root, "Manifest.json")
    readme_path = os.path.join(artifacts_root, "README.md")
    build_report_path = os.path.join(artifacts_root, "BuildReport.json")
    validation_report_path = os.path.join(artifacts_root, "ValidationReport.json")
    api_json_path = os.path.join(artifacts_root, "API.json")
    db_schema_path = os.path.join(artifacts_root, "DatabaseSchema.sql")
    folder_structure_path = os.path.join(artifacts_root, "FolderStructure.json")
    metadata_json_path = os.path.join(artifacts_root, "GenerationMetadata.json")
    changelog_json_path = os.path.join(artifacts_root, "ChangeLog.json")
    
    # 1. Source.zip
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for path, content in merged_files.items():
            zipf.writestr(path, content)
            
    # 2. Manifest.json
    with open(manifest_json_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        
    # 3. README.md
    readme_content = merged_files.get("README.md", "# Refined Project Guide\n")
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
        
    # 4. BuildReport.json
    build_report_data = state.get("build_report", {"status": "SUCCESS", "errors": []})
    with open(build_report_path, "w", encoding="utf-8") as f:
        json.dump(build_report_data, f, indent=2)
        
    # 5. ValidationReport.json
    validation_report_data = {
        "checks_run": ["StaticCodeAnalysis", "RulesEngineCheck", "CompilationChecker", "APIContractConsistency"],
        "status": "PASSED" if not state.get("validation_errors") else "FAILED",
        "errors": state.get("validation_errors", [])
    }
    with open(validation_report_path, "w", encoding="utf-8") as f:
        json.dump(validation_report_data, f, indent=2)
        
    # 6. API.json
    openapi_schema = {
        "openapi": "3.0.0",
        "info": {
            "title": f"Project API {project_id}",
            "version": "1.0.0"
        },
        "paths": {
            "/api": {
                "get": {
                    "responses": {
                        "200": {"description": "Standard root read response"}
                    }
                }
            }
        }
    }
    # Parse routes from api contract check if available
    api_contract = state.get("api_contract") or {}
    routes_found = api_contract.get("backend_routes", [])
    for rt in routes_found:
        openapi_schema["paths"][rt] = {
            "get": {
                "responses": {"200": {"description": f"Endpoint {rt} handler"}}
            }
        }
    with open(api_json_path, "w", encoding="utf-8") as f:
        json.dump(openapi_schema, f, indent=2)
        
    # 7. DatabaseSchema.sql
    db_script_content = "-- DDL Database Initializer SQL\n"
    if "app/database.py" in merged_files:
        db_script_content += f"-- Extracted from app/database.py\n{merged_files['app/database.py']}\n"
    with open(db_schema_path, "w", encoding="utf-8") as f:
        f.write(db_script_content)
        
    # 8. FolderStructure.json
    tree_layout = generate_folder_structure_json(merged_files)
    with open(folder_structure_path, "w", encoding="utf-8") as f:
        json.dump(tree_layout, f, indent=2)
        
    # 9. GenerationMetadata.json
    metadata_data = {
        "project_id": project_id,
        "version_number": version_num,
        "timestamp": datetime.utcnow().isoformat(),
        "total_files": len(merged_files),
        "validation_attempts": validation_attempts
    }
    with open(metadata_json_path, "w", encoding="utf-8") as f:
        json.dump(metadata_data, f, indent=2)
        
    # 10. ChangeLog.json (Calculate changed files list compared to parent version)
    changed_files = []
    for path, content in merged_files.items():
        if path not in parent_contents or parent_contents[path] != content:
            changed_files.append(path)
            
    feedback = state.get("human_feedback") or {}
    reason_for_revision = feedback.get("comments", "Initial codebase scaffolds compilation.") if feedback else "Initial codebase scaffolds compilation."
    review_comments = feedback.get("comments", "") if feedback else ""
    
    changelog_data = {
        "current_version": version_num,
        "parent_version": parent_version_num,
        "changed_files": changed_files,
        "reason_for_revision": reason_for_revision,
        "review_comments": review_comments,
        "timestamp": datetime.utcnow().isoformat()
    }
    with open(changelog_json_path, "w", encoding="utf-8") as f:
        json.dump(changelog_data, f, indent=2)
        
    if not os.path.isfile(zip_path) or os.path.getsize(zip_path) == 0:
        raise RuntimeError("Source.zip was not created successfully")

    # Store absolute paths so downloads work regardless of the server launch directory.
    artifact_paths_map = {
        "source_zip": os.path.abspath(zip_path),
        "database_scripts": os.path.abspath(db_schema_path),
        "api_docs": os.path.abspath(api_json_path),
        "manifest": os.path.abspath(manifest_json_path),
        "build_report": os.path.abspath(build_report_path),
        "validation_report": os.path.abspath(validation_report_path),
        "folder_structure": os.path.abspath(folder_structure_path),
        "metadata": os.path.abspath(metadata_json_path),
        "readme": os.path.abspath(readme_path),
        "changelog": os.path.abspath(changelog_json_path)
    }
    
    return {
        "artifact_paths": artifact_paths_map,
        "current_stage": "10",
        "current_agent": "ArtifactGenerator",
        "current_task": "Scaffolds compiled and artifact reports archived.",
        "progress_percentage": 95
    }
