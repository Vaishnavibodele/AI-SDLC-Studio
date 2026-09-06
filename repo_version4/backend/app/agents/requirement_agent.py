import re
import json
import os
from typing import Dict, Any, List, Optional, TypedDict, Tuple
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
    PROCESS_CLARIFICATION_PROMPT,
    CONFLICT_DETECTOR_PROMPT
)

EXTRACTION_SYSTEM_PROMPT = """
You are a Senior Business Analyst. Your task is to analyze the gathered Requirement Memory and conversation history, and extract a complete, canonical ProjectDocument.

Requirement Memory collected:
{memory_json}

CRITICAL EVIDENCE GROUNDING MANDATE:
1. Every requirement MUST be grounded directly in the provided Requirement Memory, conversation history, or human clarification answers.
2. DO NOT introduce unrequested standard features (e.g. user authentication/OAuth, payment gateways, SendGrid email notifications, TLS 1.3, password resets, admin dashboards) UNLESS explicitly requested or mentioned in the user input.
3. Keep the target domain, actors, and workflows strictly specific to the user's project statement.
4. For every requirement, include a precise 'source' object:
   - source_type: "user_input" if explicitly stated, "human_clarification" if provided in a clarification answer, "inference" if strongly implied by the domain statement.
   - source_text: The exact sentence, phrase, or quote from the user text/answer that provides evidence for this requirement.
   - confidence: 1.0 for explicit user input and human clarification, 0.7-0.9 for strong domain inferences.

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
   - source: Provenance object: {{ "source_type": "user_input"|"human_clarification"|"inference"|"assumption", "source_reference": null, "source_text": "...", "confidence": 0.9 }}
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
      "name": "Core Operational Process",
      "actor": "Primary Actor",
      "trigger": "Actor initiates operation",
      "steps": ["Step 1", "Step 2"]
    }}
  ],
  "requirements": [
    {{
      "requirement_id": "REQ-001",
      "title": "Core System Capability",
      "statement": "The system shall perform core operational processing based on user requirements.",
      "requirement_type": "functional",
      "actor": "Primary Actor",
      "priority": "must_have",
      "status": "proposed",
      "source": {{
        "source_type": "user_input",
        "source_reference": null,
        "source_text": "Quote or snippet from user text",
        "confidence": 1.0
      }}
    }}
  ],
  "assumptions": ["..."],
  "constraints": ["..."],
  "dependencies": ["..."],
  "risks": ["..."]
}}

Do not write markdown block ticks (no ```) or any preamble/explanation. Return ONLY the raw valid JSON.
"""

GAP_DETECTOR_SYSTEM_PROMPT = """
You are a Senior Systems QA & Requirement Reasoning Specialist.
Your task is to analyze the extracted project document and requirements to identify genuine ambiguities, missing operational parameters, or contradictions that materially affect THIS specific software project.

STRICT ZERO-HARDCODING DIRECTIVES:
1. DO NOT ask generic questions about common standard features (e.g. "Do you want login?", "Do you want payments?", "Do you want notifications?") UNLESS the project context specifically mentions or implies those domain operations.
2. Formulate context-specific questions derived directly from THIS project's problem statement, actors, and workflows.
3. Determine dynamic priority based on impact:
   - "high": Unresolved ambiguity that blocks core requirement specification or workflow definition.
   - "medium": Operational parameter or boundary rule needing clarification.
   - "low": Optional formatting or non-critical preference.
4. DO NOT re-generate questions that have already been asked or answered.

Project Context & Requirements:
{requirements_json}

Previously Asked / Answered Questions:
{existing_questions_json}

Return a raw JSON object containing a list of dynamic clarification questions:
{{
  "gaps": [
    {{
      "id": "GAP-001",
      "question": "Dynamic question generated specifically from this project's context",
      "reason": "Why this information is required for requirement specification",
      "related_requirements": ["REQ-001"],
      "priority": "high",
      "status": "pending"
    }}
  ]
}}

Do not write markdown block ticks (no ```) or any preamble/explanation. Return ONLY the raw valid JSON.
"""

