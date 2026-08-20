import json
from typing import Dict, Any, List, Optional, TypedDict
from pydantic import ValidationError
from langgraph.graph import StateGraph, END
from langgraph.types import interrupt

from ..database import sqlite_checkpointer
from .state import AgentState
from ..schemas import RequirementMemory, ProjectDocument, Requirement, Epic, Feature, UserStory, AcceptanceCriterion, QualityResult, RequirementStatus, RequirementSource, SourceType
from ..services.llm_provider import get_llm, get_content_text
from ..services import input_guardrails, json_repair, requirement_validator

# ----------------- PROMPTS -----------------
from ..prompts.requirement_prompts import (
    MEMORY_UPDATER_SYSTEM_PROMPT,
    CHAT_AGENT_SYSTEM_PROMPT,
)

EXTRACTION_SYSTEM_PROMPT = """
You are a Senior Business Analyst. Your task is to analyze the gathered Requirement Memory and conversation history, and extract a complete, canonical ProjectDocument.

Requirement Memory collected:
{memory_json}

You must extract:
1. project_summary: String summary of the software project
2. business_goals: List of measurable business goals
3. problem_statement: Pain points and core problem to solve
4. stakeholders: Key stakeholder roles and groups
5. actors: User roles, external systems, or entities interacting with the application
6. workflows: List of step-by-step user/system workflows. Each workflow has: workflow_id, name, actor, trigger, steps (list of strings).
7. requirements: List of canonical requirements. Each requirement has:
   - requirement_id: Stable unique ID (e.g. REQ-001, REQ-002, etc.)
   - title: Short title
   - statement: Clear, unambiguous requirement text
   - requirement_type: "functional", "non_functional", or "business_rule"
   - actor: Primary actor involved
   - priority: "must_have", "should_have", "could_have", or "wont_have"
   - status: "proposed"
   - source: Provenance object: {{ "source_type": "user_input"|"inference"|"assumption", "source_reference": null, "source_text": "...", "confidence": 0.9 }}
8. assumptions: List of foundational assumptions
9. constraints: List of technical or business restrictions
10. dependencies: List of external third-party dependencies or systems
11. risks: List of identified risks and potential impact

Return the output as a raw JSON object matching this schema:
{{
  "project_summary": "...",
  "business_goals": ["..."],
  "problem_statement": "...",
  "stakeholders": ["..."],
  "actors": ["..."],
  "workflows": [
    {{
      "workflow_id": "WF-001",
      "name": "Checkout Flow",
      "actor": "Customer",
      "trigger": "User clicks checkout",
      "steps": ["Step 1", "Step 2"]
    }}
  ],
  "requirements": [
    {{
      "requirement_id": "REQ-001",
      "title": "Send Email Notification",
      "statement": "The system must send email receipt notifications using SendGrid upon checkout completion.",
      "requirement_type": "functional",
      "actor": "Checkout Service",
      "priority": "must_have",
      "status": "proposed",
      "source": {{
        "source_type": "user_input",
        "source_reference": null,
        "source_text": "Please ensure we add email receipt notifications using SendGrid",
        "confidence": 1.0
      }}
    }}
  ],
  "assumptions": ["..."],
  "constraints": ["..."],
  "dependencies": ["SendGrid API"],
  "risks": ["..."]
}}

Do not write markdown block ticks (no ```) or any preamble/explanation. Return ONLY the raw valid JSON.
"""

GAP_DETECTOR_SYSTEM_PROMPT = """
You are a Software QA and Business Analyst. Your task is to analyze the extracted requirements list and identify gaps or missing details.

Requirements to analyze:
{requirements_json}

Identify:
1. Missing non-functional requirements (e.g., performance thresholds, security constraints, reliability expectations).
2. Ambiguous or underspecified requirements.
3. Logical contradictions or conflicting rules.

Return the output as a JSON object containing a list of gaps:
{{
  "gaps": [
    {{
      "id": "GAP-001",
      "description": "No response time threshold is defined for search operation.",
      "blocking": true,
      "suggested_question": "What is the maximum acceptable response time for search queries?"
    }}
  ]
}}

Do not write markdown block ticks (no ```) or any preamble/explanation. Return ONLY the raw valid JSON.
"""

