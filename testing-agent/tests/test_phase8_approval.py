"""Phase 8 human approval/reject tests.

Deterministic, mock-only: no browser, no external API.
Tests the approval state machine, API endpoints, and release_allowed logic.
"""
from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.models.schemas import ApprovalStatus


class TestApprovalStateMachine:
    """Test the approval state machine transitions."""
    
    def test_initial_approval_status_is_pending(self):
        """Test that initial approval status is pending."""
        client = TestClient(app)
        response = client.get("/testing/report/approval-status/test-project-1")
        assert response.status_code == 200
        body = response.json()
        assert body["approval_status"] == "pending"
        assert body["release_allowed"] is False
        assert body["approved_by"] == "--"
        assert body["approval_timestamp"] == "--"
    
    def test_successful_approval(self):
        """Test successful approval with valid request."""
        client = TestClient(app)
        
        # First, initialize a report by calling execute (which sets up approval state)
        # For this test, we'll directly call the approve endpoint
        
        approve_payload = {
            "project_id": "test-project-2",
            "report_id": "RPT-TEST001",
            "approved_by": "john.doe",
            "comment": "All tests passed, ready for release"
        }
        
        response = client.post("/testing/report/approve", json=approve_payload)
        assert response.status_code == 200
        body = response.json()
        assert body["approval_status"] == "approved"
        assert body["approved_by"] == "john.doe"
        assert body["report_id"] == "RPT-TEST001"
        assert body["comment"] == "All tests passed, ready for release"
        assert body["approval_timestamp"] is not None
        # Note: release_allowed might be false if no quality gate info is set
    
    def test_successful_rejection(self):
        """Test successful rejection with comment."""
        client = TestClient(app)
        
        reject_payload = {
            "project_id": "test-project-3",
            "report_id": "RPT-TEST002",
            "approved_by": "jane.smith",
            "comment": "Critical bugs found, cannot release"
        }
        
        response = client.post("/testing/report/reject", json=reject_payload)
        assert response.status_code == 200
        body = response.json()
        assert body["approval_status"] == "rejected"
        assert body["approved_by"] == "jane.smith"
        assert body["report_id"] == "RPT-TEST002"
        assert body["comment"] == "Critical bugs found, cannot release"
        assert body["approval_timestamp"] is not None
        assert body["release_allowed"] is False
    
    def test_rejection_requires_comment(self):
        """Test that rejection requires a non-empty comment."""
        client = TestClient(app)
        
        # Test with missing comment
        reject_payload_no_comment = {
            "project_id": "test-project-4",
            "report_id": "RPT-TEST003",
            "approved_by": "bob.jones"
        }
        
        response = client.post("/testing/report/reject", json=reject_payload_no_comment)
        assert response.status_code == 400
        assert "comment" in response.json()["detail"].lower()
        
        # Test with empty comment
        reject_payload_empty_comment = {
            "project_id": "test-project-5",
            "report_id": "RPT-TEST004",
            "approved_by": "bob.jones",
            "comment": "   "
        }
        
        response = client.post("/testing/report/reject", json=reject_payload_empty_comment)
        assert response.status_code == 400
        assert "comment" in response.json()["detail"].lower()
    
    def test_duplicate_approval_rejected(self):
        """Test that approving an already approved report is rejected."""
        client = TestClient(app)
        
        approve_payload = {
            "project_id": "test-project-6",
            "report_id": "RPT-TEST005",
            "approved_by": "alice.wonder",
            "comment": "First approval"
        }
        
        # First approval should succeed
        response1 = client.post("/testing/report/approve", json=approve_payload)
        assert response1.status_code == 200
        assert response1.json()["approval_status"] == "approved"
        
        # Second approval should fail
        response2 = client.post("/testing/report/approve", json=approve_payload)
        assert response2.status_code == 400
        assert "Cannot approve" in response2.json()["detail"]
        assert "approved" in response2.json()["detail"]
    
    def test_duplicate_rejection_rejected(self):
        """Test that rejecting an already rejected report is rejected."""
        client = TestClient(app)
        
        reject_payload = {
            "project_id": "test-project-7",
            "report_id": "RPT-TEST006",
            "approved_by": "charlie.brown",
            "comment": "First rejection"
        }
        
        # First rejection should succeed
        response1 = client.post("/testing/report/reject", json=reject_payload)
        assert response1.status_code == 200
        assert response1.json()["approval_status"] == "rejected"
        
        # Second rejection should fail
        response2 = client.post("/testing/report/reject", json=reject_payload)
        assert response2.status_code == 400
        assert "Cannot reject" in response2.json()["detail"]
        assert "rejected" in response2.json()["detail"]
    
    def test_approval_after_rejection_rejected(self):
        """Test that approval cannot override rejection."""
        client = TestClient(app)
        
        # First reject
        reject_payload = {
            "project_id": "test-project-8",
            "report_id": "RPT-TEST007",
            "approved_by": "david.lee",
            "comment": "Blocking release"
        }
        
        response1 = client.post("/testing/report/reject", json=reject_payload)
        assert response1.status_code == 200
        assert response1.json()["approval_status"] == "rejected"
        
        # Try to approve after rejection should fail
        approve_payload = {
            "project_id": "test-project-8",
            "report_id": "RPT-TEST007",
            "approved_by": "emma.watson",
            "comment": "Override rejection"
        }
        
        response2 = client.post("/testing/report/approve", json=approve_payload)
        assert response2.status_code == 400
        assert "Cannot approve" in response2.json()["detail"]
    
    def test_rejection_after_approval_rejected(self):
        """Test that rejection can override approval (terminal state change)."""
        client = TestClient(app)
        
        # First approve
        approve_payload = {
            "project_id": "test-project-9",
            "report_id": "RPT-TEST008",
            "approved_by": "frank.sinatra",
            "comment": "Initial approval"
        }
        
        response1 = client.post("/testing/report/approve", json=approve_payload)
        assert response1.status_code == 200
        assert response1.json()["approval_status"] == "approved"
        
        # Try to reject after approval should fail (both are terminal)
        reject_payload = {
            "project_id": "test-project-9",
            "report_id": "RPT-TEST008",
            "approved_by": "grace.kelly",
            "comment": "Override approval"
        }
        
        response2 = client.post("/testing/report/reject", json=reject_payload)
        assert response2.status_code == 400
        assert "Cannot reject" in response2.json()["detail"]
    
    def test_release_allowed_false_while_pending(self):
        """Test that release_allowed is false when status is pending."""
        client = TestClient(app)
        
        # Check pending status
        response = client.get("/testing/report/approval-status/test-project-10")
        assert response.status_code == 200
        body = response.json()
        assert body["approval_status"] == "pending"
        assert body["release_allowed"] is False
    
    def test_release_allowed_false_for_rejected(self):
        """Test that release_allowed is always false for rejected status."""
        client = TestClient(app)
        
        reject_payload = {
            "project_id": "test-project-11",
            "report_id": "RPT-TEST009",
            "approved_by": "henry.ford",
            "comment": "Rejected"
        }
        
        # Reject the report
        response1 = client.post("/testing/report/reject", json=reject_payload)
        assert response1.status_code == 200
        
        # Check that release_allowed is false
        response2 = client.get("/testing/report/approval-status/test-project-11")
        assert response2.status_code == 200
        body = response2.json()
        assert body["approval_status"] == "rejected"
        assert body["release_allowed"] is False
    
    def test_missing_reviewer_rejected(self):
        """Test that approval/rejection requires reviewer identifier."""
        client = TestClient(app)
        
        # Test approval without reviewer
        approve_payload = {
            "project_id": "test-project-12",
            "report_id": "RPT-TEST010",
            "approved_by": "",
            "comment": "No reviewer"
        }
        
        response = client.post("/testing/report/approve", json=approve_payload)
        assert response.status_code == 400
        assert "approved_by" in response.json()["detail"]
        
        # Test rejection without reviewer
        reject_payload = {
            "project_id": "test-project-13",
            "report_id": "RPT-TEST011",
            "approved_by": "   ",
            "comment": "No reviewer"
        }
        
        response = client.post("/testing/report/reject", json=reject_payload)
        assert response.status_code == 400
        assert "approved_by" in response.json()["detail"]
    
    def test_approval_response_schema(self):
        """Test that approval response contains all required fields."""
        client = TestClient(app)
        
        approve_payload = {
            "project_id": "test-project-14",
            "report_id": "RPT-TEST012",
            "approved_by": "isaac.newton",
            "comment": "Approved"
        }
        
        response = client.post("/testing/report/approve", json=approve_payload)
        assert response.status_code == 200
        body = response.json()
        
        # Check all required fields
        assert "project_id" in body
        assert "report_id" in body
        assert "approval_status" in body
        assert "approved_by" in body
        assert "approval_timestamp" in body
        assert "comment" in body
        assert "release_allowed" in body
        assert "quality_gate_status" in body
        assert "release_readiness" in body
        
        # Check types
        assert isinstance(body["project_id"], str)
        assert isinstance(body["report_id"], str)
        assert isinstance(body["approval_status"], str)
        assert isinstance(body["approved_by"], str)
        assert isinstance(body["approval_timestamp"], str)
        assert isinstance(body["release_allowed"], bool)
    
    def test_get_approval_status_persistence(self):
        """Test that approval status persists across calls."""
        client = TestClient(app)
        
        # Set approval status
        approve_payload = {
            "project_id": "test-project-15",
            "report_id": "RPT-TEST013",
            "approved_by": "james.bond",
            "comment": "007 approved"
        }
        
        response1 = client.post("/testing/report/approve", json=approve_payload)
        assert response1.status_code == 200
        
        # Retrieve status
        response2 = client.get("/testing/report/approval-status/test-project-15")
        assert response2.status_code == 200
        body = response2.json()
        
        assert body["approval_status"] == "approved"
        assert body["approved_by"] == "james.bond"
        assert body["comment"] == "007 approved"
        assert body["report_id"] == "RPT-TEST013"
    
    def test_approval_comment_optional(self):
        """Test that approval comment is optional."""
        client = TestClient(app)
        
        approve_payload = {
            "project_id": "test-project-16",
            "report_id": "RPT-TEST014",
            "approved_by": "kanye.west",
            "comment": None
        }
        
        response = client.post("/testing/report/approve", json=approve_payload)
        assert response.status_code == 200
        body = response.json()
        assert body["approval_status"] == "approved"
        assert body["comment"] is None
    
    def test_existing_phase_1_8_endpoints_still_work(self):
        """Test that existing Phase 1-8 endpoints remain functional."""
        client = TestClient(app)
        
        # Test /testing/start endpoint
        start_payload = {
            "project_id": "compatibility-test",
            "srs": {"title": "SRS", "version": "1.0"},
            "sdd": {"architecture": "Mono", "components": ["auth"]},
            "source_code": {"repository": "github.com/org/repo", "language": "Python"}
        }
        
        response = client.post("/testing/start", json=start_payload)
        assert response.status_code == 200
        body = response.json()
        assert "project_id" in body
        assert "validation_status" in body
        assert "workflow_status" in body
    
    def test_approval_status_enum_values(self):
        """Test that ApprovalStatus enum has correct values."""
        assert ApprovalStatus.PENDING == "pending"
        assert ApprovalStatus.APPROVED == "approved"
        assert ApprovalStatus.REJECTED == "rejected"
    
    def test_concurrent_projects_dont_interfere(self):
        """Test that approval states for different projects don't interfere."""
        client = TestClient(app)
        
        # Approve project 1
        approve_payload1 = {
            "project_id": "project-alpha",
            "report_id": "RPT-ALPHA",
            "approved_by": "reviewer1",
            "comment": "Alpha approved"
        }
        
        response1 = client.post("/testing/report/approve", json=approve_payload1)
        assert response1.status_code == 200
        
        # Reject project 2
        reject_payload2 = {
            "project_id": "project-beta",
            "report_id": "RPT-BETA",
            "approved_by": "reviewer2",
            "comment": "Beta rejected"
        }
        
        response2 = client.post("/testing/report/reject", json=reject_payload2)
        assert response2.status_code == 200
        
        # Check project 1 is still approved
        response3 = client.get("/testing/report/approval-status/project-alpha")
        assert response3.json()["approval_status"] == "approved"
        
        # Check project 2 is still rejected
        response4 = client.get("/testing/report/approval-status/project-beta")
        assert response4.json()["approval_status"] == "rejected"
        
        # Check project 3 is still pending
        response5 = client.get("/testing/report/approval-status/project-gamma")
        assert response5.json()["approval_status"] == "pending"

    def test_approval_status_after_execute_endpoint(self):
        """Test that GET /testing/report/approval-status succeeds after POST /testing/execute initializes approval state."""
        client = TestClient(app)
        payload = {
            "project_id": "project-exec-approval-test",
            "srs": {"title": "SRS", "version": "1.0", "features": ["f1"]},
            "sdd": {"architecture": "arch", "components": ["c1"]},
            "source_code": {"repository": "repo", "language": "Python", "files": ["f.py"]},
        }
        res_exec = client.post("/testing/execute", json=payload)
        assert res_exec.status_code == 200

        # Retrieve approval status after execution initialized the store
        res_status = client.get("/testing/report/approval-status/project-exec-approval-test")
        assert res_status.status_code == 200
        body = res_status.json()
        assert body["approval_status"] == "pending"
        assert body["project_id"] == "project-exec-approval-test"
        assert body["release_allowed"] is False
        assert body["report_id"] is not None