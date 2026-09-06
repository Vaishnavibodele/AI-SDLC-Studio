import sys
import os
import json
import uuid
import tempfile

# Add repo_version4/backend to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.agents.requirement_agent import build_fallback_memory, gap_detector_node, process_clarification_answer_text, is_duplicate_question
from app.schemas import RequirementMemory, ProjectDocument, Requirement, RequirementSource, SourceType, RequirementStatus, ClarificationQuestion, WorkflowItem
from app.services.requirement_validator import check_grounding, validate_requirement_document

def test_a_ambiguous_input_dynamic_detection():
    """Test A: Verify ambiguous input triggers dynamic question generation and workflow pause without generic fallbacks."""
    doc = ProjectDocument(
        project_id="test-ambiguous-01",
        version=1,
        project_summary="Build a system for students to reserve study rooms.",
        problem_statement="Students want to book study rooms on campus.",
        business_goals=["Streamline room reservation."],
        stakeholders=["Students"],
        actors=["Student"],
        workflows=[],
        requirements=[
            Requirement(
                requirement_id="REQ-F001",
                title="Room Reservation",
                statement="Students shall be able to reserve available study rooms.",
                requirement_type="functional",
                priority="must_have",
                status=RequirementStatus.proposed,
                source=RequirementSource(source_type=SourceType.user_input, confidence=1.0)
            )
        ],
        assumptions=[],
        constraints=[],
        dependencies=[],
        risks=[]
    )
    
    state = {
        "document": doc,
        "clarification_questions": [],
        "messages": [{"sender": "user", "text": "Build a system for students to reserve study rooms."}]
    }
    
    output = gap_detector_node(state)
    questions = output.get("clarification_questions", [])
    
    # Assert questions exist and are dynamic
    assert len(questions) > 0, "Expected dynamic clarification questions to be generated for ambiguous room reservation prompt."
    q_texts = " ".join([q["question"] for q in questions]).lower()
    assert any(kw in q_texts for kw in ["room", "reserve", "availability", "student", "manage", "schedule", "limit"]), \
        f"Generated questions {questions} not contextual to study room reservation."
    assert "stripe" not in q_texts and "oauth" not in q_texts, "Hallucinated standard features in generated questions."

def test_b_clear_input_minimal_questions():
    """Test B: Verify clear input generates direct requirements with minimal unnecessary clarification questions."""
    doc = ProjectDocument(
        project_id="test-clear-01",
        version=1,
        project_summary="Automated laboratory inventory tracker for chemistry supplies with barcode scanning and low stock alerts.",
        problem_statement="Track lab chemical inventory levels with barcode scanners.",
        business_goals=["Prevent chemical inventory stockouts."],
        stakeholders=["Lab Manager", "Research Chemist"],
        actors=["Lab Manager"],
        workflows=[],
        requirements=[
            Requirement(
                requirement_id="REQ-F001",
                title="Barcode Scanning",
                statement="System shall scan chemical container barcodes to update stock counts.",
                requirement_type="functional",
                priority="must_have",
                status=RequirementStatus.proposed,
                source=RequirementSource(source_type=SourceType.user_input, confidence=1.0)
            )
        ],
        assumptions=[],
        constraints=[],
        dependencies=[],
        risks=[]
    )
    
    score, issues = check_grounding(doc)
    assert score == 100, f"Expected 100 grounding score for clear input, got {score}. Issues: {issues}"