FINALIZER_SYSTEM_PROMPT = """
You are a Senior Architect and Product Owner. Your task is to synthesize a flat backlog (Epics, Features, User Stories, and Acceptance Criteria) from the approved requirements.

Approved Requirements:
{requirements_json}

CRITICAL GROUNDING MANDATE:
1. All backlog items MUST be directly derived from the approved requirements.
2. DO NOT introduce unrequested generic features (e.g. login, payment gateways, email notifications) unless they are in the approved requirements.

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
      "description": "As a primary actor, I want to execute the specified task so that the business outcome is achieved.",
      "linked_requirement_ids": ["REQ-001"],
      "status": "proposed",
      "source": {{ "source_type": "inference", "confidence": 0.9 }}
    }}
  ],
  "acceptance_criteria": [
    {{
      "ac_id": "AC-001",
      "story_id": "US-001",
      "statement": "Given valid inputs, when the operation executes, then the result is stored successfully.",
      "status": "proposed",
      "source": {{ "source_type": "inference", "confidence": 0.9 }}
    }}
  ]
}}

Do not write markdown block ticks or any preamble/explanation. Return ONLY the raw valid JSON.
"""

MAX_CLARIFICATION_QUESTIONS = int(os.getenv("MAX_CLARIFICATION_QUESTIONS", "3"))

def is_duplicate_question(new_q_text: str, existing_questions: List[Dict[str, Any]]) -> bool:
    """Checks if a newly generated question is semantically identical to an existing question."""
    new_tokens = set(re.findall(r'\w+', new_q_text.lower()))
    if not new_tokens:
        return False
    for eq in existing_questions:
        eq_text = eq.get("question", "") or eq.get("suggested_question", "")
        eq_tokens = set(re.findall(r'\w+', eq_text.lower()))
        if eq_tokens:
            overlap = len(new_tokens.intersection(eq_tokens)) / max(len(new_tokens), len(eq_tokens))
            if overlap > 0.75:
                return True
    return False

def gap_detector_node(state: AgentState) -> Dict[str, Any]:
    """Node: Runs LLM gap detector on extracted requirements to dynamically generate contextual clarification questions."""
    print("[Requirement Node] Running Dynamic Gap & Ambiguity Detection...")
    doc = state.get("document")
    llm = get_llm()
    
    existing_questions = state.get("clarification_questions", []) or []
    reqs_json = json.dumps([r.dict() for r in doc.requirements], indent=2) if doc and doc.requirements else "[]"
    existing_json = json.dumps(existing_questions, indent=2)
    
    try:
        response = llm.invoke([
            {"role": "system", "content": GAP_DETECTOR_SYSTEM_PROMPT.format(
                requirements_json=reqs_json,
                existing_questions_json=existing_json
            )},
            {"role": "user", "content": "Identify missing details, ambiguities, and operational rules for this project."}
        ])
        
        repaired_json = json_repair.repair_json(get_content_text(response))
        raw_gaps = repaired_json.get("gaps", [])
        
        clarification_questions = list(existing_questions)
        new_gaps = []
        
        for g in raw_gaps:
            q_text = g.get("question") or g.get("suggested_question") or g.get("description", "")
            if not q_text or is_duplicate_question(q_text, clarification_questions):
                continue
                
            q_id = g.get("id") or f"GAP-{len(clarification_questions)+1:03d}"
            q_obj = {
                "id": q_id,
                "question": q_text,
                "reason": g.get("reason") or g.get("description") or "Clarification needed for requirements engineering.",
                "related_requirements": g.get("related_requirements", []),
                "priority": g.get("priority", "high" if g.get("blocking") else "medium"),
                "status": "pending",
                "answer": None
            }
            clarification_questions.append(q_obj)
            new_gaps.append(q_obj)
            
        from ..schemas import ClarificationQuestion
        doc.clarification_questions = [ClarificationQuestion(**q) for q in clarification_questions]
        
        return {
            "gaps": new_gaps,
            "clarification_questions": clarification_questions,
            "document": doc,
            "phase": "awaiting_gap_approval",
            "user_feedback": None
        }
    except Exception as e:
        import traceback
        print(f"[Requirement Agent] Gap detection notice ({e}). Traceback:\n{traceback.format_exc()}")
        return {
            "gaps": [],
            "clarification_questions": existing_questions,
            "phase": "awaiting_gap_approval",
            "user_feedback": None
        }


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
        questions = state.get("clarification_questions", [])
        pending_questions = [q for q in questions if q.get("status") == "pending" and q.get("priority") in ["high", "medium"]]
        if pending_questions:
            return {"phase": "waiting_for_clarification"}
        else:
            return {"phase": "validating"}
    else:
        print(f"[Requirement Node] Gaps Rejected: {comments}")
        return {
            "phase": "gap_detection_running",
            "user_feedback": feedback
        }