FINALIZER_SYSTEM_PROMPT = """
You are a Senior Architect and Product Owner. Your task is to synthesize a flat backlog (Epics, Features, User Stories, and Acceptance Criteria) from the approved requirements.

Approved Requirements:
{requirements_json}

You must generate:
1. Epics: High-level modules or areas (e.g., EPIC-001). Each has: epic_id, title, description, status ("proposed"), source.
2. Features: Capabilities within an Epic (e.g., FEAT-001). Each has: feature_id, epic_id, title, description, status, source.
3. User Stories: Agile user stories (e.g., US-001). Each has: story_id, feature_id, title, description ("As a... I want... So that..."), linked_requirement_ids (list of requirement IDs it traces back to), status, source.
4. Acceptance Criteria: Clear Given-When-Then test conditions (e.g., AC-001). Each has: ac_id, story_id, statement ("Given..., When..., Then..."), status, source.

Ensure every backlog element includes a 'source' object tracking provenance back to the requirements or conversation.
Every functional requirement must be mapped to at least one User Story to ensure coverage.

Return the output as a JSON object matching this schema:
{{
  "epics": [
    {{
      "epic_id": "EPIC-001",
      "title": "...",
      "description": "...",
      "status": "proposed",
      "source": {{ "source_type": "inference", "confidence": 0.9 }}
    }}
  ],
  "features": [
    {{
      "feature_id": "FEAT-001",
      "epic_id": "EPIC-001",
      "title": "...",
      "description": "...",
      "status": "proposed",
      "source": {{ "source_type": "inference", "confidence": 0.9 }}
    }}
  ],
  "user_stories": [
    {{
      "story_id": "US-001",
      "feature_id": "FEAT-001",
      "title": "...",
      "description": "As a user, I want to log in so that I can access my profile.",
      "linked_requirement_ids": ["REQ-001"],
      "status": "proposed",
      "source": {{ "source_type": "inference", "confidence": 0.9 }}
    }}
  ],
  "acceptance_criteria": [
    {{
      "ac_id": "AC-001",
      "story_id": "US-001",
      "statement": "Given valid credentials, when the user submits, then they are logged in.",
      "status": "proposed",
      "source": {{ "source_type": "inference", "confidence": 0.9 }}
    }}
  ]
}}

Do not write markdown block ticks or any preamble/explanation. Return ONLY the raw valid JSON.
"""

# ----------------- NODES -----------------

def input_validation(state: AgentState) -> Dict[str, Any]:
    """Node: Checks relevance and prompt injection on user input."""
    messages = state.get("messages", [])
    if not messages:
        return {"phase": "draft"}
        
    last_msg = messages[-1]["text"].strip()
    if not last_msg:
        return {"phase": "draft"}
        
    # Check injection
    if input_guardrails.detect_prompt_injection(last_msg):
        return {"phase": "failed", "missing_info": ["Prompt injection attempt detected."]}
        
    # Check relevance
    last_msg_lower = last_msg.lower()
    is_control = any(x in last_msg_lower for x in ["generate srs", "compile srs", "finish"])
    if not is_control and not input_guardrails.check_relevance(last_msg):
        return {"phase": "failed", "missing_info": ["The request does not appear to be related to software development."]}
        
    return {"phase": "processing"}


