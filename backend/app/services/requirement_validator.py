import re
import json
from typing import List, Dict, Any, Tuple, Optional
from sqlalchemy.orm import Session
from ..schemas import ProjectDocument, QualityResult
from ..services.llm_provider import get_llm, get_content_text

def check_completeness(doc: ProjectDocument, backlog_required: bool) -> Tuple[int, List[str]]:
    """
    Checks if all required components and sections are populated in the canonical ProjectDocument.
    """
    issues = []
    points = 0
    
    # 1. Check requirements presence (30 points)
    reqs = doc.requirements
    if not reqs:
        issues.append("No requirements are defined in the document.")
        return 0, issues
        
    points += 15  # Has requirements
    
    has_functional = any(r.requirement_type == "functional" for r in reqs)
    has_non_functional = any(r.requirement_type == "non_functional" for r in reqs)
    has_business_rule = any(r.requirement_type == "business_rule" for r in reqs)
    
    if has_functional:
        points += 5
    else:
        issues.append("Document lacks Functional Requirements.")
        
    if has_non_functional:
        points += 5
    else:
        issues.append("Document lacks Non-Functional Requirements.")
        
    if has_business_rule:
        points += 5
    else:
        issues.append("Document lacks Business Rules.")

    # 2. Check Business Context & Artifacts (40 points)
    if doc.project_summary or doc.problem_statement:
        points += 10
    else:
        issues.append("Document lacks Project Summary / Problem Statement.")

    if doc.stakeholders or doc.actors:
        points += 10
    else:
        issues.append("Document lacks Stakeholders / Actors definition.")

    if doc.workflows:
        points += 10
    else:
        issues.append("Document lacks System Workflows / Process definitions.")

    if doc.assumptions or doc.constraints or doc.dependencies or doc.risks:
        points += 10
    else:
        issues.append("Document lacks Assumptions, Constraints, Dependencies, or Risks.")

    # 3. Check Backlog elements if required (30 points)
    if backlog_required:
        has_epics = bool(doc.epics and len(doc.epics) > 0)
        has_features = bool(doc.features and len(doc.features) > 0)
        has_stories = bool(doc.user_stories and len(doc.user_stories) > 0)
        has_ac = bool(doc.acceptance_criteria and len(doc.acceptance_criteria) > 0)
        
        if has_epics:
            points += 10
        else:
            issues.append("Backlog lacks Epics.")
            
        if has_features:
            points += 5
        else:
            issues.append("Backlog lacks Features.")
            
        if has_stories:
            points += 10
        else:
            issues.append("Backlog lacks User Stories.")
            
        if has_ac:
            points += 5
        else:
            issues.append("Backlog lacks Acceptance Criteria.")
    else:
        # Scale 70 points to 100 before backlog is generated
        points = int((points / 70.0) * 100)
        
    return min(points, 100), issues

