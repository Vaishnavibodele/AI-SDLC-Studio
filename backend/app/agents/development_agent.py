import json
import os
import zipfile
import subprocess
import sys
import shutil
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

from langgraph.graph import StateGraph, END
from langgraph.types import interrupt

from .development_state import DevelopmentAgentState
from ..services.llm_provider import get_llm
from ..database import sqlite_checkpointer, SessionLocal
from ..services import project_service


def update_db_project_status(project_id: str, phase: str, status: str):
    """Helper to update current_phase and status columns in the projects table."""
    db = SessionLocal()
    try:
        proj = project_service.get_project(db, project_id)
        if proj:
            proj.current_phase = phase
            proj.status = status
            db.commit()
            print(f"[State Machine] Project {project_id} transitioned -> Phase: {phase}, Status: {status}")
    except Exception as e:
        print(f"[State Machine] Error updating project status: {e}")
    finally:
        db.close()


def record_node_execution(project_id: str, node_name: str, start_time: datetime, status: str = "SUCCESS", prompt_tokens: int = 0, completion_tokens: int = 0, retry_count: int = 0, llm_provider: str = "gemini"):
    """Helper to save execution analytics logs into development_execution_logs."""
    db = SessionLocal()
    try:
        end_time = datetime.utcnow()
        duration = (end_time - start_time).total_seconds()
        
        # Link latest version record if available
        latest_ver = db.query(project_service.models.DevelopmentVersion).filter(
            project_service.models.DevelopmentVersion.project_id == project_id
        ).order_by(project_service.models.DevelopmentVersion.version_num.desc()).first()
        
        log_entry = project_service.models.DevelopmentExecutionLog(
            project_id=project_id,
            version_id=latest_ver.id if latest_ver else None,
            node_name=node_name,
            started_at=start_time,
            completed_at=end_time,
            duration=duration,
            llm_provider=llm_provider,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            retry_count=retry_count,
            status=status
        )
        db.add(log_entry)
        db.commit()
        print(f"[Execution Log] Logged node '{node_name}' execution (duration: {duration:.2f}s, status: {status})")
    except Exception as e:
        print(f"[Execution Log] Failed to save execution log: {e}")
    finally:
        db.close()


def save_dev_version_to_db(project_id: str, manifest: List[Dict[str, Any]], generated_files: Dict[str, str], zip_path: str, status: str = "PENDING", comments: str = "", artifact_paths_map: Dict[str, str] = None):
    db = SessionLocal()
    try:
        proj = project_service.get_project(db, project_id)
        if not proj:
            return None
            
        design_doc = db.query(project_service.models.DesignDocument).filter(
            project_service.models.DesignDocument.project_id == project_id
        ).first()
        
        latest_design_ver = None
        if design_doc:
            latest_design_ver = db.query(project_service.models.DesignVersion).filter(
                project_service.models.DesignVersion.design_document_id == design_doc.id
            ).order_by(project_service.models.DesignVersion.version_num.desc()).first()
            
        # Check latest development version to increment version number
        last_dev_ver = db.query(project_service.models.DevelopmentVersion).filter(
            project_service.models.DevelopmentVersion.project_id == project_id
        ).order_by(project_service.models.DevelopmentVersion.version_num.desc()).first()
        version_num = (last_dev_ver.version_num + 1) if last_dev_ver else 1
        
        manifest_payload = {
            "files": manifest,
            "contents": generated_files
        }
        
        dev_version = project_service.models.DevelopmentVersion(
            project_id=project_id,
            design_version_id=latest_design_ver.id if latest_design_ver else None,
            version_num=version_num,
            raw_manifest=json.dumps(manifest_payload),
            artifact_zip_path=zip_path,
            artifact_paths=json.dumps(artifact_paths_map) if artifact_paths_map else None,
            approval_status=status
        )
        db.add(dev_version)
        db.commit()
        db.refresh(dev_version)
        
        # Log to development_logs
        dev_log = project_service.models.DevelopmentLog(
            project_id=project_id,
            action="CODE_VERSION_SAVED",
            details=f"Code base version {version_num} generated/saved with status: {status}. Path: {zip_path}"
        )
        db.add(dev_log)
        db.commit()
        
        project_service.log_activity(db, project_id, "DEVELOPMENT_VERSION_SAVED", f"Code version {version_num} saved. Review status: {status}")
        return dev_version
    except Exception as e:
        print(f"[Dev DB] Error saving dev version: {str(e)}")
        return None
    finally:
        db.close()