def conversation_state_manager(state: AgentState) -> Dict[str, Any]:
    """Node: Gathers user chat info and updates Requirement Memory."""
    phase = state.get("phase")
    if phase in ["failed", "completed"]:
        return {}
        
    messages = state.get("messages", [])
    llm = get_llm()
    
    chat_history_str = ""
    for m in messages:
        sender = "User" if m["sender"] == "user" else "BA Agent"
        chat_history_str += f"{sender}: {m['text']}\n"
        
    try:
        response = llm.invoke([
            {"role": "system", "content": MEMORY_UPDATER_SYSTEM_PROMPT},
            {"role": "user", "content": f"Conversation History:\n{chat_history_str}\n\nCurrent Memory Schema state:\n{state.get('memory')}"}
        ])
        
        # Parse and repair JSON
        memory_data = json_repair.repair_json(response.content)
        updated_memory = RequirementMemory(**memory_data)
        
        missing_info = updated_memory.open_questions if updated_memory.open_questions else []
        if not updated_memory.project_summary:
            missing_info.append("Project Summary is missing.")
        if not updated_memory.business_goals:
            missing_info.append("Business Goals are missing.")
            
        return {
            "memory": updated_memory,
            "missing_info": missing_info
        }
    except Exception as e:
        print(f"[Requirement Agent] Error updating memory: {e}")
        return {}


def prompt_generator_and_llm(state: AgentState) -> Dict[str, Any]:
    """Node: Generates standard conversation replies if not compiling."""
    phase = state.get("phase")
    if phase in ["failed", "completed", "extraction_completed", "gap_detection_completed"]:
        return {}
        
    messages = state.get("messages", [])
    memory = state.get("memory")
    last_msg = messages[-1]["text"].lower() if messages else ""
    
    trigger_compile = False
    compile_keywords = [
        "generate srs", "compile srs", "finish", "generate requirement", "generate requirements",
        "compile requirement", "compile requirements", "extract requirement", "extract requirements",
        "analyze requirement", "analyze requirements", "create requirement", "create requirements",
        "make requirement", "make requirements", "build requirements", "generate document",
        "process problem statement", "start extraction", "create srs", "build srs"
    ]
    if any(kw in last_msg for kw in compile_keywords) or phase == "GENERATING_SRS":
        trigger_compile = True
        
    if trigger_compile:
        return {"phase": "processing"}
        
    llm = get_llm()
    memory_json = json.dumps(memory.dict() if memory else {}, indent=2)
    response = llm.invoke([
        {"role": "system", "content": CHAT_AGENT_SYSTEM_PROMPT.format(memory_json=memory_json)},
        {"role": "user", "content": "Please generate the next question or reply."}
    ])
    
    reply_text = get_content_text(response).strip()
    new_messages = list(messages)
    new_messages.append({"sender": "agent", "text": reply_text})
    
    return {
        "messages": new_messages,
        "phase": "draft"
    }


def extraction_node(state: AgentState) -> Dict[str, Any]:
    """Node: Extracts requirements into canonical ProjectDocument model."""
    print("[Requirement Node] Running Extraction...")
    memory = state.get("memory")
    project_id = state.get("project_id")
    llm = get_llm()
    
    memory_json = json.dumps(memory.dict() if memory else {}, indent=2)
    
    reviewer_comments = ""
    feedback = state.get("user_feedback")
    if feedback and feedback.get("status") == "REJECTED":
        reviewer_comments = f"\nReviewer Rejection Comments (address these specifically): {feedback.get('comments')}\n"
        
    try:
        response = llm.invoke([
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT.format(memory_json=memory_json)},
            {"role": "user", "content": f"Extract the canonical ProjectDocument.{reviewer_comments}"}
        ])
        
        repaired_json = json_repair.repair_json(response.content)
        reqs_list = repaired_json.get("requirements", [])
        
        requirements = []
        for r in reqs_list:
            src_data = r.get("source", {})
            source = RequirementSource(
                source_type=SourceType(src_data.get("source_type", "inference")),
                source_reference=src_data.get("source_reference"),
                source_text=src_data.get("source_text"),
                confidence=float(src_data.get("confidence", 1.0))
            )
            
            req = Requirement(
                requirement_id=r.get("requirement_id"),
                title=r.get("title", ""),
                statement=r.get("statement", ""),
                requirement_type=r.get("requirement_type", "functional"),
                actor=r.get("actor"),
                priority=r.get("priority", "must_have"),
                status=RequirementStatus.proposed,
                source=source,
                linked_epic_ids=r.get("linked_epic_ids", [])
            )
            requirements.append(req)

        from ..schemas import WorkflowItem
        workflows = []
        for wf in repaired_json.get("workflows", []):
            workflows.append(WorkflowItem(
                workflow_id=wf.get("workflow_id", f"WF-{len(workflows)+1:03d}"),
                name=wf.get("name", ""),
                actor=wf.get("actor", ""),
                trigger=wf.get("trigger", ""),
                steps=wf.get("steps", [])
            ))
            
        doc = ProjectDocument(
            project_id=project_id,
            version=1,
            project_summary=repaired_json.get("project_summary") or (memory.project_summary if memory else None),
            business_goals=repaired_json.get("business_goals") or ([memory.business_goals] if memory and memory.business_goals else []),
            problem_statement=repaired_json.get("problem_statement"),
            stakeholders=repaired_json.get("stakeholders", []),
            actors=repaired_json.get("actors", []),
            workflows=workflows,
            requirements=requirements,
            assumptions=repaired_json.get("assumptions", []),
            constraints=repaired_json.get("constraints", []),
            dependencies=repaired_json.get("dependencies", []),
            risks=repaired_json.get("risks", [])
        )
        
        return {
            "document": doc,
            "phase": "awaiting_extraction_approval",
            "user_feedback": None
        }
    except Exception as e:
        print(f"[Requirement Agent] Extraction error: {e}")
        return {"phase": "failed", "missing_info": [f"Extraction failed: {str(e)}"]}