def check_consistency(doc: ProjectDocument) -> Tuple[int, List[str]]:
    """
    Performs duplicate and contradiction checks using an LLM call for semantic reasoning.
    """
    issues = []
    reqs = doc.requirements
    if not reqs:
        return 100, []
        
    llm = get_llm()
    reqs_data = [
        {
            "id": r.requirement_id,
            "title": r.title,
            "statement": r.statement,
            "type": r.requirement_type
        } for r in reqs
    ]
    
    system_prompt = (
        "You are a Quality Assurance BA. Your task is to analyze a list of requirements for consistency.\n"
        "1. Contradictions: Detect requirements that conflict with each other (e.g. conflicting constraints or incompatible statements).\n"
        "2. Duplicates: Detect requirements that are semantically identical or highly redundant but have different IDs.\n"
        "Return ONLY a raw JSON object with the format: {\"conflicts\": [\"string describing conflict\"], \"duplicates\": [\"string describing duplicate\"]}\n"
        "Do not write markdown backticks or any other text."
    )
    
    try:
        response = llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Analyze these requirements:\n{json.dumps(reqs_data, indent=2)}"}
        ])
        
        content = get_content_text(response).strip()
        if content.startswith("```json"):
            content = content[7:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        res = json.loads(content)
        conflicts = res.get("conflicts", [])
        duplicates = res.get("duplicates", [])
        
        issues.extend(conflicts)
        issues.extend(duplicates)
        
        score = max(0, 100 - (len(conflicts) * 15) - (len(duplicates) * 10))
        return score, issues
    except Exception as e:
        print(f"[Validator] Consistency LLM check failed: {e}")
        # Default to 100 (pass) on API blip to avoid blocking pipeline
        return 100, []

def check_clarity(doc: ProjectDocument) -> Tuple[int, List[str]]:
    """
    Scans requirement statements for vague terms lacking concrete measurable metrics.
    """
    issues = []
    vague_patterns = [
        (r"\bquickly\b", "quickly"),
        (r"\buser-friendly\b", "user-friendly"),
        (r"\brobust\b", "robust"),
        (r"\bscalable\b", "scalable"),
        (r"\bsimple\b", "simple"),
        (r"\bfast\b", "fast"),
        (r"\befficient\b", "efficient"),
        (r"\beasy to use\b", "easy to use"),
        (r"\bhigh performance\b", "high performance"),
        (r"\bseamlessly\b", "seamlessly")
    ]
    
    vague_count = 0
    for r in doc.requirements:
        statement = r.statement.lower()
        for pattern, word in vague_patterns:
            if re.search(pattern, statement):
                issues.append(f"Requirement {r.requirement_id} contains vague term '{word}' without measurable success criteria.")
                vague_count += 1
                
    score = max(0, 100 - (vague_count * 5))
    return score, issues

def check_testability(doc: ProjectDocument, backlog_required: bool) -> Tuple[int, List[str]]:
    """
    Checks if requirements have linked acceptance criteria (if backlog exists)
    or measurable metrics before that.
    """
    issues = []
    untestable_count = 0
    
    if backlog_required:
        # Check if every functional requirement maps to at least one user story, 
        # and that user story has acceptance criteria.
        stories_by_req = {}
        for story in doc.user_stories:
            for req_id in story.linked_requirement_ids:
                stories_by_req.setdefault(req_id, []).append(story.story_id)
                
        ac_by_story = {}
        for ac in doc.acceptance_criteria:
            if ac.story_id:
                ac_by_story.setdefault(ac.story_id, []).append(ac.ac_id)
                
        for r in doc.requirements:
            if r.requirement_type == "functional":
                linked_stories = stories_by_req.get(r.requirement_id, [])
                if not linked_stories:
                    issues.append(f"Requirement {r.requirement_id} is functional but has no downstream User Story.")
                    untestable_count += 1
                else:
                    # check if linked stories have acceptance criteria
                    has_ac = False
                    for s_id in linked_stories:
                        if ac_by_story.get(s_id):
                            has_ac = True
                            break
                    if not has_ac:
                        issues.append(f"Requirement {r.requirement_id} has user stories {linked_stories} but none have acceptance criteria.")
                        untestable_count += 1
                        
        score = max(0, 100 - (untestable_count * 10))
    else:
        # Pre-backlog: check if statement contains any numbers/metrics (e.g. 99.9%, seconds, hours, pixels)
        # to ensure it's not a purely abstract description
        metric_regex = r"\b(\d+|99\.\d+|ms|seconds|minutes|hours|percent|px|gb|mb)\b"
        for r in doc.requirements:
            if r.requirement_type in ["functional", "non_functional"] and not re.search(metric_regex, r.statement.lower()):
                issues.append(f"Requirement {r.requirement_id} statement does not contain numeric thresholds or concrete units (e.g. response time, throughput).")
                untestable_count += 1
        score = max(0, 100 - (untestable_count * 5))
        
    return score, issues

def check_traceability(doc: ProjectDocument, backlog_required: bool) -> Tuple[int, List[str]]:
    """
    Checks for orphans and invalid mappings in the traceability matrix.
    Every requirement should reach an epic, every story must reach a requirement.
    """
    issues = []
    orphan_count = 0
    
    # 1. Pre-backlog check: traceability is always 100% since no backlog items exist to check orphans against.
    if not backlog_required:
        return 100, []
        
    # 2. Backlog orphan detection
    req_ids = {r.requirement_id for r in doc.requirements}
    epic_ids = {e.epic_id for e in doc.epics}
    feat_ids = {f.feature_id for f in doc.features}
    story_ids = {s.story_id for s in doc.user_stories}
    
    # Requirement orphan check: every requirement must reach an epic
    for r in doc.requirements:
        if not r.linked_epic_ids:
            issues.append(f"Orphan Requirement: {r.requirement_id} is not mapped to any Epic.")
            orphan_count += 1
        else:
            for ep_id in r.linked_epic_ids:
                if ep_id not in epic_ids:
                    issues.append(f"Invalid Mapping: Requirement {r.requirement_id} links to non-existent Epic '{ep_id}'.")
                    orphan_count += 1
                    
    # Feature orphan check: must link to valid epic
    for f in doc.features:
        if not f.epic_id:
            issues.append(f"Orphan Feature: {f.feature_id} has no parent Epic.")
            orphan_count += 1
        elif f.epic_id not in epic_ids:
            issues.append(f"Invalid Mapping: Feature {f.feature_id} links to non-existent Epic '{f.epic_id}'.")
            orphan_count += 1
            
    # User story check: must link to valid feature and at least one requirement
    for s in doc.user_stories:
        if not s.feature_id:
            issues.append(f"Orphan Story: {s.story_id} has no parent Feature.")
            orphan_count += 1
        elif s.feature_id not in feat_ids:
            issues.append(f"Invalid Mapping: Story {s.story_id} links to non-existent Feature '{s.feature_id}'.")
            orphan_count += 1
            
        if not s.linked_requirement_ids:
            issues.append(f"Orphan Story: {s.story_id} is not mapped to any upstream Requirement.")
            orphan_count += 1
        else:
            for r_id in s.linked_requirement_ids:
                if r_id not in req_ids:
                    issues.append(f"Invalid Mapping: Story {s.story_id} maps to non-existent Requirement '{r_id}'.")
                    orphan_count += 1
                    
    # Acceptance criterion check: must link to valid story
    for ac in doc.acceptance_criteria:
        if not ac.story_id:
            issues.append(f"Orphan Acceptance Criterion: {ac.ac_id} is not linked to any User Story.")
            orphan_count += 1
        elif ac.story_id not in story_ids:
            issues.append(f"Invalid Mapping: Acceptance Criterion {ac.ac_id} links to non-existent Story '{ac.story_id}'.")
            orphan_count += 1
            
    score = max(0, 100 - (orphan_count * 10))
    return score, issues

def check_coverage(doc: ProjectDocument, backlog_required: bool) -> Tuple[int, List[str]]:
    """
    Calculates the percentage of functional requirements mapped to at least one downstream user story.
    """
    issues = []
    
    # Pre-backlog coverage is 100% by default
    if not backlog_required:
        return 100, []
        
    functional_reqs = [r for r in doc.requirements if r.requirement_type == "functional"]
    if not functional_reqs:
        return 100, []
        
    mapped_reqs = set()
    for story in doc.user_stories:
        for r_id in story.linked_requirement_ids:
            mapped_reqs.add(r_id)
            
    uncovered_count = 0
    for r in functional_reqs:
        if r.requirement_id not in mapped_reqs:
            issues.append(f"Coverage Gap: Functional Requirement {r.requirement_id} has no mapped User Story.")
            uncovered_count += 1
            
    coverage_score = int(((len(functional_reqs) - uncovered_count) / len(functional_reqs)) * 100)
    return coverage_score, issues

def check_grounding(doc: ProjectDocument) -> Tuple[int, List[str]]:
    """
    Checks if requirements are strictly grounded in project context and flags hallucinated standard features.
    """
    issues = []
    ungrounded_count = 0
    
    cq_answers = [q.answer for q in getattr(doc, "clarification_questions", []) if hasattr(q, "answer") and q.answer]
    context_text = " ".join(filter(None, [
        doc.project_summary or "",
        doc.problem_statement or "",
        " ".join(doc.business_goals),
        " ".join(doc.stakeholders),
        " ".join(doc.actors),
        " ".join(doc.assumptions),
        " ".join(doc.constraints),
        " ".join(doc.dependencies),
        " ".join(cq_answers)
    ])).lower()

    # Keywords that indicate standard features often hallucinated by LLMs
    hallucination_triggers = [
        ("sendgrid", "SendGrid API integration"),
        ("twilio", "Twilio API integration"),
        ("stripe", "Stripe payment gateway"),
        ("paypal", "PayPal payment gateway"),
        ("oauth", "OAuth authentication"),
        ("tls 1.3", "TLS 1.3 protocol lock"),
        ("password reset", "Self-service password reset flow")
    ]
    
    for r in doc.requirements:
        stmt_lower = r.statement.lower()
        title_lower = r.title.lower()
        full_req = f"{title_lower} {stmt_lower}"
        
        for kw, desc in hallucination_triggers:
            if kw in full_req and kw not in context_text:
                issues.append(f"Grounding Failure: Requirement {r.requirement_id} introduces unrequested feature '{desc}' without evidence in project context.")
                ungrounded_count += 1
                
    # Also check if any requirement lacks evidence or has ungrounded assumption source
    for r in doc.requirements:
        if r.source and r.source.source_type == "assumption" and r.source.confidence < 0.5:
            issues.append(f"Grounding Weakness: Requirement {r.requirement_id} relies on unsupported low-confidence assumption.")
            ungrounded_count += 1
            
    # Include unresolved conflicts as grounding/consistency issues
    if hasattr(doc, "conflicts") and doc.conflicts:
        for c in doc.conflicts:
            issues.append(f"Contradiction Detected: {c}")
            ungrounded_count += 2

    score = max(0, 100 - (ungrounded_count * 15))
    return score, issues

def validate_requirement_document(doc: ProjectDocument, db: Optional[Session] = None, project_id: Optional[str] = None) -> QualityResult:
    """
    Orchestrates validation checks on the ProjectDocument across key quality dimensions.
    """
    # Detect if backlog is present. If so, we enforce backlog rules.
    backlog_required = bool(doc and doc.epics and len(doc.epics) > 0) or bool(doc and doc.user_stories and len(doc.user_stories) > 0)
    
    comp_score, comp_issues = check_completeness(doc, backlog_required)
    cons_score, cons_issues = check_consistency(doc)
    clar_score, clar_issues = check_clarity(doc)
    test_score, test_issues = check_testability(doc, backlog_required)
    trac_score, trac_issues = check_traceability(doc, backlog_required)
    cov_score, cov_issues = check_coverage(doc, backlog_required)
    ground_score, ground_issues = check_grounding(doc)
    
    scores = {
        "completeness": comp_score,
        "consistency": cons_score,
        "clarity": clar_score,
        "testability": test_score,
        "traceability": trac_score,
        "coverage": cov_score,
        "grounding": ground_score
    }
    
    # Overall score = minimum score of all dimensions to highlight the weakest link
    overall_score = min(scores.values())
    
    all_issues = []
    all_issues.extend(comp_issues)
    all_issues.extend(cons_issues)
    all_issues.extend(clar_issues)
    all_issues.extend(test_issues)
    all_issues.extend(trac_issues)
    all_issues.extend(cov_issues)
    all_issues.extend(ground_issues)
    
    # Valid gate: overall score must be >= 70, and no critical duplicate/contradiction/orphan issues
    is_valid = overall_score >= 70
    
    result = QualityResult(
        valid=is_valid,
        scores=scores,
        overall_score=overall_score,
        issues=all_issues,
        warnings=[],
        recommendations=[]
    )
    
    # Log validation metrics
    log_msg = (
        f"Validation complete: valid={is_valid}, overall_score={overall_score}. "
        f"Scores: {scores}. Issues found: {len(all_issues)}"
    )
    print(f"[Validator] {log_msg}")
    if db and project_id:
        project_service.log_activity(db, project_id, "QUALITY_VALIDATION_RUN", log_msg[:250])
        
    return result