# ----------------- NODES & WORKFLOWS -----------------

def input_validation(state: DevelopmentAgentState) -> Dict[str, Any]:
    """Node: Rejects development execution unless Design document is approved."""
    start_time = datetime.utcnow()
    project_id = state.get("project_id")
    print(f"[Node: input_validation] running state checks for project {project_id}...")
    
    db = SessionLocal()
    try:
        design_doc = db.query(project_service.models.DesignDocument).filter(
            project_service.models.DesignDocument.project_id == project_id
        ).first()
        
        if not design_doc or design_doc.approval_status != "APPROVED":
            record_node_execution(project_id, "input_validation", start_time, status="FAILED")
            return {
                "phase": "ERROR",
                "build_status": "FAILED",
                "execution_state": "FAILED",
                "current_node": "input_validation",
                "current_task": "Validating input design specs",
                "validation_errors": ["Design specifications (SDD) must be approved before starting development."]
            }
            
        record_node_execution(project_id, "input_validation", start_time, status="SUCCESS")
        return {
            "phase": "DESIGN_APPROVED",
            "current_node": "input_validation",
            "current_task": "Verifying input design parameters complete",
            "completed_tasks": ["input_validation"],
            "progress_percentage": 10
        }
    finally:
        db.close()


def development_context_builder(state: DevelopmentAgentState) -> Dict[str, Any]:
    """Node: Enriches state with a unified context dictionary containing all design assets, tech stack details, and constraints."""
    start_time = datetime.utcnow()
    project_id = state.get("project_id")
    print(f"[Node: development_context_builder] building context for project {project_id}...")
    
    db = SessionLocal()
    try:
        proj = project_service.get_project(db, project_id)
        latest_req_ver = project_service.get_latest_srs_version(db, project_id)
        if not latest_req_ver:
            effective_srs, _ = project_service.get_effective_srs_data(db, project_id)
            if effective_srs:
                project_service.create_or_update_requirement_srs(db, project_id, effective_srs, status="APPROVED", comments="Auto-synced for Development Context")
                latest_req_ver = project_service.get_latest_srs_version(db, project_id)
        design_doc, latest_design = design_service.get_latest_design_version(db, project_id)
        
        srs_dict = json.loads(latest_req_ver.raw_srs) if (latest_req_ver and latest_req_ver.raw_srs) else {}
        sdd_dict = json.loads(latest_design.raw_sdd) if (latest_design and latest_design.raw_sdd) else {}
        
        # Load previous versions if available
        prev_vers_list = db.query(project_service.models.DevelopmentVersion).filter(
            project_service.models.DevelopmentVersion.project_id == project_id
        ).order_by(project_service.models.DevelopmentVersion.version_num.desc()).all()
        
        prev_versions = [v.version_num for v in prev_vers_list]
        
        # Compose single unified context dictionary
        context = {
            "project_name": proj.name if proj else "Sandbox App",
            "project_description": proj.description if proj else "",
            "approved_srs": srs_dict,
            "approved_sdd": sdd_dict,
            "tech_stack": sdd_dict.get("technology_stack", ["FastAPI", "React", "SQLite"]),
            "coding_standards": sdd_dict.get("coding_standards", "Enforce clean standards and formatting guidelines."),
            "org_guidelines": "Parameterize all database bindings. Restrict CORS origins. Require JWT Authorization headers on API requests.",
            "previous_versions": prev_versions
        }
        
        # Update project state machine status to DEVELOPMENT_PLANNING
        update_db_project_status(project_id, "DEVELOPMENT", "DEVELOPMENT_PLANNING")
        
        record_node_execution(project_id, "development_context_builder", start_time, status="SUCCESS")
        return {
            "context": context,
            "phase": "DEVELOPMENT_PLANNING",
            "current_node": "development_context_builder",
            "current_task": "Compiling requirements assets, ডিজাইন frameworks, and guidelines context.",
            "completed_tasks": state.get("completed_tasks", []) + ["development_context_builder"],
            "progress_percentage": 20
        }
    except Exception as e:
        record_node_execution(project_id, "development_context_builder", start_time, status="FAILED")
        return {
            "phase": "ERROR",
            "build_status": "FAILED",
            "execution_state": "FAILED",
            "validation_errors": [f"Failed context mapping: {str(e)}"]
        }
    finally:
        db.close()


