from typing import Dict, Any, List

class MemoryManager:
    def __init__(self):
        self.run_memories: Dict[str, Dict[str, Any]] = {}

    def save_iteration_memory(self, project_id: str, version: int, data: Dict[str, Any]):
        key = f"{project_id}_v{version}"
        self.run_memories[key] = {
            "version": version,
            "manifest": data.get("manifest", []),
            "generated_files": data.get("generated_files", {}),
            "errors": data.get("errors", []),
            "feedback": data.get("feedback", {})
        }

    def get_iteration_memory(self, project_id: str, version: int) -> Dict[str, Any]:
        key = f"{project_id}_v{version}"
        return self.run_memories.get(key, {})

    def compile_feedback_context(self, project_id: str, current_version: int) -> str:
        history_str = ""
        for v in range(1, current_version):
            mem = self.get_iteration_memory(project_id, v)
            if mem:
                fb = mem.get("feedback", {})
                if fb:
                    history_str += f"- Version {v} review decision: {fb.get('status')}. Feedback: '{fb.get('comments')}'\n"
        return history_str

memory_manager = MemoryManager()
