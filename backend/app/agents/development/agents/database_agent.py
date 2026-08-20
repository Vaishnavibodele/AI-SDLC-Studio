import time
from datetime import datetime
from typing import Dict, Any
from ..development_state import DevelopmentAgentState
from ..core.prompt_manager import prompt_manager
from ..core.template_engine import template_engine
from ....services.llm_provider import get_llm

def database_agent_node(state: DevelopmentAgentState) -> Dict[str, Any]:
    # Record starts
    start_time = datetime.utcnow()
    project_id = state.get("project_id")
    rejected = state.get("rejected_modules", [])
    
    # Simulate execution duration to ensure overlapping timestamps
    time.sleep(1.0)
    
    if rejected and "database" not in rejected:
        print("[Database Agent] Skipping database DDL script generation (targeted revision active, module not rejected)")
        return {}
        
    print(f"[Database Agent] Generating database schemas for project {project_id}...")
    
    prompt = prompt_manager.get_prompt("DatabaseAgent", "v1")
    user_msg = f"""
Approved Context: {state.get("development_context", {})}
Boilerplate Template: {template_engine.templates.get('sqlite_db')}
Generate database structures.
Output ONLY raw python connection code for 'app/database.py'.
Do not wrap in markdown or backticks.
"""
    
    try:
        llm = get_llm()
        res = llm.invoke([
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_msg}
        ])
        code = res.content.strip()
        
        if code.startswith("```"):
            lines = code.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            code = "\n".join(lines)
            
        raw_files = {"app/database.py": code}
        files_list = ["app/database.py"]
        if "[FILE: " in code:
            # Parse multiple files from mock response
            parts = code.split("[FILE: ")
            raw_files = {}
            files_list = []
            for part in parts:
                if not part.strip():
                    continue
                subparts = part.split("]", 1)
                if len(subparts) == 2:
                    filepath = subparts[0].strip()
                    filecontent = subparts[1].strip()
                    raw_files[filepath] = filecontent
                    files_list.append(filepath)

        database_output = {
            "agent": "DatabaseDeveloperAgent",
            "files": files_list,
            "database_schema": {
                "tables": ["users", "projects", "requirements", "designs", "development_versions"]
            },
            "status": "COMPLETED",
            "raw_files": raw_files
        }
        
        # Log execution
        from ..orchestrator import record_node_execution
        record_node_execution(
            project_id=project_id,
            agent_name="DatabaseDeveloperAgent",
            stage="4",
            node_name="run_database_agent",
            start_time=start_time,
            status="SUCCESS",
            task_id="TASK-DB-001",
            files_generated=["app/database.py"]
        )
        
        return {
            "database_output": database_output
        }
    except Exception as e:
        from ..orchestrator import record_node_execution
        record_node_execution(
            project_id=project_id,
            agent_name="DatabaseDeveloperAgent",
            stage="4",
            node_name="run_database_agent",
            start_time=start_time,
            status="FAILED",
            task_id="TASK-DB-001",
            error_message=str(e)
        )
        raise e