def awaiting_extraction_approval(state: AgentState) -> Dict[str, Any]:
    """Node: Pauses graph using interrupt to wait for human review of extraction."""
    print("[Requirement Node] Interrupting for Extraction Approval...")
    feedback = interrupt({
        "stage": "EXTRACTION",
        "message": "Please review the extracted requirements.",
        "document": state.get("document").dict() if state.get("document") else None
    })
    return {"user_feedback": feedback}


def post_extraction_handler(state: AgentState) -> Dict[str, Any]:
    """Node: Processes extraction approval/rejection and routes phase."""
    feedback = state.get("user_feedback") or {}
    status = feedback.get("status")
    comments = feedback.get("comments", "")
    
    if status == "APPROVED":
        print("[Requirement Node] Extraction Approved!")
        return {"phase": "gap_detection_running"}
    else:
        print(f"[Requirement Node] Extraction Rejected: {comments}")
        messages = list(state.get("messages", []))
        messages.append({
            "sender": "user",
            "text": f"Requirements extraction rejected. Comments: {comments}"
        })
        return {
            "phase": "processing",
            "messages": messages,
            "user_feedback": feedback
        }


def gap_detector_node(state: AgentState) -> Dict[str, Any]:
    """Node: Runs LLM gap detector on extracted requirements."""
    print("[Requirement Node] Running Gap Detection...")
    doc = state.get("document")
    llm = get_llm()
    
    reqs_json = json.dumps([r.dict() for r in doc.requirements], indent=2)
    
    try:
        response = llm.invoke([
            {"role": "system", "content": GAP_DETECTOR_SYSTEM_PROMPT.format(requirements_json=reqs_json)},
            {"role": "user", "content": "Analyze the requirements for gaps."}
        ])
        
        repaired_json = json_repair.repair_json(response.content)
        gaps = repaired_json.get("gaps", [])
        
        return {
            "gaps": gaps,
            "phase": "awaiting_gap_approval",
            "user_feedback": None
        }
    except Exception as e:
        print(f"[Requirement Agent] Gap detection error: {e}")
        return {"phase": "failed", "missing_info": [f"Gap detection failed: {str(e)}"]}


def awaiting_gap_approval(state: AgentState) -> Dict[str, Any]:
    """Node: Pauses graph using interrupt to wait for human review of gaps."""
    print("[Requirement Node] Interrupting for Gap Approval...")
    feedback = interrupt({
        "stage": "GAP_DETECTION",
        "message": "Please review the detected gaps and clarify if necessary.",
        "gaps": state.get("gaps", [])
    })
    return {"user_feedback": feedback}