def process_clarification_answer_text(
    doc: ProjectDocument,
    question_text: str,
    answer_text: str,
    user_texts: List[str]
) -> Tuple[ProjectDocument, List[str]]:
    """Iteratively updates requirements based on human answer evidence without wiping valid requirements."""
    llm = get_llm()
    reqs_json = json.dumps([r.dict() for r in doc.requirements], indent=2) if (doc and doc.requirements) else "[]"
    conflicts = []
    
    # 1. Check for contradictions
    try:
        original_input = " ".join(user_texts)
        answers_json = json.dumps([{"question": question_text, "answer": answer_text}])
        conflict_res = llm.invoke([
            {"role": "system", "content": CONFLICT_DETECTOR_PROMPT.format(
                original_input=original_input,
                answers_json=answers_json,
                requirements_json=reqs_json
            )},
            {"role": "user", "content": "Detect direct contradictions."}
        ])
        repaired_conflict = json_repair.repair_json(get_content_text(conflict_res))
        conflicts = repaired_conflict.get("conflicts", [])
    except Exception as e:
        print(f"[Requirement Agent] Conflict detection notice ({e})")

    # 2. Update requirements using human clarification as evidence
    try:
        response = llm.invoke([
            {"role": "system", "content": PROCESS_CLARIFICATION_PROMPT.format(
                question_text=question_text,
                answer_text=answer_text,
                requirements_json=reqs_json
            )},
            {"role": "user", "content": "Update requirements with this clarification evidence."}
        ])
        
        repaired_json = json_repair.repair_json(get_content_text(response))
        updated_reqs_data = repaired_json.get("requirements", [])
        
        if updated_reqs_data:
            existing_req_ids = {r.requirement_id for r in doc.requirements}
            new_req_list = []
            
            for ur in updated_reqs_data:
                req_id = ur.get("requirement_id") or f"REQ-F{len(new_req_list)+1:03d}"
                req = Requirement(
                    requirement_id=req_id,
                    title=ur.get("title", "Clarified Requirement"),
                    statement=ur.get("statement", ""),
                    requirement_type=ur.get("requirement_type", "functional"),
                    actor=ur.get("actor"),
                    priority=ur.get("priority", "must_have"),
                    status=RequirementStatus.proposed,
                    source=RequirementSource(
                        source_type=SourceType.human_clarification,
                        source_text=answer_text,
                        confidence=1.0
                    )
                )
                new_req_list.append(req)
                
            # Retain non-conflicting existing requirements that were not overwritten
            updated_ids = {r.requirement_id for r in new_req_list}
            for er in doc.requirements:
                if er.requirement_id not in updated_ids:
                    new_req_list.append(er)
                    
            doc.requirements = new_req_list
    except Exception as e:
        print(f"[Requirement Agent] Requirement update notice ({e}). Creating requirement from answer...")
        new_req = Requirement(
            requirement_id=f"REQ-F{len(doc.requirements)+1:03d}",
            title="Human Clarified Rule",
            statement=f"System shall fulfill: {answer_text}",
            requirement_type="functional",
            priority="must_have",
            status=RequirementStatus.proposed,
            source=RequirementSource(
                source_type=SourceType.human_clarification,
                source_text=answer_text,
                confidence=1.0
            )
        )
        doc.requirements.append(new_req)

    return doc, conflicts