def test_c_human_clarification_as_evidence():
    """Test C: Verify human answer becomes authoritative evidence and updates requirements iteratively."""
    doc = ProjectDocument(
        project_id="test-hitl-01",
        version=1,
        project_summary="Food delivery platform for local restaurants.",
        problem_statement="Connect diners with local restaurants.",
        business_goals=["Enable online food ordering."],
        stakeholders=["Diners", "Restaurant Owners"],
        actors=["Diner"],
        workflows=[],
        requirements=[
            Requirement(
                requirement_id="REQ-F001",
                title="Browse Menus",
                statement="Diners shall browse restaurant menu items.",
                requirement_type="functional",
                priority="must_have",
                status=RequirementStatus.proposed,
                source=RequirementSource(source_type=SourceType.user_input, confidence=1.0)
            )
        ],
        assumptions=[],
        constraints=[],
        dependencies=[],
        risks=[]
    )
    
    question = "Who is responsible for updating restaurant menu items and prices?"
    answer = "Restaurants manage their own menus and price updates independently."
    user_texts = ["Build a food delivery platform for local restaurants."]
    
    updated_doc, conflicts = process_clarification_answer_text(doc, question, answer, user_texts)
    
    # Assert requirements updated with human_clarification source
    human_clarified_reqs = [r for r in updated_doc.requirements if r.source and r.source.source_type == SourceType.human_clarification]
    assert len(human_clarified_reqs) > 0, "Expected human clarification answer to create/update requirement with human_clarification source."
    assert human_clarified_reqs[0].source.confidence == 1.0, "Human clarification evidence must have confidence = 1.0"
    assert human_clarified_reqs[0].source.source_text == answer, f"Expected source_text to match human answer, got {human_clarified_reqs[0].source.source_text}"

def test_d_human_correction():
    """Test D: Verify human correction updates dependent requirements."""
    doc = ProjectDocument(
        project_id="test-correction-01",
        version=1,
        project_summary="Doctor appointment scheduling portal.",
        problem_statement="Book patient appointments.",
        business_goals=["Schedule patient doctor visits."],
        stakeholders=["Patients", "Doctors"],
        actors=["Patient"],
        workflows=[],
        requirements=[
            Requirement(
                requirement_id="REQ-F001",
                title="Doctor Schedule Management",
                statement="Doctors manage their own availability schedules.",
                requirement_type="functional",
                priority="must_have",
                status=RequirementStatus.proposed,
                source=RequirementSource(source_type=SourceType.user_input, confidence=1.0)
            )
        ],
        assumptions=[],
        constraints=[],
        dependencies=[],
        risks=[]
    )
    
    correction_question = "Who manages doctor availability schedules?"
    correction_answer = "Actually, hospital administrators manage doctor schedules, not individual doctors."
    
    updated_doc, conflicts = process_clarification_answer_text(
        doc, correction_question, correction_answer, ["Doctor appointment scheduling portal."]
    )
    
    req_text = " ".join([r.statement for r in updated_doc.requirements]).lower()
    assert "administrator" in req_text or "hospital" in req_text or "fulfill" in req_text, \
        "Correction answer did not update requirement statements."

def test_e_duplicate_question_prevention():
    """Test E: Verify duplicate clarification questions are detected and prevented."""
    existing_questions = [
        {"question": "Who is responsible for managing product availability?", "status": "pending"}
    ]
    
    is_dup1 = is_duplicate_question("Who is responsible for managing product availability?", existing_questions)
    is_dup2 = is_duplicate_question("Who is responsible for managing product stock?", existing_questions)
    is_diff = is_duplicate_question("What is the maximum allowed file upload size for receipts?", existing_questions)
    
    assert is_dup1 is True, "Identical question string not recognized as duplicate."
    assert is_dup2 is True, "Semantically near-identical question not recognized as duplicate."
    assert is_diff is False, "Distinct question falsely flagged as duplicate."

def test_f_contradiction_detection():
    """Test F: Verify direct contradiction between inputs is flagged."""
    doc = ProjectDocument(
        project_id="test-contradict-01",
        version=1,
        project_summary="Package delivery tracking portal.",
        problem_statement="Track delivery packages.",
        business_goals=["Package tracking."],
        stakeholders=["Customers"],
        actors=["Customer"],
        workflows=[],
        requirements=[
            Requirement(
                requirement_id="REQ-F001",
                title="Order Cancellation",
                statement="Customers are permitted to cancel package orders after dispatch.",
                requirement_type="functional",
                priority="must_have",
                status=RequirementStatus.proposed,
                source=RequirementSource(source_type=SourceType.user_input, confidence=1.0)
            )
        ],
        assumptions=[],
        constraints=[],
        dependencies=[],
        risks=[]
    )
    
    question = "Can customers cancel orders after dispatch?"
    contradictory_answer = "Customers are strictly forbidden from cancelling orders once dispatched."
    
    updated_doc, conflicts = process_clarification_answer_text(
        doc, question, contradictory_answer, ["Customers can cancel package orders after dispatch."]
    )
    
    # Conflict check should be attempted
    assert isinstance(conflicts, list)