def post_gap_handler(state: AgentState) -> Dict[str, Any]:
    """Node: Routes phase based on gap approval and blocking gaps."""
    feedback = state.get("user_feedback") or {}
    status = feedback.get("status")
    comments = feedback.get("comments", "")
    
    if status == "APPROVED":
        print("[Requirement Node] Gaps Approved!")
        gaps = state.get("gaps", [])
        blocking_gaps = [g for g in gaps if g.get("blocking")]
        if blocking_gaps:
            return {"phase": "waiting_for_clarification"}
        else:
            return {"phase": "validating"}
    else:
        print(f"[Requirement Node] Gaps Rejected: {comments}")
        return {
            "phase": "gap_detection_running",
            "user_feedback": feedback
        }


def waiting_for_clarification(state: AgentState) -> Dict[str, Any]:
    """Node: Suspends flow to await user answers to blocking gaps."""
    print("[Requirement Node] Suspending for user clarification answers...")
    gaps = state.get("gaps", [])
    blocking_gaps = [g for g in gaps if g.get("blocking")]
    
    questions_list = [f"- {g['id']}: {g['suggested_question']} (Gap: {g['description']})" for g in blocking_gaps]
    questions_text = "I have identified some blocking gaps. Please answer these questions to proceed:\n" + "\n".join(questions_list)
    
    messages = list(state.get("messages", []))
    messages.append({
        "sender": "agent",
        "text": questions_text
    })
    
    feedback = interrupt({
        "stage": "CLARIFICATION",
        "message": questions_text,
        "gaps": blocking_gaps
    })
    
    answer_text = feedback.get("answer", "")
    messages.append({
        "sender": "user",
        "text": f"Clarification Answers:\n{answer_text}"
    })
    
    return {
        "messages": messages,
        "phase": "processing",
        "user_feedback": None
    }


def validation_node(state: AgentState) -> Dict[str, Any]:
    """Node: Runs deterministic validator and transitions to approval."""
    print("[Requirement Node] Running Quality Validation...")
    doc = state.get("document")
    
    quality_result = requirement_validator.validate_requirement_document(doc)
    doc.quality_result = quality_result
    
    if not quality_result.valid:
        print("[Requirement Node] Validation FAILED.")
        return {
            "document": doc,
            "phase": "validation_failed"
        }
    else:
        print("[Requirement Node] Validation PASSED.")
        return {
            "document": doc,
            "phase": "awaiting_validation_approval"
        }


def awaiting_validation_approval(state: AgentState) -> Dict[str, Any]:
    """Node: Pauses graph using interrupt to wait for human review of validation results."""
    print("[Requirement Node] Interrupting for Validation Approval...")
    feedback = interrupt({
        "stage": "VALIDATION",
        "message": "Please review the requirement quality scores and issues.",
        "quality_result": state.get("document").quality_result.dict() if state.get("document") and state.get("document").quality_result else None
    })
    return {"user_feedback": feedback}


def post_validation_handler(state: AgentState) -> Dict[str, Any]:
    """Node: Processes validation approval/rejection."""
    feedback = state.get("user_feedback") or {}
    status = feedback.get("status")
    comments = feedback.get("comments", "")
    
    if status == "APPROVED":
        print("[Requirement Node] Validation Approved!")
        return {"phase": "ready_for_finalization"}
    else:
        print(f"[Requirement Node] Validation Rejected: {comments}")
        return {
            "phase": "validating",
            "user_feedback": feedback
        }


