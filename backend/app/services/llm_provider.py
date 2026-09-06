import os
import re
import json
from dotenv import load_dotenv
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration
from pydantic import Field
from typing import Any, List, Optional, Union

load_dotenv()

def get_content_text(content: Any) -> str:
    """Safely extracts plain string from LLM response or content object/list."""
    if hasattr(content, "content"):
        content = content.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "".join(parts)
    import re

def _extract_dynamic_project_name(text: str) -> str:
    if not text:
        return "Custom Application"
    m = re.search(r'\b(an?|the)\s+([a-z0-9\s\-]+?\s+(platform|system|application|portal|app|tool|service|dashboard|hub|manager))\b', text, re.IGNORECASE)
    if m:
        val = m.group(2).strip().title()
        if len(val) > 3 and val.lower() not in ["sandbox app", "none", "null", "custom application"]:
            return val
    m2 = re.search(r'\b([A-Z][a-zA-Z0-9\s\-]{2,30}\s+(Platform|System|Application|Portal|App|Tool|Service))\b', text)
    if m2:
        val = m2.group(1).strip()
        if val.lower() not in ["sandbox app", "custom application"]:
            return val
    words = [w for w in re.split(r'\W+', text) if w.lower() not in ['an', 'a', 'the', 'where', 'whereby', 'which', 'that', 'can', 'and', 'or', 'for', 'to', 'in', 'on', 'at', 'with', 'by']]
    if words:
        cand = ' '.join(words[:2]).strip().title()
        if not any(k in cand.lower() for k in ['system', 'platform', 'application', 'portal', 'app']):
            cand += ' System'
        return cand
    return "Custom Application"

def _extract_dynamic_actors_from_text(text: str) -> List[str]:
    if not text:
        return ["User"]
    actors = []
    matches = re.findall(r'\b([a-zA-Z]+s?)\s+(?:can|shall|should|may|able to)\b', text, re.IGNORECASE)
    for w in matches:
        w_lower = w.lower()
        if w_lower not in ['system', 'application', 'platform', 'which', 'that', 'where', 'it', 'they', 'you', 'we', 'requirement', 'requirements', 'user', 'users']:
            actor = w.capitalize()
            actors.append(actor)
    return list(dict.fromkeys(actors)) if actors else ["User"]

def _extract_dynamic_requirements_from_text(text: str) -> List[str]:
    if not text:
        return ["System shall fulfill user provided requirements."]
        
    lines = text.split('\n')
    valid_lines = [
        l.strip() for l in lines 
        if l.strip() 
        and not any(l.strip().lower().startswith(prefix) for prefix in ['requirement memory', 'critical', 'you are', 'extract', 'return', 'do not', 'schema', 'system prompt', '{', '}', '[', ']'])
        and not any(keyword in l.lower() for keyword in ['senior business analyst', 'canonical projectdocument', 'compiled srs'])
    ]
    clean_text = ' '.join(valid_lines)
    
    sentences = [s.strip() for s in re.split(r'[.;!\n]', clean_text) if s.strip()]
    reqs = []
    
    for s in sentences:
        sub_parts = [p.strip() for p in re.split(r'\bwhere\b', s, flags=re.IGNORECASE) if p.strip()]
        for sub in sub_parts:
            actor_clauses = re.split(r'\b(?=[a-zA-Z]+s?\s+can\b)', sub, flags=re.IGNORECASE)
            for ac in actor_clauses:
                ac_str = ac.strip()
                if not ac_str: continue
                
                m = re.search(r'\b([a-zA-Z]+s?)\s+can\s+(.*)', ac_str, re.IGNORECASE)
                if m:
                    actor_word = m.group(1).capitalize()
                    verbs_text = m.group(2).strip()
                    verbs_text = re.sub(r'^(?:and|or|\,)\s*', '', verbs_text, flags=re.IGNORECASE)
                    
                    v_words = verbs_text.split()
                    shared_obj = v_words[-1] if (len(v_words) > 1 and v_words[-1].lower() not in ['and', 'or', 'can']) else ''
                    
                    verb_match = re.match(r'^(manage|search|view|purchase|add|update|remove|select|make|cancel|create|delete|process|edit|build|track|stream|annotate)\s+(.*)', verbs_text, re.IGNORECASE)
                    if verb_match:
                        verb = verb_match.group(1).lower()
                        rest = verb_match.group(2).strip()
                        items = [i.strip() for i in re.split(r'\b(?:and|or)\b|,', rest) if i.strip()]

                        for item in items:
                            item_clean = re.sub(r'^(?:and|or)\s*', '', item, flags=re.IGNORECASE).strip()
                            if not item_clean: continue
                            if re.match(r'^(manage|search|view|purchase|add|update|remove|select|make|cancel|create|delete|process|edit|build|track|stream|annotate)\b', item_clean, re.IGNORECASE):
                                stmt = f'{actor_word} can {item_clean}.'
                            else:
                                if len(item_clean.split()) == 1:
                                    if item_clean.lower() in ['add', 'update', 'remove', 'edit', 'delete', 'create', 'view', 'select', 'manage']:
                                        stmt = f'{actor_word} can {item_clean} {shared_obj}.'
                                    else:
                                        stmt = f'{actor_word} can {verb} {item_clean}.'
                                else:
                                    stmt = f'{actor_word} can {verb} {item_clean}.'
                            stmt = re.sub(r'\.\.+', '.', stmt)
                            if stmt not in reqs and len(stmt) > 8:
                                reqs.append(stmt)
                    else:
                        actions = [a.strip() for a in re.split(r'\b(?:and|or)\b|,', verbs_text) if a.strip()]
                        for act in actions:
                            act_clean = re.sub(r'^(?:and|or)\s*', '', act, flags=re.IGNORECASE).strip()
                            if not act_clean: continue
                            if len(act_clean.split()) == 1 and act_clean.lower() in ['add', 'update', 'remove', 'edit', 'delete', 'create', 'view', 'select', 'manage']:
                                stmt = f'{actor_word} can {act_clean} {shared_obj}.'
                            else:
                                stmt = f'{actor_word} can {act_clean}.'
                            stmt = re.sub(r'\.\.+', '.', stmt)
                            if stmt not in reqs and len(stmt) > 8:
                                reqs.append(stmt)
                else:
                    cleaned_s = ac_str.strip()
                    if (cleaned_s 
                        and len(cleaned_s) > 10 
                        and not any(k in cleaned_s.lower() for k in ['you are', 'system prompt', 'raw json', 'senior business analyst', 'memory collected'])):
                        if not cleaned_s.endswith('.'):
                            cleaned_s += '.'
                        if cleaned_s not in reqs:
                            reqs.append(cleaned_s)
                            
    return reqs if reqs else ["System shall fulfill user provided requirements."]

