import sys
import os

# Add repo_version4/backend to sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.agents.requirement_agent import build_fallback_memory
from app.schemas import RequirementMemory, ProjectDocument, Requirement, RequirementSource, SourceType, RequirementStatus
from app.services.requirement_validator import check_grounding, validate_requirement_document

def test_domain_specific_grounding():
    """Verify that domain-specific input generates grounded requirements without hallucinated boilerplate features."""
    messages = [
        {"sender": "user", "text": "A portal connecting organic farmers with local restaurants for surplus crop bidding"}
    ]
    memory = build_fallback_memory(messages)
    
    # 1. Target users should be grounded in the domain
    assert any(u in memory.target_users for u in ["Farmer", "Farmers", "Restaurant", "Restaurants", "Bidder", "Bidders", "User"]), \
        f"Target users {memory.target_users} missing domain grounded roles."
    assert "System Administrators" not in memory.target_users, "Boilerplate 'System Administrators' injected into target users."
    
    # 2. Functional requirements should reflect bidding/farm/crop/restaurant concepts
    full_func = " ".join(memory.functional_requirements).lower()
    assert any(kw in full_func for kw in ["crop", "farm", "bid", "restaurant", "farmer", "surplus", "portal"]), \
        f"Functional requirements {memory.functional_requirements} not grounded in user text."
        
    # 3. Must NOT contain unrequested boilerplate features
    forbidden_features = ["oauth", "sendgrid", "stripe", "tls 1.3", "password reset"]
    for feat in forbidden_features:
        assert feat not in full_func, f"Hallucinated feature '{feat}' found in fallback functional requirements!"
        
    # 4. Non-functional requirements must not force TLS 1.3 or SendGrid
    full_nfr = " ".join(memory.non_functional_requirements).lower()
    assert "tls 1.3" not in full_nfr, "Hardcoded 'TLS 1.3' injected into NFRs."

def test_explicit_feature_grounding():
    """Verify that explicitly requested features are accepted and recognized as grounded."""
    doc = ProjectDocument(
        project_id="test-proj-001",
        version=1,
        project_summary="A booking system with credit card payment via Stripe.",
        problem_statement="Allow users to book appointments and pay via Stripe.",
        business_goals=["Enable online booking and automated payments."],
        stakeholders=["Customers", "Service Providers"],
        actors=["Customer"],
        workflows=[],
        requirements=[
            Requirement(
                requirement_id="REQ-F001",
                title="Stripe Payment Processing",
                statement="The system shall process customer payments via Stripe API.",
                requirement_type="functional",
                priority="must_have",
                status=RequirementStatus.proposed,
                source=RequirementSource(
                    source_type=SourceType.user_input,
                    source_text="pay via Stripe",
                    confidence=1.0
                )
            )
        ],
        assumptions=[],
        constraints=[],
        dependencies=["Stripe API"],
        risks=[]
    )
    
    score, issues = check_grounding(doc)
    assert score == 100, f"Expected 100 grounding score for explicit feature, got {score}. Issues: {issues}"
    assert len(issues) == 0, f"Unexpected grounding issues for explicitly requested Stripe feature: {issues}"

def test_hallucinated_feature_validation_rejection():
    """Verify that requirement validator flags hallucinated unrequested standard features."""
    doc = ProjectDocument(
        project_id="test-proj-002",
        version=1,
        project_summary="Agriculture crop yield forecasting system.",
        problem_statement="Help farmers predict crop harvest yields.",
        business_goals=["Improve harvest yield predictions."],
        stakeholders=["Farmers"],
        actors=["Farmer"],
        workflows=[],
        requirements=[
            Requirement(
                requirement_id="REQ-F001",
                title="Yield Forecasting",
                statement="The system shall predict harvest yield based on weather data.",
                requirement_type="functional",
                priority="must_have",
                status=RequirementStatus.proposed,
                source=RequirementSource(source_type=SourceType.user_input, confidence=1.0)
            ),
            Requirement(
                requirement_id="REQ-F002",
                title="SendGrid Email Notifications",
                statement="The system shall send automated email notifications using SendGrid API upon prediction.",
                requirement_type="functional",
                priority="must_have",
                status=RequirementStatus.proposed,
                source=RequirementSource(source_type=SourceType.inference, confidence=0.7)
            )
        ],
        assumptions=[],
        constraints=[],
        dependencies=[],
        risks=[]
    )
    
    score, issues = check_grounding(doc)
    assert score < 100, f"Expected score < 100 for ungrounded SendGrid requirement, got {score}"
    assert any("SendGrid" in issue for issue in issues), f"Grounding check failed to identify ungrounded SendGrid requirement: {issues}"

def test_vague_input_fallback():
    """Verify that vague input produces minimal grounded requirements without default e-commerce boilerplate."""
    messages = [
        {"sender": "user", "text": "Build an app"}
    ]
    memory = build_fallback_memory(messages)
    
    assert memory.project_summary is not None
    assert "TLS 1.3" not in " ".join(memory.non_functional_requirements)
    assert "System Administrators" not in memory.target_users

if __name__ == "__main__":
    print("=" * 60)
    print("RUNNING REQUIREMENT GROUNDING & ANTI-HALLUCINATION TEST SUITE")
    print("=" * 60)
    
    test_domain_specific_grounding()
    print("[PASS] test_domain_specific_grounding")
    
    test_explicit_feature_grounding()
    print("[PASS] test_explicit_feature_grounding")
    
    test_hallucinated_feature_validation_rejection()
    print("[PASS] test_hallucinated_feature_validation_rejection")
    
    test_vague_input_fallback()
    print("[PASS] test_vague_input_fallback")
    
    print("=" * 60)
    print("ALL REQUIREMENT GROUNDING TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

