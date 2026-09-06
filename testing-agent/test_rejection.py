import requests

BASE_URL = "http://127.0.0.1:8085"

def test_rejection():
    # 1. Execute run
    payload = {
        "project_id": "proj-rejection-test",
        "srs": {"title": "Test", "version": "1.0", "features": ["F1"]},
        "sdd": {"architecture": "Arch", "components": ["C1"], "interfaces": ["I1"]},
        "source_code": {"repository": "repo", "language": "Python", "files": ["f.py"]}
    }
    r = requests.post(f"{BASE_URL}/testing/execute", json=payload)
    assert r.status_code == 200
    report_id = r.json().get("report", {}).get("report_id", "RPT-REJ")

    # 2. Reject
    rej_payload = {
        "project_id": "proj-rejection-test",
        "report_id": report_id,
        "approved_by": "Senior QA Auditor",
        "comment": "Blocking release due to critical defect in authentication flow."
    }
    r = requests.post(f"{BASE_URL}/testing/report/reject", json=rej_payload)
    print(f"Rejection response status: {r.status_code}")
    print(f"Rejection response: {r.json()}")
    assert r.status_code == 200
    assert r.json().get("approval_status") == "rejected"
    assert r.json().get("release_allowed") is False
    assert r.json().get("comment") == "Blocking release due to critical defect in authentication flow."
    print("Rejection test PASSED!")

if __name__ == "__main__":
    test_rejection()