def waiting_for_clarification(state: AgentState) -> Dict[str, Any]:
    """Node: Suspends graph using interrupt to wait for human answers to clarification questions."""
    print("[Requirement Node] Suspending for user clarification answers...")
    doc = state.get("document")
    questions = state.get("clarification_questions", []) or []
    pending_questions = [q for q in questions if q.get("status") == "pending"]
    
    if not pending_questions:
        print("[Requirement Node] No pending clarification questions. Moving to validation...")
        return {"phase": "validating"}
        
    active_questions = pending_questions[:MAX_CLARIFICATION_QUESTIONS]
    
    questions_list = [f"- {q['id']}: {q['question']} (Reason: {q['reason']})" for q in active_questions]
    questions_text = "I have identified some open clarification questions. Please answer to proceed:\n" + "\n".join(questions_list)
    
    messages = list(state.get("messages", []))
    messages.append({
        "sender": "agent",
        "text": questions_text
    })
    
    # Genuine HITL Interrupt
    feedback = interrupt({
        "stage": "CLARIFICATION",
        "message": questions_text,
        "questions": active_questions
    })
    
    answer_text = feedback.get("answer", "")
    question_id = feedback.get("question_id")
    
    user_texts = [m["text"] for m in messages if m.get("sender") == "user"]
    
    answered_q_text = "Clarification question"
    for q in questions:
        if (question_id and q.get("id") == question_id) or (q in active_questions and not q.get("answer")):
            q["status"] = "answered"
            q["answer"] = answer_text
            answered_q_text = q["question"]
            break
            
    answers = list(state.get("clarification_answers", []) or [])
    answers.append({"question": answered_q_text, "answer": answer_text})
    
    messages.append({
        "sender": "user",
        "text": f"Clarification Answer ({answered_q_text}):\n{answer_text}"
    })
    
    doc, conflicts = process_clarification_answer_text(doc, answered_q_text, answer_text, user_texts)
    
    if conflicts:
        doc.conflicts = list(set((doc.conflicts or []) + conflicts))
        
    return {
        "messages": messages,
        "document": doc,
        "clarification_questions": questions,
        "clarification_answers": answers,
        "conflicts": doc.conflicts,
        "phase": "processing",
        "user_feedback": None
    }


def validation_node(state: AgentState) -> Dict[str, Any]:
    """Node: Runs quality validator and transitions to explicit approval interrupt."""
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
        print("[Requirement Node] Validation PASSED. Pausing for Explicit Human Approval...")
        return {
            "document": doc,
            "phase": "awaiting_validation_approval"
        }


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