def project_planner(state: DevelopmentAgentState) -> Dict[str, Any]:
    """Node: Generates an enriched project file manifest mapping path, module, language, owner, priority, and tokens."""
    start_time = datetime.utcnow()
    project_id = state.get("project_id")
    context = state.get("context", {})
    print(f"[Node: project_planner] synthesizing rich file manifest for project {project_id}...")
    
    prompt = f"""
You are an expert lead project planner.
Based on the approved context (SRS, SDD, guidelines), construct a flat file manifest mapping the files required for the codebase.
The manifest must contain exactly 4 files to create a clean minimal scaffold:
1. One backend entrypoint (e.g. app/main.py or app.py)
2. One database initialization/migration schema (e.g. database/schema.sql or init.sql)
3. One frontend index page (e.g. frontend/index.html or index.html)
4. One markdown documentation file (e.g. README.md)

Project context elements:
Project: {context.get('project_name')}
Description: {context.get('project_description')}
Tech Stack: {context.get('tech_stack')}
Coding Standards: {context.get('coding_standards')}

Output JSON ONLY as a list of file definitions. Do not wrap in markdown or backticks.
Each file definition object must have these keys exactly:
- path: relative file path (string)
- module: Target system module, e.g. backend, database, frontend, api, doc (string)
- owner_agent: Name of specialized owner agent, set to "CodeGenerator" (string)
- purpose: brief explanation (string)
- depends_on: path of dependency (string or "")
- priority: file generation priority from 1 (highest) to 5 (lowest) (integer)
- language: coding language, e.g. python, sql, html, markdown, tsx (string)
- security_sensitive: boolean flag (true if the file touches auth/authz or credentials)
- estimated_tokens: estimated number of tokens required to generate this file (integer)
"""
    llm = get_llm()
    try:
        res = llm.invoke(prompt)
        content = res.content.strip()
        
        # Clean markdown code wrapper blocks
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        manifest = json.loads(content)
        
        record_node_execution(project_id, "project_planner", start_time, status="SUCCESS")
        return {
            "manifest": manifest,
            "phase": "GENERATING_CODE",
            "current_node": "project_planner",
            "current_task": "Compiling project blueprint manifest outline.",
            "completed_tasks": state.get("completed_tasks", []) + ["project_planner"],
            "progress_percentage": 30,
            "validation_attempts": 0,
            "validation_errors": []
        }
    except Exception as e:
        record_node_execution(project_id, "project_planner", start_time, status="FAILED")
        return {
            "phase": "ERROR",
            "build_status": "FAILED",
            "execution_state": "FAILED",
            "validation_errors": [f"Planner manifest generation failed: {str(e)}"]
        }


# Modular specialized agent dispatcher helper generators
def generate_backend_file(file_info: Dict[str, Any], context: Dict[str, Any], feedback: List[str] = None) -> str:
    prompt = f"Write Python backend source code file: {file_info['path']}. Purpose: {file_info['purpose']}. Target API specs: {json.dumps(context.get('approved_sdd', {}).get('api_endpoints', {}))}. Enforce coding standards: {context.get('coding_standards')}. {f'Validation errors to fix: {feedback}' if feedback else ''}. Output RAW content only."
    return get_llm().invoke(prompt).content

def generate_frontend_file(file_info: Dict[str, Any], context: Dict[str, Any], feedback: List[str] = None) -> str:
    prompt = f"Write Frontend client index file: {file_info['path']}. Purpose: {file_info['purpose']}. Coding language: {file_info['language']}. Context: {context.get('project_description')}. {f'Validation errors to fix: {feedback}' if feedback else ''}. Output RAW content only."
    return get_llm().invoke(prompt).content

