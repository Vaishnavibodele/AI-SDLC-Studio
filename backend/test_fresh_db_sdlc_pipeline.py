import os
import sys
import json
import uuid
import tempfile
import traceback

# Add repo_version4/backend to sys.path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)
curr_dir = os.path.dirname(os.path.abspath(__file__))
if curr_dir not in sys.path:
    sys.path.insert(0, curr_dir)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app import models, schemas
from app.services import project_service, agent_service, design_service, development_service

def test_fresh_database_sdlc_pipeline():
    print("=" * 60)
    print("STARTING FRESH-DATABASE SDLC PIPELINE ROBUSTNESS TEST")
    print("=" * 60)

    # 1. Create a fresh isolated SQLite database
    test_db_file = os.path.join(tempfile.gettempdir(), f"sdlc_fresh_test_{uuid.uuid4().hex[:8]}.db")
    if os.path.exists(test_db_file):
        os.remove(test_db_file)
        
    db_url = f"sqlite:///{test_db_file}"
    print(f"[Step 1] Initializing clean database at: {test_db_file}")
    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()

    try:
        # 2. Create Project
        print("[Step 2] Creating new project...")
        project_create = schemas.ProjectCreate(
            name="Cloud Commerce Microservices",
            description="High-scale e-commerce platform with real-time checkout and inventory tracking."
        )
        proj = project_service.create_project(db, project_create)
        project_id = proj.id
        print(f" -> Project created: ID={project_id}, Name={proj.name}, Phase={proj.current_phase}")
        assert proj.current_phase == "REQUIREMENT"
        assert proj.status == "IN_PROGRESS"

        # 3. Test Prerequisite Guard: Attempting Development prematurely must fail
        print("[Step 3] Testing Prerequisite Guard (calling development prematurely)...")
        try:
            development_service.start_development_generation(db, project_id)
            print("FAILED: Development started without approved requirements/design!")
            sys.exit(1)
        except ValueError as ve:
            print(f" -> Expected rejection caught successfully: '{ve}'")
            assert "must be approved" in str(ve) or "not found" in str(ve)

        # 4. Generate Requirements via Chat
        print("[Step 4] Simulating Requirement Gathering & Generation...")
        chat_msg = "Generate full software requirements specification for the Cloud Commerce Microservices platform including payment processing and inventory tracking."
        chat_res = agent_service.run_chat_step(db, project_id, chat_msg)
        print(f" -> Chat Step response status: {chat_res.get('status')}")

        # 5. Human Approves Requirements
        print("[Step 5] Human Approves Requirements Specification (SRS)...")
        approval_res = agent_service.resume_approval_step(
            db=db,
            project_id=project_id,
            status="APPROVED",
            comments="Lead Architect approved SRS after IEEE-830 inspection.",
            reviewer_name="Principal Architect",
            stage="FINALIZATION"
        )
        print(f" -> Approval response: {approval_res.get('status')}")

        # Verify SQLite Requirement & RequirementVersion records
        db_req = project_service.get_requirements(db, project_id)
        assert db_req is not None, "Requirement record missing in SQLite!"
        assert db_req.approval_status == "APPROVED", f"Expected APPROVED but got {db_req.approval_status}"

        latest_srs_ver = project_service.get_latest_srs_version(db, project_id)
        assert latest_srs_ver is not None, "RequirementVersion record missing in SQLite!"
        srs_json = json.loads(latest_srs_ver.raw_srs)
        assert "functional_requirements" in srs_json or "project_name" in srs_json
        print(f" -> VERIFIED: Requirement approved & RequirementVersion v{latest_srs_ver.version_num} persisted in SQLite!")

        # 6. Generate Design (SDD)
        print("[Step 6] Generating Software Design Document (SDD)...")
        design_res = design_service.start_design_generation(db, project_id)
        print(f" -> Design generation initiated: status={design_res.get('phase') or design_res.get('status')}")

        # 7. Human Approves Design
        print("[Step 7] Human Approves Design Document (SDD)...")
        design_appr = design_service.resume_design_approval(
            db=db,
            project_id=project_id,
            status="APPROVED",
            comments="Architecture design approved with microservices & OpenAPI specs.",
            reviewer_name="Chief Architect",
            stage="DESIGN_FINALIZATION"
        )
        print(f" -> Design approval completed: status={design_appr.get('status')}")

        # Verify SQLite DesignDocument & DesignVersion records
        design_doc, latest_design_ver = design_service.get_latest_design_version(db, project_id)
        assert design_doc is not None, "DesignDocument record missing in SQLite!"
        assert design_doc.approval_status == "APPROVED", f"Expected APPROVED but got {design_doc.approval_status}"
        assert latest_design_ver is not None, "DesignVersion record missing in SQLite!"
        print(f" -> VERIFIED: Design approved & DesignVersion v{latest_design_ver.version_num} persisted in SQLite!")

        # 8. Start Development Generation
        print("[Step 8] Triggering Development Generation (Multi-Agent Codebase Scaffolding)...")
        dev_res = development_service.start_development_generation(db, project_id)
        print(f" -> Development Generation succeeded! Status: {dev_res.get('status')}")
        manifest = dev_res.get("manifest", [])
        files = dev_res.get("generated_files", {})
        print(f" -> Total generated files: {len(files)} (Manifest items: {len(manifest)})")
        assert len(files) > 0 or len(manifest) > 0 or dev_res.get("status") in ["DEVELOPMENT_PLANNING", "WAITING_FOR_REVIEW", "COMPLETED", "APPROVED"]

        # Verify SQLite Development logs
        proj_refreshed = project_service.get_project(db, project_id)
        print(f" -> Project state post-development: phase={proj_refreshed.current_phase}, status={proj_refreshed.status}")

        print("=" * 60)
        print("ALL TESTS PASSED: 100% SUCCESSFUL ON FRESH DATABASE!")
        print("=" * 60)

    finally:
        db.close()
        if os.path.exists(test_db_file):
            try:
                os.remove(test_db_file)
            except Exception:
                pass

if __name__ == "__main__":
    test_fresh_database_sdlc_pipeline()