def build_fallback_memory(messages: List[Dict[str, Any]], existing_memory: Optional[RequirementMemory] = None) -> RequirementMemory:
    """Deterministic NLP rule-based fallback extractor grounded strictly in user input text."""
    user_texts = [m["text"].strip() for m in messages if isinstance(m, dict) and m.get("sender") == "user" and m.get("text")]
    combined_text = " ".join(user_texts).strip()
    
    if not combined_text:
        combined_text = "Software application system."
        
    summary = combined_text
    if len(summary) > 250:
        sentences = [s.strip() for s in re.split(r'[.!?]', summary) if s.strip()]
        summary = ". ".join(sentences[:2]) + "."
        
    goals_text = f"Fulfill application capabilities and processing for: {summary[:120]}"
    
    # Dynamically extract target users/actors
    target_users = []
    actor_matches = re.findall(r'\b([a-zA-Z]+s?)\s+(?:can|shall|should|may|able to)\b', combined_text, re.IGNORECASE)
    for w in actor_matches:
        w_lower = w.lower()
        if w_lower not in ['system', 'application', 'platform', 'which', 'that', 'where', 'it', 'they', 'you', 'we', 'user', 'users']:
            target_users.append(w.capitalize())
    if not target_users:
        target_users = ["User"]
    target_users = list(dict.fromkeys(target_users))
    
    # Dynamically extract functional requirement clauses
    func_reqs = []
    sentences = [s.strip() for s in re.split(r'[.;!\n]', combined_text) if s.strip()]
    for s in sentences:
        sub_parts = [p.strip() for p in re.split(r'\bwhere\b', s, flags=re.IGNORECASE) if p.strip()]
        for sub in sub_parts:
            actor_clauses = re.split(r'\b(?=[a-zA-Z]+s?\s+can\b)', sub, flags=re.IGNORECASE)
            for ac in actor_clauses:
                ac_str = ac.strip()
                if not ac_str: continue
                m = re.search(r'\b([a-zA-Z]+s?)\s+can\s+(.*)', ac_str, re.IGNORECASE)
                if m:
                    act_word = m.group(1).capitalize()
                    verbs_text = re.sub(r'^(?:and|or|\,)\s*', '', m.group(2).strip(), flags=re.IGNORECASE)
                    actions = [a.strip() for a in re.split(r'\b(?:and|or)\b|,', verbs_text) if a.strip()]
                    shared_obj = ''
                    if len(actions) > 1 and len(actions[-1].split()) > 1:
                        shared_obj = ' '.join(actions[-1].split()[1:])
                    for act in actions:
                        act_clean = re.sub(r'^(?:and|or)\s*', '', act, flags=re.IGNORECASE).strip()
                        if not act_clean: continue
                        stmt = f"{act_word} can {act_clean} {shared_obj}." if (len(act_clean.split()) == 1 and shared_obj) else f"{act_word} can {act_clean}."
                        stmt = re.sub(r'\.\.+', '.', stmt)
                        if stmt not in func_reqs and len(stmt) > 8:
                            func_reqs.append(stmt)
                else:
                    clean_s = ac_str.strip()
                    if clean_s and len(clean_s) > 10:
                        if not clean_s.endswith('.'): clean_s += '.'
                        if clean_s not in func_reqs: func_reqs.append(clean_s)
                        
    if not func_reqs:
        func_reqs = [f"System shall fulfill user request: {combined_text[:150]}."]
        
    non_func_reqs = ["Not specified in the provided requirements."]
    constraints = ["Not specified in the provided requirements."]
    assumptions = ["Not specified in the provided requirements."]
    acceptance_criteria = [f"Given user action, system fulfills {fr}" for fr in func_reqs[:5]]
    
    if existing_memory:
        if existing_memory.project_summary:
            summary = existing_memory.project_summary
        if existing_memory.business_goals:
            goals_text = existing_memory.business_goals
        if existing_memory.functional_requirements:
            for fr in existing_memory.functional_requirements:
                if fr not in func_reqs:
                    func_reqs.insert(0, fr)
        if existing_memory.target_users:
            target_users = list(dict.fromkeys(existing_memory.target_users + target_users))

    return RequirementMemory(
        project_summary=summary,
        business_goals=goals_text,
        target_users=target_users,
        functional_requirements=func_reqs,
        non_functional_requirements=non_func_reqs,
        constraints=constraints,
        assumptions=assumptions,
        acceptance_criteria=acceptance_criteria,
        open_questions=[]
    )


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
        memory_data = json_repair.repair_json(get_content_text(response))
        updated_memory = RequirementMemory(**memory_data)
        
        # Ensure fallback items if empty fields
        if not updated_memory.project_summary or not updated_memory.functional_requirements:
            fallback = build_fallback_memory(messages, state.get("memory"))
            if not updated_memory.project_summary:
                updated_memory.project_summary = fallback.project_summary
            if not updated_memory.business_goals:
                updated_memory.business_goals = fallback.business_goals
            if not updated_memory.functional_requirements:
                updated_memory.functional_requirements = fallback.functional_requirements
            if not updated_memory.non_functional_requirements:
                updated_memory.non_functional_requirements = fallback.non_functional_requirements
            if not updated_memory.target_users:
                updated_memory.target_users = fallback.target_users
        
        return {
            "memory": updated_memory,
            "missing_info": []
        }
    except Exception as e:
        print(f"[Requirement Agent] LLM memory update exception ({e}). Utilizing deterministic memory fallback...")
        updated_memory = build_fallback_memory(messages, state.get("memory"))
        return {
            "memory": updated_memory,
            "missing_info": []
        }


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
        
    memory_json = json.dumps(memory.dict() if memory else {}, indent=2)
    try:
        llm = get_llm()
        response = llm.invoke([
            {"role": "system", "content": CHAT_AGENT_SYSTEM_PROMPT.format(memory_json=memory_json)},
            {"role": "user", "content": "Please generate the next question or reply."}
        ])
        reply_text = get_content_text(response).strip()
    except Exception as e:
        print(f"[Requirement Agent] Prompt LLM exception ({e}). Providing fallback chat reply...")
        reply_text = "I have analyzed your requirement input and generated the structured project requirements. You can inspect the Project Summary, Business Goals, and Functional Requirements in the panel on the right. Click Approve in the Gated Approval Pipeline when you are ready to compile the SRS document."
        
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
        print(f"[Requirement Agent] Extraction error ({e}). Utilizing fallback ProjectDocument from memory...")
        requirements = []
        if memory and memory.functional_requirements:
            for i, fr in enumerate(memory.functional_requirements):
                requirements.append(Requirement(
                    requirement_id=f"REQ-F{i+1:03d}",
                    title=fr[:50] + ("..." if len(fr) > 50 else ""),
                    statement=fr,
                    requirement_type="functional",
                    priority="must_have",
                    status=RequirementStatus.proposed,
                    source=RequirementSource(source_type=SourceType.user_input, source_text=fr, confidence=1.0)
                ))
        if memory and memory.non_functional_requirements:
            for i, nfr in enumerate(memory.non_functional_requirements):
                requirements.append(Requirement(
                    requirement_id=f"REQ-NF{i+1:03d}",
                    title=nfr[:50] + ("..." if len(nfr) > 50 else ""),
                    statement=nfr,
                    requirement_type="non_functional",
                    priority="must_have",
                    status=RequirementStatus.proposed,
                    source=RequirementSource(source_type=SourceType.user_input, source_text=nfr, confidence=1.0)
                ))
                
        if not requirements:
            fallback_stmt = memory.project_summary if (memory and memory.project_summary) else "Software system requirement processing."
            requirements = [
                Requirement(
                    requirement_id="REQ-F001",
                    title="Core Project Processing",
                    statement=f"The system shall execute operational requirements for: {fallback_stmt[:150]}",
                    requirement_type="functional",
                    priority="must_have",
                    status=RequirementStatus.proposed,
                    source=RequirementSource(source_type=SourceType.user_input, source_text=fallback_stmt[:150], confidence=1.0)
                )
            ]
            
        doc = ProjectDocument(
            project_id=project_id,
            version=1,
            project_summary=memory.project_summary if memory else "Project specification under analysis.",
            business_goals=[memory.business_goals] if memory and memory.business_goals else ["Not specified in the provided requirements."],
            problem_statement=memory.project_summary if memory else "Requirements specified by user input.",
            stakeholders=memory.target_users if (memory and memory.target_users) else ["Not specified in the provided requirements."],
            actors=memory.target_users if (memory and memory.target_users) else ["User"],
            workflows=[],
            requirements=requirements,
            assumptions=memory.assumptions if (memory and memory.assumptions) else ["Not specified in the provided requirements."],
            constraints=memory.constraints if (memory and memory.constraints) else ["Not specified in the provided requirements."],
            dependencies=[],
            risks=["Not specified in the provided requirements."]
        )
        
        return {
            "document": doc,
            "phase": "awaiting_extraction_approval",
            "user_feedback": None
        }


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
            
        if not epics and doc and doc.requirements:
            print("[Requirement Node] Synthesizing grounded Epics, Features, Stories, and ACs from requirements...")
            actor_reqs = {}
            for r in doc.requirements:
                if r.requirement_type != "functional":
                    continue
                # Exclude Non-Functional Requirements
                is_nfr = any(k in r.statement.lower() or k in (r.title or "").lower() for k in [
                    "response time", "latency", "https", "tls", "gdpr", "soc2", "security", "encryption", "sla", "uptime", "throughput", "concurrency"
                ])
                if is_nfr:
                    continue

                actor = r.actor or "User"
                if actor not in actor_reqs:
                    actor_reqs[actor] = []
                actor_reqs[actor].append(r)
                
            epic_count = 1
            feat_count = 1
            story_count = 1
            ac_count = 1
            
            for actor, req_group in actor_reqs.items():
                actor_sing = actor.rstrip('s') if actor.lower().endswith('s') and not actor.lower().endswith('ss') else actor
                if not actor_sing or actor_sing == "User":
                    actor_sing = "User"
                art = "an" if actor_sing and actor_sing[0].lower() in "aeiou" else "a"
                
                epic_id = f"EPIC-{epic_count:03d}"
                epic_title = f"{actor_sing} Operations & Workflow"
                epics.append(Epic(
                    epic_id=epic_id,
                    title=epic_title,
                    description=f"Epics covering functional operations for {actor}.",
                    status=RequirementStatus.proposed,
                    source=RequirementSource(source_type=SourceType.inference, confidence=1.0)
                ))
                epic_count += 1
                
                for r in req_group:
                    feat_id = f"FEAT-{feat_count:03d}"
                    clean_stmt = r.statement.rstrip('.').strip()
                    clean_action = re.sub(r'^(?:[a-zA-Z]+s?\s+can\s+)', '', clean_stmt, flags=re.IGNORECASE).strip()
                    action_clean = clean_action.lower()

                    features.append(Feature(
                        feature_id=feat_id,
                        epic_id=epic_id,
                        title=clean_action.capitalize()[:50],
                        description=clean_stmt,
                        status=RequirementStatus.proposed,
                        source=RequirementSource(source_type=SourceType.inference, confidence=1.0)
                    ))
                    feat_count += 1
                    
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

                    story_id = f"US-{story_count:03d}"
                    stories.append(UserStory(
                        story_id=story_id,
                        feature_id=feat_id,
                        title=f"As {art} {actor_sing}, I want to {action_clean}",
                        description=f"As {art} {actor_sing}, I want to {action_clean} so that I can {benefit}.",
                        linked_requirement_ids=[r.requirement_id],
                        status=RequirementStatus.proposed,
                        source=RequirementSource(source_type=SourceType.user_input, confidence=1.0)
                    ))
                    story_count += 1
                    
                    ac_id = f"AC-{ac_count:03d}"
                    acs.append(AcceptanceCriterion(
                        ac_id=ac_id,
                        story_id=story_id,
                        statement=f"{ac_given}, {ac_when}, {ac_then}",
                        status=RequirementStatus.proposed,
                        source=RequirementSource(source_type=SourceType.user_input, confidence=1.0)
                    ))
                    ac_count += 1
            
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
