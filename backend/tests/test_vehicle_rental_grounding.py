import os
import sys
import json

# Add parent directory to python path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.database import SessionLocal, Base, engine
from app.services import project_service, agent_service
from app import schemas

def test_exact_vehicle_rental_scenario():
    """Requirement 14 test scenario: Vehicle Rental application."""
    print("\n--- Running Test Scenario 14: Vehicle Rental Application ---")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    prompt = (
        "Create a vehicle rental application where customers can search available vehicles, "
        "select rental dates, make reservations, make payments, and cancel bookings. "
        "Administrators should be able to manage vehicles, pricing, and reservations."
    )
    
    project = project_service.create_project(db, schemas.ProjectCreate(name="Vehicle Rental Test", description=prompt))
    
    # Process project through requirement service
    result = agent_service.run_chat_step(db, project.id, message_text=prompt)
    
    # Trigger SRS compilation
    agent_service.run_chat_step(db, project.id, message_text="Generate SRS")
    
    # Get compiled SRS data
    srs_data, _ = project_service.get_effective_srs_data(db, project.id)
    
    # Convert entire SRS data to JSON string for checking forbidden terms
    srs_json_str = json.dumps(srs_data, indent=2)
    srs_json_lower = srs_json_str.lower()
    
    print("\nGenerated Functional Requirements:")
    for fr in srs_data.get("functional_requirements", []):
        print(f"  • {fr}")

    print("\nGenerated Actors:")
    print(f"  • {srs_data.get('actors')}")
    
    print("\nGenerated Non-Functional Requirements:")
    print(f"  • {srs_data.get('non_functional_requirements')}")

    # Check for forbidden hallucinated terms
    forbidden_terms = [
        "oauth", "jwt", "zero-trust", "tls 1.3", "aes-256", "gdpr", "soc2", 
        "rate limiting", "500 requests", "500ms", "microservices", "webhooks",
        "alex", "taylor", "executive sponsor", "qa manager"
    ]
    
    found_forbidden = []
    for term in forbidden_terms:
        if term in srs_json_lower:
            found_forbidden.append(term)
            
    if found_forbidden:
        print(f"\n[FAIL] Found hallucinated terms in generated SRS: {found_forbidden}")
        assert False, f"Hallucinated terms found: {found_forbidden}"
    else:
        print("\n[PASS] Vehicle Rental SRS contains ZERO hallucinated enterprise terms!")

def test_adversarial_unrelated_domains():
    """Requirement 15 test scenario: Adversarial tests across multiple domains."""
    print("\n--- Running Requirement 15: Adversarial Unrelated Domains Test ---")
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    
    domains = [
        ("Library Management", "A library system where members can search books, borrow titles, return books, and librarians can manage inventory."),
        ("Fitness Booking", "A fitness application where members can book workout classes, view trainer schedules, and cancel bookings."),
        ("Event Ticketing", "An event platform where attendees can view event schedules, purchase tickets, and organizers can manage events.")
    ]
    
    for domain_name, prompt in domains:
        print(f"\nTesting domain: {domain_name}")
        project = project_service.create_project(db, schemas.ProjectCreate(name=f"{domain_name} Test", description=prompt))
        agent_service.run_chat_step(db, project.id, message_text=prompt)
        srs_data, _ = project_service.get_effective_srs_data(db, project.id)
        
        srs_json_str = json.dumps(srs_data)
        assert "oauth" not in srs_json_str.lower(), f"Hallucinated OAuth in {domain_name}"
        assert "alex" not in srs_json_str.lower(), f"Hallucinated Alex in {domain_name}"
        assert "microservices" not in srs_json_str.lower(), f"Hallucinated microservices in {domain_name}"
        print(f"[PASS] {domain_name} generated grounded requirements cleanly!")

if __name__ == "__main__":
    test_exact_vehicle_rental_scenario()
    test_adversarial_unrelated_domains()
    print("\n============================================================")
    print("ALL VEHICLE RENTAL & ADVERSARIAL GROUNDING TESTS PASSED (100% SUCCESS)!")
    print("============================================================")