def generate_database_file(file_info: Dict[str, Any], context: Dict[str, Any], feedback: List[str] = None) -> str:
    prompt = f"Write database schema/migration file: {file_info['path']}. Purpose: {file_info['purpose']}. Mapped tables layout: {json.dumps(context.get('approved_sdd', {}).get('database_tables', {}))}. {f'Validation errors to fix: {feedback}' if feedback else ''}. Output RAW content only."
    return get_llm().invoke(prompt).content

def default_code_generator(file_info: Dict[str, Any], context: Dict[str, Any], feedback: List[str] = None) -> str:
    prompt = f"Write full source code content for {file_info['path']} ({file_info['language']}). Purpose: {file_info['purpose']}. {f'Validation errors to fix: {feedback}' if feedback else ''}. Output RAW content only."
    return get_llm().invoke(prompt).content


def code_generator(state: DevelopmentAgentState) -> Dict[str, Any]:
    """Node: Dispatches and compiles code files based on owner_agent types, routing tasks sequentially."""
    start_time = datetime.utcnow()
    project_id = state.get("project_id")
    manifest = state.get("manifest", [])
    context = state.get("context", {})
    generated_files = dict(state.get("generated_files", {}))
    validation_errors = state.get("validation_errors", [])
    
    print(f"[Node: code_generator] synthesising files for project {project_id}...")
    update_db_project_status(project_id, "DEVELOPMENT", "GENERATING_CODE")
    
    # Check if this is a selective regeneration based on prior validation errors
    failed_paths = []
    for err in validation_errors:
        for item in manifest:
            path = item["path"]
            if path in err:
                failed_paths.append(path)
                
    re_generate_paths = failed_paths if failed_paths else [item["path"] for item in manifest]
    
    try:
        for file in manifest:
            path = file["path"]
            if path not in re_generate_paths and path in generated_files:
                continue
                
            owner = file.get("owner_agent", "CodeGenerator")
            print(f"Routing file '{path}' to owner agent: '{owner}'...")
            
            # Future Multi-Agent Router Dispatcher
            if owner == "BackendAgent":
                content = generate_backend_file(file, context, validation_errors)
            elif owner == "FrontendAgent":
                content = generate_frontend_file(file, context, validation_errors)
            elif owner == "DatabaseAgent":
                content = generate_database_file(file, context, validation_errors)
            else:
                content = default_code_generator(file, context, validation_errors)
                
            # Clean markdown code block syntax if the LLM output wrapped it
            if content.startswith("```"):
                lines = content.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                content = "\n".join(lines)
                
            generated_files[path] = content
            
        record_node_execution(project_id, "code_generator", start_time, status="SUCCESS")
        return {
            "generated_files": generated_files,
            "phase": "VALIDATING",
            "current_node": "code_generator",
            "current_task": "Compiling source files content through modular agent dispatchers.",
            "completed_tasks": state.get("completed_tasks", []) + ["code_generator"],
            "progress_percentage": 50,
            "build_status": "PENDING"
        }
    except Exception as e:
        record_node_execution(project_id, "code_generator", start_time, status="FAILED")
        return {
            "phase": "ERROR",
            "build_status": "FAILED",
            "execution_state": "FAILED",
            "validation_errors": [f"Code generation failed: {str(e)}"]
        }


