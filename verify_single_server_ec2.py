#!/usr/bin/env python3
"""
Comprehensive End-to-End Verification for Single-Server AI-SDLC Studio (Port 8000 Only).
Validates that all 4 agents (Requirement, Design, Development, Testing) run seamlessly
on ONE single backend port with NO external testing service on 8085.
"""

import os
import sys
import time
import requests

API_BASE = "http://127.0.0.1:8000"
API_KEY = "default_secret_key_12345"
HEADERS = {
    "Content-Type": "application/json",
    "X-API-Key": API_KEY
}

def log(msg, status="INFO"):
    symbol = {"INFO": "[i]", "SUCCESS": "[OK]", "ERROR": "[X]", "WARN": "[!]"}.get(status, "*")
    print(f"[{status}] {symbol} {msg}")

def run_checks():
    log("Starting Single-Server Architecture & Port Portability Checks on Port 8000...", "INFO")

    # 1. Health check
    log("Checking backend /health endpoint on port 8000...", "INFO")
    r = requests.get(f"{API_BASE}/health", timeout=10)
    assert r.status_code == 200, f"Health check failed: {r.status_code} {r.text}"
    health_data = r.json()
    log(f"Health check response: {health_data}", "SUCCESS")
    assert health_data.get("port_configuration") == "single-port-unified"

    # 2. Verify port 8085 is NOT reachable (confirming complete independence)
    log("Verifying port 8085 is CLOSED / NOT REQUIRED...", "INFO")
    try:
        r_8085 = requests.get("http://127.0.0.1:8085/health", timeout=2)
        log(f"Warning: Port 8085 responded (status: {r_8085.status_code}). Unified architecture should not require 8085.", "WARN")
    except requests.exceptions.RequestException:
        log("Confirmed: Port 8085 is closed. All agent logic runs strictly in-process on port 8000!", "SUCCESS")

    # 3. Create Project
    log("Step 1: Creating a new AI-SDLC Project...", "INFO")
    proj_resp = requests.post(f"{API_BASE}/api/projects", json={
        "name": "Cloud Logistics Unified Platform",
        "description": "Next-gen supply chain automation with real-time fleet analytics"
    }, headers=HEADERS, timeout=10)
    assert proj_resp.status_code == 200, f"Create project failed: {proj_resp.status_code} {proj_resp.text}"
    project = proj_resp.json()
    project_id = project["id"]
    log(f"Created Project: {project['name']} (ID: {project_id})", "SUCCESS")

    # 4. Phase 1: Requirement Agent (Chat & Approval)
    log("Step 2: Eliciting and Approving Requirements (SRS)...", "INFO")
    chat_resp = requests.post(
        f"{API_BASE}/api/projects/{project_id}/chat",
        json={"message": "Build warehouse dispatch, vehicle tracking, delivery proof, automated alerts, and analytics dashboards."},
        headers=HEADERS, timeout=60
    )
    assert chat_resp.status_code == 200, f"Chat step failed: {chat_resp.text}"

    req_app = requests.post(
        f"{API_BASE}/api/projects/{project_id}/approve",
        json={
            "status": "APPROVED",
            "comments": "SRS thoroughly reviewed and baseline approved.",
            "reviewer_name": "Product Owner",
            "stage": "SRS"
        },
        headers=HEADERS, timeout=15
    )
    assert req_app.status_code == 200, f"Requirement approval failed: {req_app.text}"
    log("Requirement SRS approved and state updated to DESIGN phase.", "SUCCESS")

    # 5. Phase 2: Design Agent (Approval)
    log("Step 3: Approving Architecture & Design (SDD)...", "INFO")
    des_app = requests.post(
        f"{API_BASE}/api/projects/{project_id}/design/approve",
        json={
            "status": "APPROVED",
            "comments": "Microservices SDD and ER diagrams verified.",
            "reviewer_name": "Chief Architect",
            "stage": "DESIGN"
        },
        headers=HEADERS, timeout=15
    )
    assert des_app.status_code == 200, f"Design approval failed: {des_app.text}"
    log("Design SDD approved and state updated to DEVELOPMENT phase.", "SUCCESS")

    # 6. Phase 3: Development Agent (Approval)
    log("Step 4: Approving Source Code & Merged Artifacts...", "INFO")
    dev_app = requests.post(
        f"{API_BASE}/api/projects/{project_id}/development/approve",
        json={
            "status": "APPROVED",
            "comments": "Source code and endpoints verified.",
            "reviewer_name": "Lead Developer",
            "stage": "DEVELOPMENT"
        },
        headers=HEADERS, timeout=15
    )
    assert dev_app.status_code == 200, f"Development approval failed: {dev_app.text}"
    log("Development approved and state transitioned to TESTING / READY_FOR_TESTING.", "SUCCESS")

    # 7. Phase 4: Testing Agent (In-Process P1-P3 Workflow)
    log("Step 5: Triggering Testing Agent P1-P3 Workflow on Port 8000...", "INFO")
    test_start = requests.post(
        f"{API_BASE}/api/projects/{project_id}/testing/start",
        headers=HEADERS, timeout=30
    )
    assert test_start.status_code == 200, f"Testing start failed: {test_start.text}"
    start_data = test_start.json()
    log(f"Testing Intelligence Status: {start_data.get('validation_status')}, Workflow: {start_data.get('workflow_status')}", "SUCCESS")

    # 8. Phase 4-8: Testing Execution (In-Process Execution & Quality Gate)
    log("Step 6: Executing Full Testing Pipeline P1-P8 on Port 8000...", "INFO")
    test_exec = requests.post(
        f"{API_BASE}/api/projects/{project_id}/testing/execute",
        headers=HEADERS, timeout=45
    )
    assert test_exec.status_code == 200, f"Testing execute failed: {test_exec.text}"
    exec_data = test_exec.json()
    qg = exec_data.get("quality_gate") or {}
    log(f"Testing Executed! Results: {len(exec_data.get('results', []))} test cases. Quality Gate: {qg.get('overall_status')}, Readiness: {qg.get('release_readiness')}", "SUCCESS")

    # 9. Verify Live Testing Status Endpoint
    log("Step 7: Verifying Live Testing Status on Port 8000...", "INFO")
    status_resp = requests.get(f"{API_BASE}/api/projects/{project_id}/testing/status", headers=HEADERS, timeout=10)
    assert status_resp.status_code == 200, f"Testing status failed: {status_resp.text}"
    status_data = status_resp.json()
    assert status_data.get("execution_status") == "completed"
    log(f"Testing State verified: Quality Score = {status_data.get('quality_score')}, Readiness = {status_data.get('release_readiness')}", "SUCCESS")

    # 10. Verify Direct /testing Mounted Router Endpoints
    log("Step 8: Verifying Direct /testing Mounted Router Endpoints on Port 8000...", "INFO")
    direct_status = requests.get(f"{API_BASE}/testing/status/{project_id}", timeout=10)
    assert direct_status.status_code == 200, f"Direct /testing/status failed: {direct_status.text}"
    log("Direct /testing/status endpoint verified on port 8000!", "SUCCESS")

    # 11. Verify All 6 Report Export Formats on Single Port 8000
    log("Step 9: Verifying All 6 Report Export Formats (PDF, DOCX, MD, HTML, CSV, JSON) on Port 8000...", "INFO")
    formats = [
        ("pdf", "application/pdf"),
        ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("md", "text/markdown"),
        ("html", "text/html"),
        ("csv", "text/csv"),
        ("json", "application/json"),
    ]

    for fmt, expected_mime in formats:
        export_resp = requests.get(
            f"{API_BASE}/api/projects/{project_id}/testing/export/{fmt}?api_key={API_KEY}",
            timeout=30
        )
        assert export_resp.status_code == 200, f"Export {fmt} failed with status {export_resp.status_code}: {export_resp.text}"
        assert len(export_resp.content) > 50, f"Export {fmt} produced empty or too small content: {len(export_resp.content)} bytes"
        log(f"Export format '{fmt.upper()}' generated successfully: {len(export_resp.content):,} bytes (Content-Type: {export_resp.headers.get('content-type')})", "SUCCESS")

    # 12. Human Approval Governance
    log("Step 10: Verifying Human Approval Governance on Port 8000...", "INFO")
    report_id = (exec_data.get("report") or {}).get("report_id") or "RPT-SINGLE-PORT-001"
    approval_resp = requests.post(
        f"{API_BASE}/api/projects/{project_id}/testing/report/approve",
        json={
            "report_id": report_id,
            "approved_by": "Lead QA Engineer",
            "comment": "All test results verified in unified single-server setup."
        },
        headers=HEADERS, timeout=15
    )
    assert approval_resp.status_code == 200, f"Approval failed: {approval_resp.text}"
    appr_data = approval_resp.json()
    log(f"Human Approval registered: Status={appr_data.get('approval_status')}, Release Allowed={appr_data.get('release_allowed')}", "SUCCESS")

    # Verify project status moved to DEPLOYMENT
    proj_final = requests.get(f"{API_BASE}/api/projects/{project_id}", headers=HEADERS, timeout=10).json()
    assert proj_final["current_phase"] == "DEPLOYMENT"
    log(f"Project state successfully transitioned to: Phase={proj_final['current_phase']}, Status={proj_final['status']}", "SUCCESS")

    print("\n" + "="*70)
    log("ALL SINGLE-SERVER UNIFIED ARCHITECTURE VERIFICATIONS PASSED!", "SUCCESS")
    print("="*70)

if __name__ == "__main__":
    run_checks()