def finalizer_node(state: AgentState) -> Dict[str, Any]:
    """Node: Runs LLM to generate Epic/Feature/Story/AC backlog based on requirements."""
    print("[Requirement Node] Running Backlog Synthesis (Finalization)...")
    doc = state.get("document")
    project_id = state.get("project_id")
    llm = get_llm()
    
    reqs_json = json.dumps([r.dict() for r in doc.requirements], indent=2)
    
    reviewer_comments = ""
    feedback = state.get("user_feedback")
    if feedback and feedback.get("status") == "REJECTED":
        reviewer_comments = f"\nReviewer Feedback on previous backlog (modify/fix accordingly): {feedback.get('comments')}\n"
        
    try:
        response = llm.invoke([
            {"role": "system", "content": FINALIZER_SYSTEM_PROMPT.format(requirements_json=reqs_json)},
            {"role": "user", "content": f"Generate the trace-linked backlog.{reviewer_comments}"}
        ])
        
        repaired_json = json_repair.repair_json(response.content)
        
        epics = []
        for ep in repaired_json.get("epics", []):
            epics.append(Epic(
                epic_id=ep.get("epic_id"),
                title=ep.get("title", ""),
                description=ep.get("description"),
                status=RequirementStatus.proposed,
                source=RequirementSource(
                    source_type=SourceType(ep.get("source", {}).get("source_type", "inference")),
                    confidence=float(ep.get("source", {}).get("confidence", 0.9))
                )
            ))
            
        features = []
        for f in repaired_json.get("features", []):
            features.append(Feature(
                feature_id=f.get("feature_id"),
                epic_id=f.get("epic_id"),
                title=f.get("title", ""),
                description=f.get("description"),
                status=RequirementStatus.proposed,
                source=RequirementSource(
                    source_type=SourceType(f.get("source", {}).get("source_type", "inference")),
                    confidence=float(f.get("source", {}).get("confidence", 0.9))
                )
            ))
            
        stories = []
        for s in repaired_json.get("user_stories", []):
            stories.append(UserStory(
                story_id=s.get("story_id"),
                feature_id=s.get("feature_id"),
                title=s.get("title", ""),
                description=s.get("description", ""),
                linked_requirement_ids=s.get("linked_requirement_ids", []),
                status=RequirementStatus.proposed,
                source=RequirementSource(
                    source_type=SourceType(s.get("source", {}).get("source_type", "inference")),
                    confidence=float(s.get("source", {}).get("confidence", 0.9))
                )
            ))
            
        acs = []
        for ac in repaired_json.get("acceptance_criteria", []):
            acs.append(AcceptanceCriterion(
                ac_id=ac.get("ac_id"),
                story_id=ac.get("story_id"),
                statement=ac.get("statement", ""),
                status=RequirementStatus.proposed,
                source=RequirementSource(
                    source_type=SourceType(ac.get("source", {}).get("source_type", "inference")),
                    confidence=float(ac.get("source", {}).get("confidence", 0.9))
                )
            ))
            
        doc.epics = epics
        doc.features = features
        doc.user_stories = stories
        doc.acceptance_criteria = acs
        
        final_quality = requirement_validator.validate_requirement_document(doc)
        doc.quality_result = final_quality
        
        return {
            "document": doc,
            "phase": "awaiting_finalization_approval",
            "user_feedback": None
        }
    except Exception as e:
        print(f"[Requirement Agent] Finalization error: {e}")
        return {"phase": "failed", "missing_info": [f"Finalization failed: {str(e)}"]}


def awaiting_finalization_approval(state: AgentState) -> Dict[str, Any]:
    """Node: Pauses graph using interrupt to wait for human review of finalized backlog."""
    print("[Requirement Node] Interrupting for Finalization Approval...")
    feedback = interrupt({
        "stage": "FINALIZATION",
        "message": "Please review the finalized requirements and flat backlog.",
        "document": state.get("document").dict() if state.get("document") else None
    })
    return {"user_feedback": feedback}


def post_finalization_handler(state: AgentState) -> Dict[str, Any]:
    """Node: Processes finalization approval/rejection."""
    feedback = state.get("user_feedback") or {}
    status = feedback.get("status")
    comments = feedback.get("comments", "")
    
    if status == "APPROVED":
        print("[Requirement Node] Finalization Approved! Completed!")
        return {"phase": "completed"}
    else:
        print(f"[Requirement Node] Finalization Rejected: {comments}")
        return {
            "phase": "ready_for_finalization",
            "user_feedback": feedback
        }

# ----------------- EDGES & ROUTING -----------------

def route_after_input(state: AgentState) -> str:
    phase = state.get("phase")
    if phase == "failed":
        return END
    return "conversation_state_manager"