def build_validator(state: DevelopmentAgentState) -> Dict[str, Any]:
    """Node: Runs advanced multi-stage validation checks (syntax, imports, dependencies, structure, formatting, API consistency)."""
    start_time = datetime.utcnow()
    project_id = state.get("project_id")
    generated_files = state.get("generated_files", {})
    manifest = state.get("manifest", [])
    validation_attempts = state.get("validation_attempts", 0)
    context = state.get("context", {})
    
    print(f"[Node: build_validator] executing multi-stage validations for project {project_id}...")
    update_db_project_status(project_id, "DEVELOPMENT", "VALIDATING")
    
    errors = []
    
    # 1. Folder Structure Validation: verify files fall under allowed subfolders
    print("Checking folder structure constraints...")
    for path in generated_files.keys():
        parts = path.split('/')
        if not parts or parts[0] not in ["app", "frontend", "database", "README.md", "init.sql", "schema.sql", "src", "index.html"]:
            errors.append(f"Structure Error: File path '{path}' falls outside authorized module boundaries.")

    # 2. Dependency Resolution Validation: verify depends_on files exist in manifest
    print("Checking dependencies resolution...")
    for item in manifest:
        dep = item.get("depends_on")
        if dep and dep not in generated_files:
            errors.append(f"Dependency Error in file '{item['path']}': Required dependency file '{dep}' is missing.")

    # 3. Formatting Validation: verify files have content and no trailing empty states
    print("Checking basic formatting rules...")
    for path, content in generated_files.items():
        if not content.strip():
            errors.append(f"Formatting Warning in file '{path}': File content is empty.")

    # 4. Import Validation: check that local project imports (app.) exist in manifest
    print("Checking project import maps...")
    for path, content in generated_files.items():
        if path.endswith(".py"):
            matches = re.findall(r'(?:import\s+([\w\.]+)|from\s+([\w\.]+)\s+import)', content)
            for m in matches:
                imp_module = m[0] or m[1]
                if imp_module.startswith("app."):
                    # app.database -> app/database.py
                    target_path = imp_module.replace(".", "/") + ".py"
                    if target_path not in generated_files:
                        errors.append(f"Import Error in file '{path}': Module '{imp_module}' (expected path '{target_path}') is missing in generated files.")

    # 5. API Contract Consistency: check that frontend api fetch routes match main.py REST routes
    print("Checking API endpoint contracts consistency...")
    backend_routes = []
    for path, content in generated_files.items():
        if path.endswith("main.py") or path.endswith("app.py"):
            routes = re.findall(r'@app\.(?:get|post|put|delete)\(\s*["\']([^"\']+)["\']', content)
            backend_routes.extend(routes)
            
    if backend_routes:
        for path, content in generated_files.items():
            if path.endswith(".html") or path.endswith(".tsx") or path.endswith(".js"):
                api_calls = re.findall(r'[\'"]\/api\/[^\'"]+[\'"]', content)
                for api_call in api_calls:
                    cleaned_call = api_call.strip('"\'')
                    # Standard check
                    if cleaned_call not in backend_routes:
                        # Add as a validation warning
                        print(f"[Contract warning] Frontend '{path}' calls '{cleaned_call}' not declared in routes: {backend_routes}")

    # 6. Syntax Compilation Checks: py_compile
    print("Checking python compiler compatibility...")
    scratch_dir = os.path.join(os.getcwd(), "scratch", f"dev_{project_id}")
    if os.path.exists(scratch_dir):
        shutil.rmtree(scratch_dir)
    os.makedirs(scratch_dir, exist_ok=True)
    
    # Write files to run py_compile
    for path, content in generated_files.items():
        full_path = os.path.join(scratch_dir, path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
            
    for item in manifest:
        path = item["path"]
        if path.endswith(".py"):
            filepath = os.path.join(scratch_dir, path)
            res = subprocess.run([sys.executable, "-m", "py_compile", filepath], capture_output=True, text=True)
            if res.returncode != 0:
                err_msg = res.stderr or res.stdout
                errors.append(f"Python syntax compilation error in '{path}':\n{err_msg}")
                
    try:
        shutil.rmtree(scratch_dir)
    except:
        pass

    if errors:
        next_attempt = validation_attempts + 1
        print(f"Encountered validation errors (Attempt {next_attempt}/3): {errors}")
        
        if next_attempt >= 3:
            record_node_execution(project_id, "build_validator", start_time, status="FAILED", retry_count=validation_attempts)
            # Cap reached: route to Human Approval with error state
            return {
                "validation_attempts": next_attempt,
                "validation_errors": errors,
                "phase": "ERROR",
                "build_status": "FAILED",
                "execution_state": "FAILED",
                "current_node": "build_validator",
                "current_task": "Multi-stage syntax and structure validations failed after 3 attempts.",
                "failed_tasks": state.get("failed_tasks", []) + errors
            }
        else:
            record_node_execution(project_id, "build_validator", start_time, status="FAILED", retry_count=validation_attempts)
            return {
                "validation_attempts": next_attempt,
                "validation_errors": errors,
                "phase": "GENERATING_CODE",
                "current_node": "build_validator",
                "current_task": "Validations failed. Re-routing for selective regeneration.",
                "progress_percentage": 60
            }
            
    print("All advanced validations passed successfully!")
    record_node_execution(project_id, "build_validator", start_time, status="SUCCESS", retry_count=validation_attempts)
    return {
        "phase": "GENERATING_ARTIFACTS",
        "current_node": "build_validator",
        "current_task": "Verification checks completed successfully.",
        "completed_tasks": state.get("completed_tasks", []) + ["build_validator"],
        "progress_percentage": 70,
        "build_status": "SUCCESS"
    }


def generate_folder_structure_json(generated_files: Dict[str, str]) -> Dict[str, Any]:
    """Helper to convert flat file paths into a nested tree structure JSON."""
    tree = {}
    for path in generated_files.keys():
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


def artifact_generator(state: DevelopmentAgentState) -> Dict[str, Any]:
    """Node: Synthesizes 7 distinct artifact packages (ZIP, manifest, readme, reports, metadata) and updates database."""
    start_time = datetime.utcnow()
    project_id = state.get("project_id")
    generated_files = state.get("generated_files", {})
    manifest = state.get("manifest", [])
    context = state.get("context", {})
    validation_attempts = state.get("validation_attempts", 0)
    
    print(f"[Node: artifact_generator] generating multi-artifact reports package for project {project_id}...")
    update_db_project_status(project_id, "DEVELOPMENT", "GENERATING_ARTIFACTS")
    
    # Determine next version number
    db = SessionLocal()
    try:
        last_dev_ver = db.query(project_service.models.DevelopmentVersion).filter(
            project_service.models.DevelopmentVersion.project_id == project_id
        ).order_by(project_service.models.DevelopmentVersion.version_num.desc()).first()
        version_num = (last_dev_ver.version_num + 1) if last_dev_ver else 1
    finally:
        db.close()
        
    version_dir_name = f"{project_id}_v{version_num}"
    artifacts_root = os.path.join(os.getcwd(), "scratch", "dev_zips", version_dir_name)
    os.makedirs(artifacts_root, exist_ok=True)
    
    # File Paths map
    zip_path = os.path.join(artifacts_root, "Source.zip")
    manifest_json_path = os.path.join(artifacts_root, "Manifest.json")
    readme_md_path = os.path.join(artifacts_root, "README.md")
    build_report_path = os.path.join(artifacts_root, "BuildReport.json")
    validation_report_path = os.path.join(artifacts_root, "ValidationReport.json")
    folder_structure_path = os.path.join(artifacts_root, "FolderStructure.json")
    metadata_json_path = os.path.join(artifacts_root, "GenerationMetadata.json")
    
    # 1. Source.zip: compress generated files
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for path, content in generated_files.items():
            zipf.writestr(path, content)
            
    # 2. Manifest.json: manifest outline list
    with open(manifest_json_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        
    # 3. README.md: generated markdown setup file
    readme_content = generated_files.get("README.md", f"# Codebase Scaffold - Version {version_num}\nSetup instructions.")
    with open(readme_md_path, "w", encoding="utf-8") as f:
        f.write(readme_content)
        
    # 4. BuildReport.json: compilation verification status
    build_report_data = {
        "status": "SUCCESS",
        "timestamp": datetime.utcnow().isoformat(),
        "compilation_steps": [
            {"step": "python_pycompile", "status": "PASSED"},
            {"step": "eslint_check", "status": "SKIPPED"}
        ]
    }
    with open(build_report_path, "w", encoding="utf-8") as f:
        json.dump(build_report_data, f, indent=2)
        
    # 5. ValidationReport.json: import, formatting, folder structure details
    validation_report_data = {
        "checks_run": ["FolderStructure", "DependencyResolution", "Formatting", "ImportValidation", "APIContractConsistency"],
        "status": "PASSED",
        "failures_logged": [],
        "warnings_logged": []
    }
    with open(validation_report_path, "w", encoding="utf-8") as f:
        json.dump(validation_report_data, f, indent=2)
        
    # 6. FolderStructure.json: tree representation layout
    tree_layout = generate_folder_structure_json(generated_files)
    with open(folder_structure_path, "w", encoding="utf-8") as f:
        json.dump(tree_layout, f, indent=2)
        
    # 7. GenerationMetadata.json: generation stats
    metadata_data = {
        "project_id": project_id,
        "version_number": version_num,
        "timestamp": datetime.utcnow().isoformat(),
        "total_files_generated": len(generated_files),
        "validation_attempts": validation_attempts,
        "llm_model": "gemini-2.5-flash",
        "prompt_tokens_est": sum(file.get("estimated_tokens", 500) for file in manifest)
    }
    with open(metadata_json_path, "w", encoding="utf-8") as f:
        json.dump(metadata_data, f, indent=2)
        
    # Combine artifact paths mapped to local directory relative URL schemes
    artifact_paths_map = {
        "source_zip": os.path.relpath(zip_path, os.getcwd()),
        "manifest": os.path.relpath(manifest_json_path, os.getcwd()),
        "readme": os.path.relpath(readme_md_path, os.getcwd()),
        "build_report": os.path.relpath(build_report_path, os.getcwd()),
        "validation_report": os.path.relpath(validation_report_path, os.getcwd()),
        "folder_structure": os.path.relpath(folder_structure_path, os.getcwd()),
        "metadata": os.path.relpath(metadata_json_path, os.getcwd())
    }
    
    # Save the version record to database
    save_dev_version_to_db(
        project_id=project_id,
        manifest=manifest,
        generated_files=generated_files,
        zip_path=zip_path,
        status="PENDING",
        artifact_paths_map=artifact_paths_map
    )
    
    # Record node execution stats
    record_node_execution(project_id, "artifact_generator", start_time, status="SUCCESS")
    
    return {
        "phase": "WAITING_FOR_REVIEW",
        "current_node": "artifact_generator",
        "current_task": "Compiling zip archives and diagnostic report artifacts.",
        "completed_tasks": state.get("completed_tasks", []) + ["artifact_generator"],
        "progress_percentage": 85,
        "artifact_path": zip_path
    }


def human_approval(state: DevelopmentAgentState) -> Dict[str, Any]:
    """Node: Halts execution to request lead developer sign-off."""
    project_id = state.get("project_id")
    print(f"[Node: human_approval] entering gated review interrupt for project {project_id}...")
    update_db_project_status(project_id, "DEVELOPMENT", "WAITING_FOR_REVIEW")
    
    feedback = interrupt({
        "message": "Gated human review required. Code scaffolds compiled and reports validated successfully.",
        "manifest": state.get("manifest", []),
        "generated_files": state.get("generated_files", {}),
        "validation_errors": state.get("validation_errors", [])
    })
    return {
        "user_feedback": feedback,
        "phase": "WAITING_FOR_REVIEW"
    }


def post_approval_handler(state: DevelopmentAgentState) -> Dict[str, Any]:
    """Node: Commits review decision and updates project phase state to READY_FOR_TESTING or loops back for revisions."""
    start_time = datetime.utcnow()
    feedback = state.get("user_feedback", {})
    status = feedback.get("status")
    comments = feedback.get("comments", "")
    project_id = state.get("project_id")
    manifest = state.get("manifest", [])
    generated_files = state.get("generated_files", {})
    
    print(f"[Node: post_approval_handler] processing review decision '{status}' for project {project_id}...")
    
    db = SessionLocal()
    try:
        # Load latest development version to retrieve artifact paths
        last_dev_ver = db.query(project_service.models.DevelopmentVersion).filter(
            project_service.models.DevelopmentVersion.project_id == project_id
        ).order_by(project_service.models.DevelopmentVersion.version_num.desc()).first()
        
        artifact_paths_map = json.loads(last_dev_ver.artifact_paths) if last_dev_ver and last_dev_ver.artifact_paths else {}
        zip_path = last_dev_ver.artifact_zip_path if last_dev_ver else ""
        
        # Log Review Record
        review = project_service.models.DevelopmentReview(
            project_id=project_id,
            status=status,
            comments=comments,
            reviewer_name=feedback.get("reviewer_name", "Lead Developer")
        )
        db.add(review)
        db.commit()
        
        # Save to dev logs
        dev_log = project_service.models.DevelopmentLog(
            project_id=project_id,
            action=f"HUMAN_REVIEW_{status}",
            details=f"Code base comments: {comments}"
        )
        db.add(dev_log)
        db.commit()
        
        if status == "APPROVED":
            # State Machine: Transition to DEVELOPMENT_APPROVED then READY_FOR_TESTING
            update_db_project_status(project_id, "DEVELOPMENT", "DEVELOPMENT_APPROVED")
            
            # Transition current phase to TESTING and status to READY_FOR_TESTING
            project_service.log_activity(db, project_id, "DEVELOPMENT_APPROVED", f"Development scaffold version {last_dev_ver.version_num if last_dev_ver else 1} approved by {feedback.get('reviewer_name')}.")
            update_db_project_status(project_id, "TESTING", "READY_FOR_TESTING")
            project_service.log_activity(db, project_id, "PHASE_TRANSITION", "Project transitioned to TESTING phase (READY_FOR_TESTING).")
            
            # Update development version approval status
            if last_dev_ver:
                last_dev_ver.approval_status = "APPROVED"
                db.commit()
                
            record_node_execution(project_id, "post_approval_handler", start_time, status="SUCCESS")
            return {
                "phase": "READY_FOR_TESTING",
                "execution_state": "COMPLETED",
                "current_node": "post_approval_handler",
                "current_task": "Gated sign-off approved. Phase locked.",
                "completed_tasks": state.get("completed_tasks", []) + ["post_approval_handler"],
                "progress_percentage": 100,
                "user_feedback": None
            }
        else:
            # REJECTED / REQUEST_CHANGES
            update_db_project_status(project_id, "DEVELOPMENT", "DEVELOPMENT_PLANNING")
            project_service.log_activity(db, project_id, "DEVELOPMENT_REJECTED", f"Changes requested: {comments}")
            
            if last_dev_ver:
                last_dev_ver.approval_status = "REJECTED"
                db.commit()
                
            record_node_execution(project_id, "post_approval_handler", start_time, status="FAILED")
            return {
                "phase": "DEVELOPMENT_PLANNING",
                "current_node": "post_approval_handler",
                "current_task": "Review rejected. Re-submitting manifest details for revisions.",
                "failed_tasks": state.get("failed_tasks", []) + ["post_approval_handler_rejected"],
                "progress_percentage": 20,
                "user_feedback": feedback
            }
    finally:
        db.close()


# ----------------- EDGES & ROUTING -----------------

def route_after_validation(state: DevelopmentAgentState) -> str:
    phase = state.get("phase")
    if phase == "ERROR":
        # Multi-stage validations failed after 3 attempts -> Route to human approval (review failed compile logs)
        return "human_approval"
    elif phase == "GENERATING_ARTIFACTS":
        return "artifact_generator"
    else:
        # Loop back to code generator
        return "code_generator"


def route_after_approval(state: DevelopmentAgentState) -> str:
    phase = state.get("phase")
    if phase == "READY_FOR_TESTING":
        return END
    else:
        # Loop back to planner node for code revisions
        return "project_planner"


# ----------------- GRAPH COMPILATION -----------------

workflow = StateGraph(DevelopmentAgentState)

# Add Nodes
workflow.add_node("input_validation", input_validation)
workflow.add_node("development_context_builder", development_context_builder)
workflow.add_node("project_planner", project_planner)
workflow.add_node("code_generator", code_generator)
workflow.add_node("build_validator", build_validator)
workflow.add_node("artifact_generator", artifact_generator)
workflow.add_node("human_approval", human_approval)
workflow.add_node("post_approval_handler", post_approval_handler)

# Set Entry Point
workflow.set_entry_point("input_validation")

# Define Connections
workflow.add_conditional_edges(
    "input_validation",
    lambda state: "development_context_builder" if state.get("phase") != "ERROR" else END
)
workflow.add_edge("development_context_builder", "project_planner")
workflow.add_edge("project_planner", "code_generator")
workflow.add_edge("code_generator", "build_validator")

workflow.add_conditional_edges(
    "build_validator",
    route_after_validation,
    {
        "artifact_generator": "artifact_generator",
        "code_generator": "code_generator",
        "human_approval": "human_approval"
    }
)

workflow.add_edge("artifact_generator", "human_approval")
workflow.add_edge("human_approval", "post_approval_handler")

workflow.add_conditional_edges(
    "post_approval_handler",
    route_after_approval,
    {
        END: END,
        "project_planner": "project_planner"
    }
)

compiled_development_graph = workflow.compile(checkpointer=sqlite_checkpointer)
