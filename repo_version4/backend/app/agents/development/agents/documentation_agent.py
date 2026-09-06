import time
from datetime import datetime
from typing import Dict, Any
from ..development_state import DevelopmentAgentState
from ..core.prompt_manager import prompt_manager
from ..core.template_engine import template_engine
from ....services.llm_provider import get_llm

def documentation_agent_node(state: DevelopmentAgentState) -> Dict[str, Any]:
    start_time = datetime.utcnow()
    project_id = state.get("project_id")
    manifest = state.get("manifest", [])
    rejected = state.get("rejected_modules", [])
    
    time.sleep(1.0)
    
    if rejected and "documentation" not in rejected:
        print("[Documentation Agent] Skipping documentation generation (targeted revision active, module not rejected)")
        return {}
        
    print(f"[Documentation Agent] Generating README and user guides for project {project_id}...")
    
    prompt = prompt_manager.get_prompt("DocumentationAgent", "v1")
    
    paths_list = [t.get("path") for t in manifest]
    directory_structure = "\n".join([f"- {p}" for p in paths_list if p])
    
    dev_ctx = state.get("development_context", {})
    proj_title = dev_ctx.get("project_name") or "Application Project"
    tech_stack_str = ", ".join(dev_ctx.get("tech_stack", ["Python", "FastAPI", "React"]))
    
    readme_template = template_engine.render("readme_md", {
        "title": proj_title,
        "description": dev_ctx.get("srs_summary", f"Technical implementation and source code scaffold for {proj_title}."),
        "tech_stack": tech_stack_str,
        "directory_structure": directory_structure
    })

    user_msg = f"""
Approved Context: {dev_ctx}
Boilerplate Template: {readme_template}
Directory Structure: {directory_structure}
Generate the technical README markdown guide for project '{proj_title}'.
Output ONLY raw markdown content for 'README.md'.
Do not wrap in code backticks.
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
            
        documentation_output = {
            "agent": "DocumentationAgent",
            "files": ["README.md"],
            "status": "COMPLETED",
            "raw_files": {
                "README.md": code
            }
        }
        
        from ..orchestrator import record_node_execution
        record_node_execution(
            project_id=project_id,
            agent_name="DocumentationAgent",
            stage="4",
            node_name="run_documentation_agent",
            start_time=start_time,
            status="SUCCESS",
            task_id="TASK-DOC-001",
            files_generated=["README.md"]
        )
        
        return {
            "documentation_output": documentation_output
        }
    except Exception as e:
        from ..orchestrator import record_node_execution
        record_node_execution(
            project_id=project_id,
            agent_name="DocumentationAgent",
            stage="4",
            node_name="run_documentation_agent",
            start_time=start_time,
            status="FAILED",
            task_id="TASK-DOC-001",
            error_message=str(e)
        )
        raise e
