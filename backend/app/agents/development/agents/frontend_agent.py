import time
from datetime import datetime
from typing import Dict, Any
from ..development_state import DevelopmentAgentState
from ..core.prompt_manager import prompt_manager
from ..core.template_engine import template_engine
from ....services.llm_provider import get_llm

def frontend_agent_node(state: DevelopmentAgentState) -> Dict[str, Any]:
    start_time = datetime.utcnow()
    project_id = state.get("project_id")
    rejected = state.get("rejected_modules", [])
    
    time.sleep(1.0)
    
    if rejected and "frontend" not in rejected:
        print("[Frontend Agent] Skipping code generation (targeted revision active, module not rejected)")
        return {}
        
    print(f"[Frontend Agent] Generating UI components for project {project_id}...")
    
    prompt = prompt_manager.get_prompt("FrontendAgent", "v1")
    user_msg = f"""
Approved Context: {state.get("development_context", {})}
Boilerplate Template: {template_engine.templates.get('html_entry')}
Generate the frontend index layout.
Output ONLY raw html content for 'frontend/index.html'.
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
            
        frontend_output = {
            "agent": "FrontendDeveloperAgent",
            "files": ["frontend/index.html"],
            "status": "COMPLETED",
            "raw_files": {
                "frontend/index.html": code
            }
        }
        
        from ..orchestrator import record_node_execution
        record_node_execution(
            project_id=project_id,
            agent_name="FrontendDeveloperAgent",
            stage="4",
            node_name="run_frontend_agent",
            start_time=start_time,
            status="SUCCESS",
            task_id="TASK-FE-001",
            files_generated=["frontend/index.html"]
        )
        
        return {
            "frontend_output": frontend_output
        }
    except Exception as e:
        from ..orchestrator import record_node_execution
        record_node_execution(
            project_id=project_id,
            agent_name="FrontendDeveloperAgent",
            stage="4",
            node_name="run_frontend_agent",
            start_time=start_time,
            status="FAILED",
            task_id="TASK-FE-001",
            error_message=str(e)
        )
        raise e