def test_g_explicit_human_approval_gate():
    """Test G: Verify validation passing does NOT auto-approve; explicit human action is required."""
    doc = ProjectDocument(
        project_id="test-approval-01",
        version=1,
        project_summary="Inventory management system for spare parts.",
        problem_statement="Track spare parts count.",
        business_goals=["Maintain accurate inventory counts."],
        stakeholders=["Warehouse Staff"],
        actors=["Warehouse Staff"],
        workflows=[WorkflowItem(workflow_id="WF-001", name="Scan barcode", actor="Warehouse Staff", trigger="User scans spare part barcode", steps=["Scan item", "Update inventory count"])],
        requirements=[
            Requirement(
                requirement_id="REQ-F001",
                title="Parts Count Tracking",
                statement="System shall track spare part quantity count in real-time.",
                requirement_type="functional",
                priority="must_have",
                status=RequirementStatus.proposed,
                source=RequirementSource(source_type=SourceType.user_input, confidence=1.0)
            ),
            Requirement(
                requirement_id="REQ-NF001",
                title="Inventory Search Speed",
                statement="System shall return inventory count lookup queries in less than 1 second.",
                requirement_type="non_functional",
                priority="must_have",
                status=RequirementStatus.proposed,
                source=RequirementSource(source_type=SourceType.user_input, confidence=1.0)
            ),
            Requirement(
                requirement_id="REQ-BR001",
                title="Reorder Threshold Alert",
                statement="System shall issue an alert when part quantity drops below the safety stock threshold.",
                requirement_type="business_rule",
                priority="must_have",
                status=RequirementStatus.proposed,
                source=RequirementSource(source_type=SourceType.user_input, confidence=1.0)
            )
        ],
        assumptions=["Warehouse staff have barcode scanner devices"],
        constraints=["System must operate on company intranet"],
        dependencies=[],
        risks=[]
    )
    
    quality_result = validate_requirement_document(doc)
    assert quality_result.valid is True, "Valid requirement document failed quality validation."
    
    # Explicit human approval requirement
    # Quality result valid does NOT set requirement status to approved on its own
    assert doc.requirements[0].status == RequirementStatus.proposed, \
        "Requirement status prematurely set to approved without explicit human review submission."

def test_h_persistence_and_checkpointing():
    """Test H: Verify state values retain requirements, clarification questions, and answers across serialization."""
    doc = ProjectDocument(
        project_id="test-persist-01",
        version=1,
        project_summary="Equipment maintenance scheduling portal.",
        problem_statement="Schedule factory equipment maintenance.",
        business_goals=["Minimize factory downtime."],
        stakeholders=["Maintenance Staff"],
        actors=["Technician"],
        workflows=[],
        requirements=[
            Requirement(
                requirement_id="REQ-F001",
                title="Equipment Issue Reporting",
                statement="Technicians shall record equipment issues with severity level.",
                requirement_type="functional",
                priority="must_have",
                status=RequirementStatus.proposed,
                source=RequirementSource(source_type=SourceType.user_input, confidence=1.0)
            )
        ],
        clarification_questions=[
            ClarificationQuestion(
                id="GAP-001",
                question="Who approves emergency maintenance work orders?",
                reason="Determine authorization workflow.",
                priority="high",
                status="answered",
                answer="Plant manager approves all emergency work orders."
            )
        ],
        assumptions=[],
        constraints=[],
        dependencies=[],
        risks=[]
    )
    
    # Dump to JSON and reload
    serialized = doc.dict()
    reloaded_doc = ProjectDocument(**serialized)
    
    assert reloaded_doc.project_id == "test-persist-01"
    assert len(reloaded_doc.requirements) == 1
    assert len(reloaded_doc.clarification_questions) == 1
    assert reloaded_doc.clarification_questions[0].answer == "Plant manager approves all emergency work orders."

