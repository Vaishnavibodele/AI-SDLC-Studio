import os
import sys
import json
import uuid
import tempfile
from fastapi.testclient import TestClient

# Add repo_version4/backend to sys.path
backend_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)
curr_dir = os.path.dirname(os.path.abspath(__file__))
if curr_dir not in sys.path:
    sys.path.insert(0, curr_dir)

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base, get_db
from app.main import app

def test_api_fresh_endpoints():
    print("=" * 60)
    print("STARTING FASTAPI TESTCLIENT E2E SDLC FRESH DATABASE TEST")
    print("=" * 60)

    test_db_file = os.path.join(tempfile.gettempdir(), f"sdlc_api_fresh_{uuid.uuid4().hex[:8]}.db")
    if os.path.exists(test_db_file):
        os.remove(test_db_file)
        
    engine = create_engine(f"sqlite:///{test_db_file}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    headers = {"X-API-Key": "default_secret_key_12345"}

    try:
        # 1. Create Project
        res = client.post("/api/projects", json={"name": "Logistics Dispatch Portal", "description": "Fleet route optimization and driver management system."}, headers=headers)
        assert res.status_code == 200, f"Project creation failed: {res.text}"
        project_data = res.json()
        project_id = project_data["id"]
        print(f"[API Step 1] Project created: ID={project_id}")

        # 2. Attempt Development Start prematurely -> Must fail with 400
        res = client.post(f"/api/projects/{project_id}/development/start", headers=headers)
        assert res.status_code == 400, f"Expected 400 when starting development prematurely, got {res.status_code}"
        print(f"[API Step 2] Premature development attempt rejected: {res.json()['detail']}")

        # 3. Requirement Chat
        res = client.post(f"/api/projects/{project_id}/chat", json={"message": "Extract and compile complete system requirements."}, headers=headers)
        assert res.status_code == 200, f"Chat failed: {res.text}"
        print(f"[API Step 3] Requirement chat completed: status={res.json().get('status')}")

        # 4. Approve Requirements
        res = client.post(f"/api/projects/{project_id}/requirements/approve", json={
            "status": "APPROVED",
            "comments": "Approved requirements specification.",
            "reviewer_name": "Chief Architect",
            "stage": "FINALIZATION"
        }, headers=headers)
        assert res.status_code == 200, f"Requirement approval failed: {res.text}"
        print(f"[API Step 4] Requirements approved: status={res.json().get('status')}")

        # 5. Check Project Status
        res = client.get(f"/api/projects/{project_id}/status", headers=headers)
        assert res.status_code == 200, f"Get status failed: {res.text}"
        status_data = res.json()
        assert status_data["srs"] is not None, "SRS data is null in status response!"
        print(f"[API Step 5] Status verified: Project current_phase={status_data['project']['current_phase']}, SRS is populated.")

        # 6. Generate Design
        res = client.post(f"/api/projects/{project_id}/design/generate", headers=headers)
        assert res.status_code == 200, f"Design generation failed: {res.text}"
        print(f"[API Step 6] Design generated: status={res.json().get('status')}")

        # 7. Approve Design
        res = client.post(f"/api/projects/{project_id}/design/review", json={
            "status": "APPROVED",
            "comments": "System design approved for implementation.",
            "reviewer_name": "Chief Architect",
            "stage": "DESIGN_FINALIZATION"
        }, headers=headers)
        assert res.status_code == 200, f"Design review failed: {res.text}"
        print(f"[API Step 7] Design approved: status={res.json().get('status')}")

        # 8. Start Development
        res = client.post(f"/api/projects/{project_id}/development/start", headers=headers)
        assert res.status_code == 200, f"Development start failed: {res.text}"
        dev_res = res.json()
        print(f"[API Step 8] Development started successfully! Status: {dev_res.get('status')}")
        print(f" -> Generated files count: {len(dev_res.get('generated_files', {}))}")

        # 9. Test History Endpoints
        res = client.get(f"/api/projects/{project_id}/history", headers=headers)
        assert res.status_code == 200
        history = res.json()
        assert len(history) > 0, "Requirement history is empty!"
        print(f"[API Step 9] History verified: {len(history)} requirement versions saved.")

        # 10. Test SRS Downloads
        res_pdf = client.get(f"/api/projects/{project_id}/requirements/download/pdf", headers=headers)
        assert res_pdf.status_code == 200
        assert res_pdf.headers["content-type"] == "application/pdf"

        res_docx = client.get(f"/api/projects/{project_id}/requirements/download/docx", headers=headers)
        assert res_docx.status_code == 200
        assert "officedocument" in res_docx.headers["content-type"]

        res_md = client.get(f"/api/projects/{project_id}/requirements/download/markdown", headers=headers)
        assert res_md.status_code == 200
        assert "text/markdown" in res_md.headers["content-type"]

        print("[API Step 10] Requirements PDF/DOCX/MD downloads verified successfully!")

        print("=" * 60)
        print("ALL FASTAPI TESTCLIENT TESTS PASSED!")
        print("=" * 60)

    finally:
        app.dependency_overrides.clear()
        if os.path.exists(test_db_file):
            try:
                os.remove(test_db_file)
            except Exception:
                pass

if __name__ == "__main__":
    test_api_fresh_endpoints()