class MockChatModel(BaseChatModel):
    """A mock chat model that mimics requirement elicitation and outputs valid JSON when requested."""
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        last_user_msg = ""
        system_prompt = ""
        
        for m in messages:
            m_type = getattr(m, "type", "")
            m_role = getattr(m, "role", "") if hasattr(m, "role") else ""
            m_content = getattr(m, "content", "")
            
            print(f"[MockModel Debug] Msg type: {m_type}, role: {m_role}, content length: {len(str(m_content))}")
            
            if m_type == "system" or m_role == "system":
                system_prompt = m_content
            elif m_type == "user" or m_type == "human" or m_role == "user":
                last_user_msg = m_content

        import re

        def extract_project_name() -> str:
            raw_text = " ".join(str(getattr(m, "content", "")) for m in messages) + " " + str(system_prompt) + " " + str(last_user_msg)
            # 1. Search for project_name field in dict/json
            m = re.search(r"['\"]project_name['\"]\s*:\s*['\"]([^'\"]+)['\"]", raw_text, re.IGNORECASE)
            if m:
                val = m.group(1).strip()
                if val and val.lower() not in ["sandbox app", "none", "null", "e-commerce app store", "project"]:
                    return val
            # 2. Search for project '{title}' or Project: {title}
            m_proj = re.search(r"project\s*['\"]([^'\"]+)['\"]", raw_text, re.IGNORECASE)
            if m_proj:
                val = m_proj.group(1).strip()
                if val and val.lower() not in ["sandbox app", "none", "null", "e-commerce app store", "project"]:
                    return val
            m_cover = re.search(r"Project:\s*([^\n\r,]+)", raw_text, re.IGNORECASE)
            if m_cover:
                val = m_cover.group(1).strip()
                if val and val.lower() not in ["sandbox app", "none", "null", "e-commerce app store", "project"]:
                    return val
            # 3. Infer from user message keywords
            prompt_lower = raw_text.lower()
            if "delivery" in prompt_lower or "food" in prompt_lower:
                return "Food Delivery Platform"
            elif "ecommerce" in prompt_lower or "shop" in prompt_lower or "store" in prompt_lower:
                return "Online E-Commerce Platform"
            elif "book" in prompt_lower:
                return "Online Bookstore System"
            elif "hospital" in prompt_lower or "clinic" in prompt_lower:
                return "Healthcare Management System"
            elif "school" in prompt_lower or "student" in prompt_lower:
                return "Student Information Portal"
            elif "task" in prompt_lower or "todo" in prompt_lower:
                return "Task Management Application"
            elif "chat" in prompt_lower or "messaging" in prompt_lower:
                return "Realtime Messaging Application"
            return "Custom Application"

        p_name = extract_project_name()

        is_srs_compiler = "compile" in system_prompt.lower() and "srs" in system_prompt.lower()
        is_memory_updater = "update the structured requirement memory" in system_prompt.lower() or "state manager" in system_prompt.lower()
        is_gap_detector = "gap" in system_prompt.lower() or "ambiguity" in system_prompt.lower() or "gaps" in system_prompt.lower() or "clarification questions" in system_prompt.lower()
        is_process_clarification = "clarification evidence" in system_prompt.lower() or "process_clarification" in system_prompt.lower() or "update requirements with this clarification" in system_prompt.lower()
        is_conflict_detector = "contradiction" in system_prompt.lower() or "detect direct contradictions" in system_prompt.lower()
        is_finalizer = "synthesize a flat backlog" in system_prompt.lower() or "epics, features, user stories" in system_prompt.lower() or "finalizer" in system_prompt.lower()
        
        print(f"[MockModel Debug] is_srs_compiler: {is_srs_compiler}, is_memory_updater: {is_memory_updater}, is_gap_detector: {is_gap_detector}, is_finalizer: {is_finalizer}, extracted p_name: {p_name}")
        
        # Multi-Agent development prompts routing checks
        last_msg_lower = last_user_msg.lower()
        if "planningengine" in last_msg_lower or "projectplanner" in last_msg_lower:
            manifest_list = [
                {
                    "path": "app/main.py",
                    "module": "backend",
                    "owner_agent": "BackendAgent",
                    "purpose": "FastAPI entry point containing REST APIs",
                    "depends_on": "",
                    "priority": 1,
                    "language": "python",
                    "security_sensitive": True,
                    "estimated_tokens": 1200,
                    "requirement_id": "REQ-003",
                    "design_section_id": "api_endpoints"
                },
                {
                    "path": "app/database.py",
                    "module": "database",
                    "owner_agent": "DatabaseAgent",
                    "purpose": "Database initialization and engine setup",
                    "depends_on": "",
                    "priority": 2,
                    "language": "python",
                    "security_sensitive": False,
                    "estimated_tokens": 800,
                    "requirement_id": "REQ-001",
                    "design_section_id": "database_tables"
                },
                {
                    "path": "frontend/index.html",
                    "module": "frontend",
                    "owner_agent": "FrontendAgent",
                    "purpose": "React web app client file",
                    "depends_on": "",
                    "priority": 3,
                    "language": "html",
                    "security_sensitive": False,
                    "estimated_tokens": 500,
                    "requirement_id": "REQ-002",
                    "design_section_id": "ui_requirements"
                },
                {
                    "path": "README.md",
                    "module": "doc",
                    "owner_agent": "DocumentationAgent",
                    "purpose": "Setup instructions and compile steps",
                    "depends_on": "",
                    "priority": 4,
                    "language": "markdown",
                    "security_sensitive": False,
                    "estimated_tokens": 300,
                    "requirement_id": "REQ-004",
                    "design_section_id": "constraints"
                }
            ]
            response_content = json.dumps(manifest_list, indent=2)
            
        # Check messages for test override triggers
        all_text = (" ".join(str(m.content) for m in messages) + " " + system_prompt).lower()
        is_ownership_conflict = "ownership-conflict" in all_text
        is_api_mismatch = "api-mismatch" in all_text
        is_syntax_error = "syntax-error" in all_text
        is_input_validation_fail = "input-validation-fail" in all_text
        is_planning_fail = "planning-fail" in all_text
        is_agent_fail = "agent-fail" in all_text
        is_artifact_fail = "artifact-fail" in all_text

        print(f"[MockModel Debug] is_ownership_conflict: {is_ownership_conflict}, is_api_mismatch: {is_api_mismatch}, is_syntax_error: {is_syntax_error}, is_agent_fail: {is_agent_fail}, is_planning_fail: {is_planning_fail}, is_input_validation_fail: {is_input_validation_fail}, is_artifact_fail: {is_artifact_fail}")
        if is_gap_detector:
            print(f"[MockModel Debug] is_gap_detector all_text: {all_text}")
            if "laboratory" in all_text or "chemical" in all_text or "barcode scanner" in all_text:
                response_content = json.dumps({"gaps": []})
            else:
                topic = "room availability and reservation rules" if ("room" in all_text or "reserve" in all_text) else "operational workflow rules"
                response_content = json.dumps({
                    "gaps": [
                        {
                            "id": "GAP-001",
                            "question": f"Who is responsible for managing {topic}?",
                            "reason": "Administrative workflow details need clarification.",
                            "priority": "high",
                            "status": "pending"
                        }
                    ]
                }, indent=2)

        elif is_process_clarification:
            statement = f"System shall fulfill: {last_user_msg}" if last_user_msg else "Updated system requirement based on human clarification."
            if "hospital" in all_text or "administrator" in all_text:
                statement = "Hospital administrators manage doctor schedules, not individual doctors."
            elif "restaurant" in all_text or "menu" in all_text:
                statement = "Restaurants manage their own menus and price updates independently."
            elif "forbid" in all_text or "cancel" in all_text or "strictly forbidden" in all_text:
                statement = "Customers are strictly forbidden from cancelling orders once dispatched."

            response_content = json.dumps({
                "requirements": [
                    {
                        "requirement_id": "REQ-F001",
                        "title": "Clarified Operational Rule",
                        "statement": statement,
                        "requirement_type": "functional",
                        "priority": "must_have",
                        "status": "proposed"
                    }
                ]
            }, indent=2)

        elif is_conflict_detector:
            conflicts_list = []
            if ("permitted" in all_text or "can cancel" in all_text or "cancel package" in all_text) and ("forbidden" in all_text or "cannot cancel" in all_text or "strictly forbidden" in all_text):
                conflicts_list.append({
                    "id": "CONF-001",
                    "requirement_id": "REQ-F001",
                    "description": "Contradiction detected: initial input permits order cancellation after dispatch, but clarification answer strictly forbids it.",
                    "severity": "high",
                    "suggested_resolution": "Clarify cancellation rules with stakeholders."
                })
            response_content = json.dumps({"conflicts": conflicts_list}, indent=2)

        elif "quality assurance ba" in all_text or "consistency" in all_text:
            response_content = json.dumps({"conflicts": [], "duplicates": []})
        elif "databaseagent" in last_msg_lower or "databasedeveloperagent" in system_prompt.lower():
            if is_agent_fail:
                raise Exception("Mock Database Developer Agent Failure Exception")
            if is_ownership_conflict:
                response_content = """[FILE: app/database.py]
# app/database.py
from sqlalchemy import create_engine
DATABASE_URL = "sqlite:///./sdlc_studio_test.db"
engine = create_engine(DATABASE_URL)

[FILE: app/main.py]
# Conflict file claim
print("Conflict!")
"""
            else:
                response_content = """# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base

DATABASE_URL = "sqlite:///./sdlc_studio_test.db"
engine = create_engine(DATABASE_URL)
Base = declarative_base()
"""
            
        elif "backendagent" in last_msg_lower or "backenddeveloperagent" in system_prompt.lower():
            if is_syntax_error:
                response_content = """# app/main.py
def read_root()
    invalid python syntax error!
"""
            else:
                response_content = f"""# app/main.py
from fastapi import FastAPI
app = FastAPI(title="{p_name} API")

@app.get("/api")
def read_root():
    return {{"status": "success", "message": "{p_name} API"}}

@app.post("/api/checkout")
def checkout(payload: dict):
    return {{"status": "success", "service": "{p_name}"}}
"""
            
        elif "frontendagent" in last_msg_lower or "frontenddeveloperagent" in system_prompt.lower():
            if is_api_mismatch:
                response_content = """<!-- frontend/index.html -->
<!DOCTYPE html>
<html>
<body>
    <script>
        // Method mismatch: GET instead of POST
        fetch("/api/checkout", { method: "GET" });
    </script>
</body>
</html>
"""
            else:
                response_content = f"""<!-- frontend/index.html -->
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{p_name} Client</title>
</head>
<body>
    <div id="root">Welcome to {p_name} Client UI</div>
    <script>
        fetch("/api/checkout", {{ method: "POST" }});
    </script>
</body>
</html>
"""
            
        elif "apiintegrationagent" in last_msg_lower or "apiintegrationagent" in system_prompt.lower():
            response_content = json.dumps({"mismatches": [], "status": "COMPLETED"})
            
        elif "documentationagent" in last_msg_lower or "documentationagent" in system_prompt.lower():
            response_content = f"""# README.md
# {p_name} Scaffold

## Installation
Run:
`pip install -r requirements.txt`

## Execution
Run:
`uvicorn app.main:app --reload`
"""

        # Scenario 1: State Manager / Memory update
        # Scenario 1: State Manager / Memory update
        elif is_memory_updater:
            user_evidence_text = ""
            for m in messages:
                m_type = getattr(m, "type", "")
                m_role = getattr(m, "role", "") if hasattr(m, "role") else ""
                m_content = str(getattr(m, "content", ""))
                if (m_type in ["user", "human"] or m_role == "user") and m_content:
                    if not any(cmd in m_content.lower() for cmd in ["extract the canonical", "generate srs", "compile srs", "update requirements with this"]):
                        user_evidence_text += " " + m_content

            if not user_evidence_text.strip() and last_user_msg:
                user_evidence_text = last_user_msg

            kw_suffix = ""
            for kw in ["ownership-conflict", "api-mismatch", "syntax-error", "input-validation-fail", "planning-fail", "agent-fail", "artifact-fail"]:
                if kw in all_text:
                    kw_suffix = f" [TEST-KEYWORD: {kw}]"
                    break

            # Dynamic extraction without hardcoding
            p_name = _extract_dynamic_project_name(user_evidence_text)
            dyn_actors = _extract_dynamic_actors_from_text(user_evidence_text)
            dyn_func = _extract_dynamic_requirements_from_text(user_evidence_text)

            if kw_suffix:
                dyn_func.append(f"Traceability override check{kw_suffix}")

            summary = f"{p_name} fulfilling user provided requirements."
            memory_dict = {
                "project_summary": summary,
                "business_goals": f"Deliver core capabilities for {summary}",
                "target_users": dyn_actors,
                "functional_requirements": dyn_func,
                "non_functional_requirements": ["Not specified in the provided requirements."],
                "constraints": ["Not specified in the provided requirements."],
                "assumptions": ["Not specified in the provided requirements."],
                "acceptance_criteria": [f"Given user action, system fulfills {f}" for f in dyn_func],
                "open_questions": []
            }
            response_content = json.dumps(memory_dict, indent=2)

        # Scenario 1.5: Gap & Ambiguity Detector
        elif is_gap_detector:
            if "lab" in all_text or "chemical" in all_text or "barcode" in all_text or "vehicle" in all_text or "rental" in all_text:
                response_content = json.dumps({"gaps": []})
            else:
                topic = "operational workflow rules"
                response_content = json.dumps({
                    "gaps": [
                        {
                            "id": "GAP-001",
                            "question": f"Who is responsible for managing {topic}?",
                            "reason": "Administrative workflow details need clarification.",
                            "priority": "high",
                            "status": "pending"
                        }
                    ]
                }, indent=2)

        # Scenario 1.6: Clarification Answer Processor
        elif is_process_clarification:
            statement = f"System shall fulfill: {last_user_msg}" if last_user_msg else "Updated system requirement based on human clarification."
            if "hospital" in all_text or "administrator" in all_text:
                statement = "Hospital administrators manage doctor schedules, not individual doctors."
            elif "restaurant" in all_text or "menu" in all_text:
                statement = "Restaurants manage their own menus and price updates independently."
            elif "forbid" in all_text or "cancel" in all_text or "strictly forbidden" in all_text:
                statement = "Customers are strictly forbidden from cancelling orders once dispatched."

            response_content = json.dumps({
                "requirements": [
                    {
                        "requirement_id": "REQ-F001",
                        "title": "Clarified Operational Rule",
                        "statement": statement,
                        "requirement_type": "functional",
                        "priority": "must_have",
                        "status": "proposed"
                    }
                ]
            }, indent=2)

        # Scenario 1.7: Contradiction & Conflict Detector
        elif is_conflict_detector:
            conflicts_list = []
            if ("permitted" in all_text or "can cancel" in all_text or "cancel package" in all_text) and ("forbidden" in all_text or "cannot cancel" in all_text or "strictly forbidden" in all_text):
                conflicts_list.append({
                    "id": "CONF-001",
                    "requirement_id": "REQ-F001",
                    "description": "Contradiction detected: initial input permits order cancellation after dispatch, but clarification answer strictly forbids it.",
                    "severity": "high",
                    "suggested_resolution": "Clarify cancellation rules with stakeholders."
                })
            response_content = json.dumps({"conflicts": conflicts_list}, indent=2)

        # Scenario 1.8: Finalizer / Backlog Synthesizer
        elif is_finalizer:
            user_evidence_text = ""
            for m in messages:
                m_content = str(getattr(m, "content", ""))
                if getattr(m, "type", "") in ["user", "human"] or getattr(m, "role", "") == "user":
                    if not any(cmd in m_content.lower() for cmd in ["extract the canonical", "generate srs", "compile srs"]):
                        user_evidence_text += " " + m_content

            if not user_evidence_text.strip() and last_user_msg:
                user_evidence_text = last_user_msg

            dyn_actors = _extract_dynamic_actors_from_text(user_evidence_text)
            dyn_func = _extract_dynamic_requirements_from_text(user_evidence_text)

            epics_list = []
            features_list = []
            stories_list = []
            acs_list = []

            primary_actor = dyn_actors[0] if dyn_actors else "User"
            actor_sing = primary_actor.rstrip('s') if primary_actor.lower().endswith('s') and not primary_actor.lower().endswith('ss') else primary_actor
            art = "an" if actor_sing and actor_sing[0].lower() in "aeiou" else "a"

            epics_list.append({
                "epic_id": "EPIC-001",
                "title": f"{actor_sing} Core Capabilities",
                "description": f"Functional operations for {primary_actor}.",
                "status": "proposed",
                "source": {"source_type": "inference", "confidence": 1.0}
            })

            for i, f in enumerate(dyn_func):
                clean_f = f.rstrip('.').strip()
                clean_action = re.sub(r'^(?:[a-zA-Z]+s?\s+can\s+)', '', clean_f, flags=re.IGNORECASE).strip()
                action_clean = clean_action.lower()

                # Filter out Non-Functional Requirements
                is_nfr = any(k in action_clean or k in clean_f.lower() for k in [
                    "response time", "latency", "https", "tls", "gdpr", "soc2", "security", "encryption", "sla", "uptime", "throughput", "concurrency"
                ])
                if is_nfr:
                    continue

                feat_id = f"FEAT-{len(features_list)+1:03d}"
                story_id = f"US-{len(stories_list)+1:03d}"
                ac_id = f"AC-{len(acs_list)+1:03d}"

                features_list.append({
                    "feature_id": feat_id,
                    "epic_id": "EPIC-001",
                    "title": clean_action.capitalize()[:50],
                    "description": clean_f,
                    "status": "proposed",
                    "source": {"source_type": "inference", "confidence": 1.0}
                })

                if any(k in action_clean for k in ["view", "see", "display", "check", "browse", "read", "monitor", "search", "track"]):
                    topic = re.sub(r'^(?:view|see|display|check|browse|read|monitor|search|track)\s*', '', action_clean).strip()
                    benefit = f"stay informed about relevant {topic or 'information'}"
                    ac_given = f"Given {art} {actor_sing} is accessing the system"
                    ac_when = f"when they request to {action_clean}"
                    ac_then = f"then the system retrieves and displays the requested {topic or 'details'}."
                elif any(k in action_clean for k in ["buy", "purchase", "pay", "checkout", "order", "book", "reserve"]):
                    topic = re.sub(r'^(?:buy|purchase|pay|checkout|order|book|reserve)\s*', '', action_clean).strip()
                    benefit = f"successfully obtain the requested {topic or 'items or services'}"
                    ac_given = f"Given {art} {actor_sing} selects {topic or 'items'} to {action_clean}"
                    ac_when = f"when they confirm and submit the transaction"
                    ac_then = f"then the system processes the request and provides confirmation."
                elif any(k in action_clean for k in ["manage", "create", "add", "edit", "update", "delete", "configure", "setup"]):
                    topic = re.sub(r'^(?:manage|create|add|edit|update|delete|configure|setup)\s*', '', action_clean).strip()
                    benefit = f"keep {topic or 'system records'} accurate and up to date"
                    ac_given = f"Given {art} {actor_sing} accesses the management interface"
                    ac_when = f"when they submit updates to {action_clean}"
                    ac_then = f"then the system validates and saves the updated configuration."
                else:
                    benefit = f"accomplish {action_clean} effectively"
                    ac_given = f"Given {art} {actor_sing} initiates the request"
                    ac_when = f"when valid parameters are provided for {action_clean}"
                    ac_then = f"then the system completes the workflow and returns confirmation."

                stories_list.append({
                    "story_id": story_id,
                    "feature_id": feat_id,
                    "title": f"As {art} {actor_sing}, I want to {action_clean}",
                    "description": f"As {art} {actor_sing}, I want to {action_clean} so that I can {benefit}.",
                    "linked_requirement_ids": [f"REQ-{len(stories_list)+1:03d}"],
                    "status": "proposed",
                    "source": {"source_type": "user_input", "confidence": 1.0}
                })

                acs_list.append({
                    "ac_id": ac_id,
                    "story_id": story_id,
                    "statement": f"{ac_given}, {ac_when}, {ac_then}",
                    "status": "proposed",
                    "source": {"source_type": "user_input", "confidence": 1.0}
                })

            response_content = json.dumps({
                "epics": epics_list,
                "features": features_list,
                "user_stories": stories_list,
                "acceptance_criteria": acs_list
            }, indent=2)

        # Scenario 2: SRS Emitter / Compiler
        elif is_srs_compiler:
            user_evidence_text = ""
            for m in messages:
                m_content = str(getattr(m, "content", ""))
                if "Requirement Memory collected:" in m_content:
                    idx = m_content.find("Requirement Memory collected:")
                    user_evidence_text += " " + m_content[idx:]
                elif getattr(m, "type", "") in ["user", "human"] or getattr(m, "role", "") == "user":
                    if not any(cmd in m_content.lower() for cmd in ["extract the canonical", "generate srs", "compile srs"]):
                        user_evidence_text += " " + m_content

            if not user_evidence_text.strip() and last_user_msg:
                user_evidence_text = last_user_msg

            p_name = _extract_dynamic_project_name(user_evidence_text)
            if "input-validation-fail" in all_text:
                p_name = "Input-Validation-Fail App"
            elif "planning-fail" in all_text:
                p_name = "Planning-Fail App"
            elif "agent-fail" in all_text:
                p_name = "Agent-Fail App"
            elif "artifact-fail" in all_text:
                p_name = "Artifact-Fail App"

            dyn_actors = _extract_dynamic_actors_from_text(user_evidence_text)
            dyn_func = _extract_dynamic_requirements_from_text(user_evidence_text)
            p_summary = f"{p_name} requirements derived strictly from user prompt."
            scope = f"Scope derived from user requested capabilities: {', '.join(dyn_func[:4])}."

            if "input-validation-fail" in all_text:
                dyn_func.append("Traceability override check [TEST-KEYWORD: input-validation-fail]")
            elif "planning-fail" in all_text:
                dyn_func.append("Traceability override check [TEST-KEYWORD: planning-fail]")
            elif "agent-fail" in all_text:
                dyn_func.append("Traceability override check [TEST-KEYWORD: agent-fail]")
            elif "artifact-fail" in all_text:
                dyn_func.append("Traceability override check [TEST-KEYWORD: artifact-fail]")

            primary_actor = dyn_actors[0] if dyn_actors else "User"
            user_stories = [f"US-{i+1:03d}: As a {primary_actor}, I want to {f.lower()} so that the system fulfills this capability." for i, f in enumerate(dyn_func)]
            use_cases = [f"UC-{i+1:03d}: Execute {f}\n  • Actor: {primary_actor}\n  • Flow: Trigger -> Execute -> Persist State." for i, f in enumerate(dyn_func)]
            acceptance_criteria = [f"AC-{i+1:03d}: Given {primary_actor} initiates {f}, when system executes request, then capability is fulfilled." for i, f in enumerate(dyn_func)]
            rtm = [{"id": f"REQ-{i+1:03d}", "title": f[:40], "description": f, "category": "Functional"} for i, f in enumerate(dyn_func)]

            srs_dict = {
                "project_name": p_name,
                "document_information": "Classification: Internal. Author: AI Business Analyst. Organization: SDLC Studio.",
                "revision_history": "v1.0.0 - Initial grounded draft compilation.",
                "approval_history": "Approved by Business Analyst.",
                "executive_summary": p_summary + (" [TEST-KEYWORD: ownership-conflict]" if is_ownership_conflict else " [TEST-KEYWORD: api-mismatch]" if is_api_mismatch else " [TEST-KEYWORD: syntax-error]" if is_syntax_error else " [TEST-KEYWORD: input-validation-fail]" if is_input_validation_fail else " [TEST-KEYWORD: planning-fail]" if is_planning_fail else " [TEST-KEYWORD: agent-fail]" if is_agent_fail else " [TEST-KEYWORD: artifact-fail]" if is_artifact_fail else ""),
                "problem_statement": f"Requirements statement for {p_name}.",
                "business_objectives": f"Deliver capabilities for {p_name}.",
                "stakeholders": dyn_actors,
                "user_personas": ["Not specified in the provided requirements."],
                "actors": dyn_actors,
                "scope": scope,
                "out_of_scope": "Not specified in the provided requirements.",
                "business_requirements": ["Not specified in the provided requirements."],
                "functional_requirements": dyn_func,
                "non_functional_requirements": ["Not specified in the provided requirements."],
                "business_rules": ["Not specified in the provided requirements."],
                "user_stories": user_stories,
                "use_cases": use_cases,
                "acceptance_criteria": acceptance_criteria,
                "ui_requirements": ["Not specified in the provided requirements."],
                "navigation_flow": ["Not specified in the provided requirements."],
                "data_requirements": ["Not specified in the provided requirements."],
                "security_requirements": ["Not specified in the provided requirements."],
                "integration_requirements": ["Not specified in the provided requirements."],
                "performance_requirements": ["Not specified in the provided requirements."],
                "compliance_requirements": ["Not specified in the provided requirements."],
                "constraints": ["Not specified in the provided requirements."],
                "assumptions": ["Not specified in the provided requirements."],
                "risks": ["Not specified in the provided requirements."],
                "dependencies": ["Not specified in the provided requirements."],
                "requirement_traceability_matrix": rtm
            }
            response_content = json.dumps(srs_dict, indent=2)

        # Scenario 2.5: SDD Emitter / Compiler
        elif "architect" in system_prompt.lower() or "sdd" in system_prompt.lower() or "software design document" in system_prompt.lower():
            # Infer project type from system prompt context
            is_food = "delivery" in system_prompt.lower() or "food" in system_prompt.lower()
            if is_food:
                p_name = "Food Delivery Platform"
                intro = "This document presents the detailed architectural design and specifications for the Food Delivery platform."
                tech_stack = ["FastAPI", "React", "PostgreSQL", "Redis for tracking cache", "Docker"]
                tables = [
                    {
                        "name": "users",
                        "columns": [
                            {"name": "id", "type": "VARCHAR(36)", "nullable": False, "description": "Primary key UUID"},
                            {"name": "email", "type": "VARCHAR(255)", "nullable": False, "description": "Unique email"},
                            {"name": "password_hash", "type": "VARCHAR(255)", "nullable": False, "description": "Hashed password"}
                        ],
                        "primary_key": "id",
                        "foreign_keys": [],
                        "constraints": ["UNIQUE(email)"]
                    },
                    {
                        "name": "orders",
                        "columns": [
                            {"name": "id", "type": "VARCHAR(36)", "nullable": False, "description": "Primary key UUID"},
                            {"name": "customer_id", "type": "VARCHAR(36)", "nullable": False, "description": "Foreign key to users"},
                            {"name": "restaurant_name", "type": "VARCHAR(255)", "nullable": False, "description": "Selected restaurant"},
                            {"name": "total_amount", "type": "DECIMAL(10,2)", "nullable": False, "description": "Total payment price"}
                        ],
                        "primary_key": "id",
                        "foreign_keys": [
                            {"column": "customer_id", "references_table": "users", "references_column": "id"}
                        ],
                        "constraints": []
                    }
                ]
                apis = [
                    {
                        "method": "POST",
                        "path": "/api/orders/place",
                        "request_body": "{ 'restaurant_id': 'string', 'items': [{'id': 'string', 'quantity': 1}] }",
                        "response_body": "{ 'order_id': 'string', 'status': 'PENDING' }",
                        "description": "Places a new food order."
                    }
                ]
                traceability = [
                    {
                        "requirement_id": "REQ-003",
                        "module": "Order Processor",
                        "api_endpoint": "POST /api/orders/place",
                        "db_table": "orders",
                        "ui_screen": "Checkout screen"
                    }
                ]
            else:
                p_name = extract_project_name()
                if "input-validation-fail" in all_text:
                    p_name = "Input-Validation-Fail App"
                elif "planning-fail" in all_text:
                    p_name = "Planning-Fail App"
                elif "agent-fail" in all_text:
                    p_name = "Agent-Fail App"
                elif "artifact-fail" in all_text:
                    p_name = "Artifact-Fail App"
                intro = f"This document presents the detailed architectural design and specifications for the {p_name}."
                tech_stack = ["FastAPI", "React", "PostgreSQL", "Docker", "Stripe API SDK"]
                tables = [
                    {
                        "name": "users",
                        "columns": [
                            {"name": "id", "type": "VARCHAR(36)", "nullable": False, "description": "Primary key UUID"},
                            {"name": "email", "type": "VARCHAR(255)", "nullable": False, "description": "Unique user email"},
                            {"name": "password_hash", "type": "VARCHAR(255)", "nullable": False, "description": "Hashed user credentials"}
                        ],
                        "primary_key": "id",
                        "foreign_keys": [],
                        "constraints": ["UNIQUE(email)"]
                    },
                    {
                        "name": "orders",
                        "columns": [
                            {"name": "id", "type": "VARCHAR(36)", "nullable": False, "description": "Primary key UUID"},
                            {"name": "user_id", "type": "VARCHAR(36)", "nullable": False, "description": "Foreign key to users"},
                            {"name": "total_amount", "type": "DECIMAL(10,2)", "nullable": False, "description": "Order total cost"}
                        ],
                        "primary_key": "id",
                        "foreign_keys": [
                            {"column": "user_id", "references_table": "users", "references_column": "id"}
                        ],
                        "constraints": []
                    }
                ]
                apis = [
                    {
                        "method": "POST",
                        "path": "/api/orders/checkout",
                        "request_body": "{ 'items': [{'id': 'string', 'quantity': 1}], 'stripe_token': 'string' }",
                        "response_body": "{ 'order_id': 'string', 'charge_status': 'success' }",
                        "description": "Submits checkout cart items and charges customer billing credit card."
                    }
                ]
                traceability = [
                    {
                        "requirement_id": "REQ-003",
                        "module": "Checkout Module",
                        "api_endpoint": "POST /api/orders/checkout",
                        "db_table": "orders",
                        "ui_screen": "Payment confirmation screen"
                    }
                ]

            sdd_dict = {
                "cover_page": f"SOFTWARE DESIGN DOCUMENT\nProject: {p_name}\nAuthor: Lead Architect\nOrganization: SDLC Studio Labs\nClassification: Internal Confidentially",
                "revision_history": "v1.0.0 (2026-07-26) - Initial architecture definition. v1.1.0 (2026-07-26) - Added security parameters.",
                "approval_history": "Reviewed by Lead Architect on 2026-07-26. Awaiting final PM signature.",
                "introduction": intro + (" [TEST-KEYWORD: ownership-conflict]" if is_ownership_conflict else " [TEST-KEYWORD: api-mismatch]" if is_api_mismatch else " [TEST-KEYWORD: syntax-error]" if is_syntax_error else ""),
                "design_goals": "Target SLA: 99.9% uptime. API latency < 2s. Support horizontal container scale.",
                "system_overview": "Three-tier architecture: React web app client, FastAPI REST gateway application server, PostgreSQL database store.",
                "high_level_architecture": "Clean Architecture implementation with segregated UI layers, API routing, business services, and database gateways.",
                "low_level_architecture": "Details submodules: authentication services, ordering checkouts, payment managers, and inventory sync processes.",
                "module_breakdown": "API Layer: main.py, routers/. Domain Layer: services/, models/. Repository Layer: database.py, repositories/.",
                
                # Mermaid Diagrams syntax fields
                "system_context_diagram_mermaid": f"graph TD\n  User[Customer] -->|Browse & Order| System[{p_name}]\n  System -->|Process Payment| PaymentGateway[Stripe API]",
                "use_case_diagram_mermaid": "graph LR\n  subgraph System[\"System Scope\"]\n    UC1([\"Browse Products\"])\n    UC2([\"Checkout Orders\"])\n    UC3([\"Update Catalog\"])\n  end\n  Customer[\"👤 Customer\"] --> UC1\n  Customer --> UC2\n  Administrator[\"👤 Administrator\"] --> UC3",
                "component_diagram_mermaid": "graph TD\n  subgraph Client App\n    UI[React Web App]\n  end\n  subgraph Backend Gateway\n    Controller[FastAPI Router] --> Service[Order Service]\n  end\n  subgraph Database Layer\n    Service --> Repo[SQLAlchemy Repository]\n    Repo --> DB[(PostgreSQL Database)]\n  end\n  UI -->|HTTP POST| Controller",
                "class_diagram_mermaid": "classDiagram\n  class User {\n    +String id\n    +String email\n    +login()\n  }\n  class Order {\n    +String id\n    +Float totalAmount\n    +save()\n  }\n  User --> Order",
                "sequence_diagram_mermaid": "sequenceDiagram\n  actor Customer\n  Customer->>UI: Click Purchase\n  UI->>Gateway: POST /api/orders/checkout\n  Gateway->>Stripe: Charge Token\n  Stripe-->>Gateway: Charge Approved\n  Gateway->>Database: Save Order Record\n  Database-->>Gateway: Save Success\n  Gateway-->>UI: Confirm Order ID\n  UI-->>Customer: Display Success Screen",
                "activity_diagram_mermaid": "graph TD\n  Start([Start]) --> Browse[Browse Items] --> Cart[Add to Cart] --> Check[Checkout Payment] --> End([End])",
                "er_diagram_mermaid": "erDiagram\n  users ||--o{ orders : places\n  users {\n    string id PK\n    string email\n  }\n  orders {\n    string id PK\n    string user_id FK\n    float total_amount\n  }",
                "deployment_diagram_mermaid": "graph TD\n  subgraph AWS Cloud\n    ALB[Application Load Balancer] --> ECS[FastAPI Container Service]\n    ECS --> RDS[(Managed RDS Database)]\n  end",
                "flow_diagram_mermaid": "graph TD\n  Step1[Browse products] --> Step2[Modify quantities] --> Step3[Submit stripe payment]",
                "db_relationship_diagram_mermaid": "graph TD\n  users -->|one-to-many| orders",
                
                "database_design_overview": "Relational schema design implemented on PostgreSQL database. Strict foreign keys enforce integrity constraints.",
                "database_tables": tables,
                "database_relationships": ["users table contains a one-to-many relation with orders table linked via user_id column."],
                "database_constraints": ["FOREIGN KEY (user_id) REFERENCES users(id)", "UNIQUE(email) on users table."],
                
                "api_design_overview": "RESTful endpoints communicating in JSON payloads. Uses standard HTTP response templates (200, 201, 400, 404, 500).",
                "api_endpoints": apis,
                "authentication_flow": "Stateless authentication via secure JSON Web Tokens (JWT). Passwords hashed using bcrypt prior to database insertion.",
                "authorization_flow": "Role-Based Access Control (RBAC). Admin routes are gated with specific check decorator checks.",
                
                "security_design_policies": "All communications encrypted via TLS 1.3. CORS origins white-listed. SQL injection prevented using parameters binding.",
                "logging_strategy": "Structured JSON logging containing correlation IDs, log level parameters, and trace logs. Outputs to console stdout.",
                "exception_handling": "Global middleware intercepts exceptions, logs stack trace data, and returns formatted error payloads with stable codes.",
                "configuration_management": "System configuration parameters loaded dynamically from secure environment variables and Vault files.",
                
                "technology_stack": tech_stack,
                "folder_structure": "src/\n  main.py\n  api/\n    routers/\n  core/\n    config.py\n  services/\n  models/\n  repositories/\ntests/",
                "coding_standards": "Enforce PEP-8 guidelines. Static code checks verified using flake8 and black. PR reviews require approvals.",
                
                "performance_design": "Index primary keys and search fields. Implement connection pooling on DB engines. Cache configuration states.",
                "scalability_design": "FastAPI containers deployed as stateless cluster nodes under ALB. Scale thresholds defined at 75% average CPU limits.",
                "availability_design": "Multi-AZ database replica deployments with automatic health checking and failover systems. target SLA is 99.9% uptime.",
                
                "monitoring_strategy": "Expose Prometheus scraping endpoints. Alert notifications triggered when error rates exceed 1% within a 5-minute interval.",
                "backup_strategy": "Automated snapshot snapshots taken daily with a 30-day retention policy. Transaction logs replicated continuously.",
                "disaster_recovery_runbook": "Backup restoration recovery procedures run quarterly. RPO target is 24 hours. RTO target is 4 hours.",
                "architectural_risks": ["Potential stripe gateway response lag during peak periods. Mitigation: Queue client retry processes."],
                "design_assumptions": ["FastAPI container will scale horizontally under the AWS Application Load Balancer."],
                "future_enhancements": ["Integrate Redis query cache for catalogs.", "Develop custom recommendation model analytics."],
                "traceability_matrix": traceability
            }
            if is_input_validation_fail:
                if "database_tables" in sdd_dict:
                    del sdd_dict["database_tables"]
            response_content = json.dumps(sdd_dict, indent=2)

        # Scenario 2.7: Project Planner (Development Agent)
        elif "manifest" in system_prompt.lower() or "planner" in system_prompt.lower() or "manifest" in last_user_msg.lower():
            if is_planning_fail:
                raise Exception("Mock Planning Engine Failure Exception")
            manifest_list = [
                {
                    "path": "app/main.py",
                    "module": "backend",
                    "owner_agent": "CodeGenerator",
                    "purpose": "FastAPI entry point containing REST APIs",
                    "depends_on": "",
                    "priority": 1,
                    "language": "python",
                    "security_sensitive": True,
                    "estimated_tokens": 1200
                },
                {
                    "path": "app/database.py",
                    "module": "database",
                    "owner_agent": "CodeGenerator",
                    "purpose": "Database initialization and engine setup",
                    "depends_on": "",
                    "priority": 2,
                    "language": "python",
                    "security_sensitive": False,
                    "estimated_tokens": 800
                },
                {
                    "path": "frontend/index.html",
                    "module": "frontend",
                    "owner_agent": "CodeGenerator",
                    "purpose": "React web app client file",
                    "depends_on": "",
                    "priority": 3,
                    "language": "html",
                    "security_sensitive": False,
                    "estimated_tokens": 500
                },
                {
                    "path": "README.md",
                    "module": "doc",
                    "owner_agent": "CodeGenerator",
                    "purpose": "Setup instructions and compile steps",
                    "depends_on": "",
                    "priority": 4,
                    "language": "markdown",
                    "security_sensitive": False,
                    "estimated_tokens": 300
                }
            ]
            response_content = json.dumps(manifest_list, indent=2)

        # Scenario 2.8: Code Generator (Development Agent)
        elif "source code" in system_prompt.lower() or "file path:" in last_user_msg.lower() or "source code" in last_user_msg.lower() or "code content" in system_prompt.lower() or "agent" in system_prompt.lower() or "developer" in system_prompt.lower() or "database" in system_prompt.lower() or "backend" in system_prompt.lower() or "frontend" in system_prompt.lower():
            if is_agent_fail:
                raise Exception("Mock Agent Worker Failure Exception")
            last_msg_lower = last_user_msg.lower()
            if "main.py" in last_msg_lower or "main" in last_msg_lower:
                response_content = f"""# app/main.py
from fastapi import FastAPI
app = FastAPI(title="{p_name} API")

@app.get("/api")
def read_root():
    return {{"status": "success", "message": "{p_name} API"}}

@app.post("/api/checkout")
def checkout(payload: dict):
    return {{"status": "success", "service": "{p_name}"}}
"""
            elif "database.py" in last_msg_lower or "database" in last_msg_lower:
                response_content = """# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base

DATABASE_URL = "sqlite:///./sdlc_studio_test.db"
engine = create_engine(DATABASE_URL)
Base = declarative_base()
"""
            elif "index.html" in last_msg_lower or "index" in last_msg_lower:
                response_content = f"""<!-- frontend/index.html -->
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{p_name} Client</title>
</head>
<body>
    <div id="root">Welcome to {p_name} Client UI</div>
</body>
</html>
"""
            else:
                response_content = f"""# README.md
# {p_name} Scaffold

## Installation
Run:
`pip install -r requirements.txt`

## Execution
Run:
`uvicorn app.main:app --reload`
"""

        # Scenario 3: Conversational Chat
        else:
            if not last_user_msg:
                response_content = "Hello! I am your AI Business Analyst. What kind of application are we building today?"
            elif "generate" in last_user_msg.lower() or "srs" in last_user_msg.lower() or "finish" in last_user_msg.lower():
                response_content = "I have collected sufficient information. Let's compile and generate the SRS document now!"
            else:
                response_content = f"Got it. I have noted that down. Can you tell me more about the primary target users and if there are any specific tech constraints we need to know about?"

        ai_message = AIMessage(content=response_content)
        return ChatResult(generations=[ChatGeneration(message=ai_message)])

    @property
    def _llm_type(self) -> str:
        return "mock-sdlc-model"


