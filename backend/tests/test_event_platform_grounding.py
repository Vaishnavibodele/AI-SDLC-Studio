import os
import sys
import json

# Add parent path to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.schemas import RequirementMemory, ProjectDocument
from app.services.llm_provider import MockChatModel
from langchain_core.messages import SystemMessage, HumanMessage

FORBIDDEN_TERMS = [
    "authentication", "oauth", "jwt", "audit log", "gdpr", "soc2", "tls",
    "microservice", "500ms", "500 requests", "dashboard", "alex", "taylor",
    "executive sponsor", "qa manager"
]

def test_event_platform_grounding():
    prompt = "An event platform where attendees can view event schedules, purchase tickets, and organizers can manage events."
    model = MockChatModel()
    
    # 1. State Memory Updater
    mem_res = model.invoke([
        SystemMessage(content="You are the State Manager & Memory node for a Senior Business Analyst Agent. Update the structured Requirement Memory"),
        HumanMessage(content=prompt)
    ])
    mem_json = json.loads(mem_res.content)
    
    # Assert functional requirements are strictly grounded
    func_reqs = mem_json.get("functional_requirements", [])
    func_text = " ".join(func_reqs).lower()
    assert "view event schedules" in func_text or "attendees can view event schedules" in func_text
    assert "purchase tickets" in func_text
    assert "manage events" in func_text or "organizers can manage events" in func_text
    
    for term in FORBIDDEN_TERMS:
        assert term not in mem_res.content.lower(), f"Forbidden generic term '{term}' found in Memory Updater output!"
        
    # 2. SRS Emitter / Compiler
    srs_res = model.invoke([
        SystemMessage(content="You are a Senior Business Analyst. Compile a complete SRS document in JSON format."),
        HumanMessage(content=f"Requirement Memory collected:\n{mem_res.content}")
    ])
    srs_json = json.loads(srs_res.content)
    
    # Assert Actors are dynamically derived
    actors = srs_json.get("actors", [])
    actors_lower = [a.lower() for a in actors]
    assert "attendees" in actors_lower or "attendee" in actors_lower
    assert "organizers" in actors_lower or "organizer" in actors_lower
    assert "doctor" not in actors_lower and "patient" not in actors_lower and "admin" not in actors_lower
    
    # Assert Unmentioned fields return 'Not specified'
    assert "Not specified in the provided requirements." in srs_json.get("non_functional_requirements", [])
    assert "Not specified in the provided requirements." in srs_json.get("user_personas", [])
    assert "Not specified in the provided requirements." in srs_json.get("security_requirements", [])
    assert "Not specified in the provided requirements." in srs_json.get("compliance_requirements", [])
    
    # Assert zero generic enterprise terms in compiled SRS
    for term in FORBIDDEN_TERMS:
        assert term not in srs_res.content.lower(), f"Forbidden generic term '{term}' found in Compiled SRS!"
        
    print("[PASS] Event Platform Grounding Verified (Zero generic enterprise content)!")


def test_vehicle_rental_grounding():
    prompt = "Customers can search vehicles, select rental dates, make reservations, make payments, and cancel bookings. Administrators can manage vehicles, pricing, and reservations."
    model = MockChatModel()
    
    mem_res = model.invoke([
        SystemMessage(content="You are the State Manager & Memory node for a Senior Business Analyst Agent. Update the structured Requirement Memory"),
        HumanMessage(content=prompt)
    ])
    srs_res = model.invoke([
        SystemMessage(content="You are a Senior Business Analyst. Compile a complete SRS document in JSON format."),
        HumanMessage(content=f"Requirement Memory collected:\n{mem_res.content}")
    ])
    srs_json = json.loads(srs_res.content)
    
    actors_lower = [a.lower() for a in srs_json.get("actors", [])]
    assert "customers" in actors_lower or "customer" in actors_lower
    assert "administrators" in actors_lower or "administrator" in actors_lower
    
    func_text = " ".join(srs_json.get("functional_requirements", [])).lower()
    assert "search vehicles" in func_text
    assert "rental dates" in func_text
    assert "make reservations" in func_text
    assert "make payments" in func_text
    assert "cancel bookings" in func_text
    assert "manage vehicles" in func_text
    assert "manage pricing" in func_text
    
    for term in FORBIDDEN_TERMS:
        assert term not in srs_res.content.lower(), f"Forbidden generic term '{term}' found in Vehicle Rental SRS!"
        
    print("[PASS] Vehicle Rental Grounding Verified!")


def test_library_system_grounding():
    prompt = "Students can search for books and librarians can add, update, and remove books."
    model = MockChatModel()
    
    mem_res = model.invoke([
        SystemMessage(content="You are the State Manager & Memory node for a Senior Business Analyst Agent. Update the structured Requirement Memory"),
        HumanMessage(content=prompt)
    ])
    srs_res = model.invoke([
        SystemMessage(content="You are a Senior Business Analyst. Compile a complete SRS document in JSON format."),
        HumanMessage(content=f"Requirement Memory collected:\n{mem_res.content}")
    ])
    srs_json = json.loads(srs_res.content)
    
    actors_lower = [a.lower() for a in srs_json.get("actors", [])]
    assert "students" in actors_lower or "student" in actors_lower
    assert "librarians" in actors_lower or "librarian" in actors_lower
    
    func_text = " ".join(srs_json.get("functional_requirements", [])).lower()
    assert "search" in func_text and "books" in func_text
    assert "add" in func_text and "books" in func_text
    assert "update" in func_text and "books" in func_text
    assert "remove" in func_text and "books" in func_text
    
    for term in FORBIDDEN_TERMS:
        assert term not in srs_res.content.lower(), f"Forbidden generic term '{term}' found in Library System SRS!"
        
    print("[PASS] Library System Grounding Verified!")


def test_completely_new_domain_grounding():
    prompt = "Pilots can stream live flight telemetry and engineers can annotate thermal imaging frames."
    model = MockChatModel()
    
    mem_res = model.invoke([
        SystemMessage(content="You are the State Manager & Memory node for a Senior Business Analyst Agent. Update the structured Requirement Memory"),
        HumanMessage(content=prompt)
    ])
    srs_res = model.invoke([
        SystemMessage(content="You are a Senior Business Analyst. Compile a complete SRS document in JSON format."),
        HumanMessage(content=f"Requirement Memory collected:\n{mem_res.content}")
    ])
    srs_json = json.loads(srs_res.content)
    
    actors_lower = [a.lower() for a in srs_json.get("actors", [])]
    assert "pilots" in actors_lower or "pilot" in actors_lower
    assert "engineers" in actors_lower or "engineer" in actors_lower
    
    func_text = " ".join(srs_json.get("functional_requirements", [])).lower()
    assert "stream live flight telemetry" in func_text or "telemetry" in func_text
    assert "annotate thermal imaging" in func_text or "thermal" in func_text
    
    for term in FORBIDDEN_TERMS:
        assert term not in srs_res.content.lower(), f"Forbidden generic term '{term}' found in Drone Inspection SRS!"
        
    print("[PASS] Completely New Domain Grounding Verified!")

if __name__ == "__main__":
    test_event_platform_grounding()
    test_vehicle_rental_grounding()
    test_library_system_grounding()
    test_completely_new_domain_grounding()
    print("\n" + "="*70)
    print("ALL 4 USER GROUNDING TEST SCENARIOS PASSED WITH 100% SUCCESS!")
    print("="*70)