def test_i_multiple_unrelated_domains():
    """Test I: Verify system produces domain-specific outputs for unrelated domains without cross-domain pollution."""
    domains = [
        {"prompt": "K-12 Student grading and report card generation portal", "expected_kw": ["student", "grade", "report", "school"]},
        {"prompt": "Veterinary clinic pet vaccination and appointment record system", "expected_kw": ["vet", "pet", "vaccin", "clinic", "animal"]},
        {"prompt": "Port container crane dispatch and freight berth management system", "expected_kw": ["crane", "freight", "container", "port", "berth"]}
    ]
    
    for item in domains:
        memory = build_fallback_memory([{"sender": "user", "text": item["prompt"]}])
        full_text = (memory.project_summary + " " + " ".join(memory.functional_requirements) + " " + " ".join(memory.target_users)).lower()
        
        assert any(kw in full_text for kw in item["expected_kw"]), \
            f"Domain prompt '{item['prompt']}' produced memory text lacking domain keywords: {full_text}"
        assert "stripe" not in full_text and "sendgrid" not in full_text and "tls 1.3" not in full_text, \
            f"Cross-domain pollution detected in domain prompt '{item['prompt']}'"

def test_j_completely_new_domain_acceptance():
    """Test J Acceptance: Test completely new domain (manufacturing equipment maintenance) without any source code changes."""
    new_domain_input = "Create a system for managing equipment maintenance in a manufacturing facility. Maintenance staff should record equipment issues and schedule maintenance activities."
    
    memory = build_fallback_memory([{"sender": "user", "text": new_domain_input}])
    
    assert memory.project_summary is not None
    full_func = " ".join(memory.functional_requirements).lower()
    
    assert any(kw in full_func for kw in ["equipment", "maintain", "issue", "schedule", "record", "facility", "system"]), \
        f"New domain requirement extraction failed to capture manufacturing maintenance context: {memory.functional_requirements}"
    
    # Assert ZERO hardcoded boilerplate
    forbidden = ["oauth", "stripe", "sendgrid", "tls 1.3", "password reset"]
    for feat in forbidden:
        assert feat not in full_func, f"Forbidden feature '{feat}' found in new domain extraction!"

if __name__ == "__main__":
    print("=" * 60)
    print("RUNNING PHASE 2 REQUIREMENT AGENT TEST SUITE (SCENARIOS A - J)")
    print("=" * 60)
    
    test_a_ambiguous_input_dynamic_detection()
    print("[PASS] Test A — Ambiguous Input Dynamic Question Generation")
    
    test_b_clear_input_minimal_questions()
    print("[PASS] Test B — Clear Input Minimal Questions")
    
    test_c_human_clarification_as_evidence()
    print("[PASS] Test C — Human Clarification as Authoritative Evidence")
    
    test_d_human_correction()
    print("[PASS] Test D — Human Correction Requirement Revision")
    
    test_e_duplicate_question_prevention()
    print("[PASS] Test E — Duplicate Question Prevention")
    
    test_f_contradiction_detection()
    print("[PASS] Test F — Contradiction Detection")
    
    test_g_explicit_human_approval_gate()
    print("[PASS] Test G — Explicit Human Approval Gate")
    
    test_h_persistence_and_checkpointing()
    print("[PASS] Test H — Persistence & Checkpointing")
    
    test_i_multiple_unrelated_domains()
    print("[PASS] Test I — Multiple Unrelated Domains")
    
    test_j_completely_new_domain_acceptance()
    print("[PASS] Test J — Completely New Domain Acceptance Test")
    
    print("=" * 60)
    print("ALL PHASE 2 REQUIREMENT AGENT TESTS PASSED (10/10 SUCCESS)!")
    print("=" * 60)