def get_llm() -> BaseChatModel:
    # Force MockChatModel only if MOCK_MODE is true
    if os.getenv("MOCK_MODE", "false").lower() == "true":
        print("[LLM Provider] MOCK_MODE is true. Forcing MockChatModel.")
        return MockChatModel()
        
    provider = os.getenv("DEFAULT_LLM_PROVIDER", "gemini").lower()
    model_name = os.getenv("DEFAULT_LLM_MODEL", "")

    has_openai = bool(os.getenv("OPENAI_API_KEY"))
    has_gemini = bool(os.getenv("GEMINI_API_KEY"))
    has_anthropic = bool(os.getenv("ANTHROPIC_API_KEY"))

    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key and not os.getenv("GOOGLE_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = gemini_key

    if provider == "openai" and has_openai:
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model=model_name or "gpt-4o", temperature=0.2)
        except ImportError as ie:
            print(f"[LLM Provider] langchain_openai import error: {ie}")
    elif provider == "gemini" and has_gemini:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model=model_name or "gemini-3.6-flash", api_key=gemini_key, temperature=0.2)
        except Exception as ie:
            print(f"[LLM Provider] langchain_google_genai error: {ie}")
    elif provider == "anthropic" and has_anthropic:
        try:
            from langchain_community.chat_models import ChatAnthropic
            return ChatAnthropic(model=model_name or "claude-3-5-sonnet", temperature=0.2)
        except ImportError as ie:
            print(f"[LLM Provider] langchain_community import error: {ie}")

    # Fallback to active key if default provider isn't configured
    if has_gemini:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(model="gemini-3.6-flash", api_key=gemini_key, temperature=0.2)
        except Exception:
            pass
    if has_openai:
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(model="gpt-4o-mini", temperature=0.2)
        except Exception:
            pass

    # If no keys or dependencies missing, fallback to MockChatModel to prevent server crash
    print("[LLM Provider] No active LLM provider configured or available. Falling back to MockChatModel.")
    return MockChatModel()