def route_after_prompt(state: AgentState) -> str:
    phase = state.get("phase")
    if phase == "processing":
        return "extraction_node"
    return END

def route_after_extraction(state: AgentState) -> str:
    phase = state.get("phase")
    if phase == "failed":
        return END
    return "awaiting_extraction_approval"

def route_after_extraction_approval(state: AgentState) -> str:
    phase = state.get("phase")
    if phase == "gap_detection_running":
        return "gap_detector_node"
    return "conversation_state_manager"

def route_after_gap(state: AgentState) -> str:
    phase = state.get("phase")
    if phase == "failed":
        return END
    return "awaiting_gap_approval"

def route_after_gap_approval(state: AgentState) -> str:
    phase = state.get("phase")
    if phase == "waiting_for_clarification":
        return "waiting_for_clarification"
    elif phase == "validating":
        return "validation_node"
    else:
        return "gap_detector_node"

def route_after_validation(state: AgentState) -> str:
    phase = state.get("phase")
    if phase == "validation_failed":
        return "waiting_for_clarification"
    return "awaiting_validation_approval"

def route_after_validation_approval(state: AgentState) -> str:
    phase = state.get("phase")
    if phase == "ready_for_finalization":
        return "finalizer_node"
    else:
        return "validation_node"

def route_after_finalization(state: AgentState) -> str:
    phase = state.get("phase")
    if phase == "failed":
        return END
    return "awaiting_finalization_approval"

def route_after_finalization_approval(state: AgentState) -> str:
    phase = state.get("phase")
    if phase == "completed":
        return END
    else:
        return "finalizer_node"


# ----------------- GRAPH COMPILATION -----------------

workflow = StateGraph(AgentState)

workflow.add_node("input_validation", input_validation)
workflow.add_node("conversation_state_manager", conversation_state_manager)
workflow.add_node("prompt_generator_and_llm", prompt_generator_and_llm)
workflow.add_node("extraction_node", extraction_node)
workflow.add_node("awaiting_extraction_approval", awaiting_extraction_approval)
workflow.add_node("post_extraction_handler", post_extraction_handler)
workflow.add_node("gap_detector_node", gap_detector_node)
workflow.add_node("awaiting_gap_approval", awaiting_gap_approval)
workflow.add_node("post_gap_handler", post_gap_handler)
workflow.add_node("waiting_for_clarification", waiting_for_clarification)
workflow.add_node("validation_node", validation_node)
workflow.add_node("awaiting_validation_approval", awaiting_validation_approval)
workflow.add_node("post_validation_handler", post_validation_handler)
workflow.add_node("finalizer_node", finalizer_node)
workflow.add_node("awaiting_finalization_approval", awaiting_finalization_approval)
workflow.add_node("post_finalization_handler", post_finalization_handler)

workflow.set_entry_point("input_validation")

workflow.add_conditional_edges("input_validation", route_after_input)
workflow.add_edge("conversation_state_manager", "prompt_generator_and_llm")
workflow.add_conditional_edges("prompt_generator_and_llm", route_after_prompt)

workflow.add_conditional_edges("extraction_node", route_after_extraction)
workflow.add_edge("awaiting_extraction_approval", "post_extraction_handler")
workflow.add_conditional_edges("post_extraction_handler", route_after_extraction_approval)

workflow.add_conditional_edges("gap_detector_node", route_after_gap)
workflow.add_edge("awaiting_gap_approval", "post_gap_handler")
workflow.add_conditional_edges("post_gap_handler", route_after_gap_approval)

workflow.add_edge("waiting_for_clarification", "conversation_state_manager")

workflow.add_conditional_edges("validation_node", route_after_validation)
workflow.add_edge("awaiting_validation_approval", "post_validation_handler")
workflow.add_conditional_edges("post_validation_handler", route_after_validation_approval)

workflow.add_conditional_edges("finalizer_node", route_after_finalization)
workflow.add_edge("awaiting_finalization_approval", "post_finalization_handler")
workflow.add_conditional_edges("post_finalization_handler", route_after_finalization_approval)

compiled_graph = workflow.compile(checkpointer=sqlite_checkpointer)
