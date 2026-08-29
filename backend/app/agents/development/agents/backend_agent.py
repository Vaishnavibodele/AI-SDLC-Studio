import time
from datetime import datetime
from typing import Dict, Any
from ..development_state import DevelopmentAgentState
from ..core.prompt_manager import prompt_manager
from ..core.template_engine import template_engine
from ..core.code_snippet_store import code_snippet_store
from ....services.llm_provider import get_llm

def backend_agent_node(state: DevelopmentAgentState) -> Dict[str, Any]:
    start_time = datetime.utcnow()
    project_id = state.get("project_id")
    rejected = state.get("rejected_modules", [])
    
    time.sleep(1.0)
    
    if rejected and "backend" not in rejected:
        print("[Backend Agent] Skipping code generation (targeted revision active, module not rejected)")
        return {}
        
    print(f"[Backend Agent] Generating backend services for project {project_id}...")
    
    prompt = prompt_manager.get_prompt("BackendAgent", "v2")
    user_msg = f"""
Approved Context: {state.get("development_context", {})}
Boilerplate Template: {template_engine.templates.get('fastapi_app')}
JWT Authentication Snippet: {code_snippet_store.get_snippet('jwt_auth')}
Generate the backend source code. 
Output ONLY raw python code for 'app/main.py'.
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
            
        backend_output = {
            "agent": "BackendDeveloperAgent",
            "files": ["app/main.py"],
            "status": "COMPLETED",
            "raw_files": {
                "app/main.py": code
            },
            "security_sensitive": True  # Auth-related controllers
        }
        
        from ..orchestrator import record_node_execution
        record_node_execution(
            project_id=project_id,
            agent_name="BackendDeveloperAgent",
            stage="4",
            node_name="run_backend_agent",
            start_time=start_time,
            status="SUCCESS",
            task_id="TASK-BE-001",
            files_generated=["app/main.py"]
        )
        
        return {
            "backend_output": backend_output
        }
    except Exception as e:
        from ..orchestrator import record_node_execution
        record_node_execution(
            project_id=project_id,
            agent_name="BackendDeveloperAgent",
            stage="4",
            node_name="run_backend_agent",
            start_time=start_time,
            status="FAILED",
            task_id="TASK-BE-001",
            error_message=str(e)
        )
        raise e
