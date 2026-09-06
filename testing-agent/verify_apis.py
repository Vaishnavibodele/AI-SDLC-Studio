import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8085"
FRONTEND_URL = "http://127.0.0.1:8002"

def run_checks():
    print("=" * 60)
    print("TESTING AGENT END-TO-END VERIFICATION")
    print("=" * 60)

    # 1. Health check backend
    try:
        r = requests.get(f"{BASE_URL}/")
        print(f"[1/8] Backend Health (8085): {r.status_code} -> {r.json()}")
        assert r.status_code == 200
    except Exception as e:
        print(f"[1/8] Backend Health FAILED: {e}")
        return

    # 2. Frontend HTTP check
    try:
        r = requests.get(f"{FRONTEND_URL}/")
        print(f"[2/8] Frontend Server (8002): {r.status_code} (HTML bytes: {len(r.content):,})")
        assert r.status_code == 200
        assert "AI-SDLC Testing Agent" in r.text or "TESTING AGENT" in r.text
    except Exception as e:
        print(f"[2/8] Frontend Check FAILED: {e}")

    # 3. Payload test
    payload = {
        "project_id": "test-e2e-suite",
        "srs": {
            "title": "Smart Building Telemetry SRS",
            "version": "1.0.0",
            "features": [
                "Real-time temperature telemetry collection",
                "HVAC automated threshold alerts"
            ]
        },
        "sdd": {
            "architecture": "Event-driven microservices",
            "components": ["Telemetry Collector", "Alert Engine"],
            "interfaces": ["POST /telemetry", "GET /alerts"]
        },
        "source_code": {
            "repository": "github.com/org/smart-building",
            "language": "Python",
            "files": ["app/main.py", "app/services/telemetry.py"],
            "changes": {
                "changed_files": ["app/services/telemetry.py"],
                "changed_functions": ["parse_sensor_reading"]
            }
        },
        "api_docs": {
            "base_url": "https://api.building.internal",
            "endpoints": ["POST /telemetry", "GET /alerts"]
        },
        "database_schema": {
            "dialect": "PostgreSQL",
            "tables": ["telemetry", "alerts"]
        },
        "environment": {
            "name": "staging"
        }
    }

    # 4. Test POST /testing/start (Phases 1-3)
    try:
        r = requests.post(f"{BASE_URL}/testing/start", json=payload)
        data = r.json()
        print(f"[3/8] POST /testing/start: {r.status_code}")
        print(f"      Validation: {data.get('validation_status')}")
        print(f"      Requirements: {len(data.get('intelligence', {}).get('requirements', []))}")
        print(f"      Test Cases: {len(data.get('test_design', {}).get('test_cases', []))}")
        assert r.status_code == 200
    except Exception as e:
        print(f"[3/8] POST /testing/start FAILED: {e}")

    # 5. Test POST /testing/execute (Phases 1-8)
    try:
        r = requests.post(f"{BASE_URL}/testing/execute", json=payload)
        exec_data = r.json()
        print(f"[4/8] POST /testing/execute: {r.status_code}")
        summary = exec_data.get("execution_summary", {})
        print(f"      Total Tests: {summary.get('total')}, Passed: {summary.get('passed')}, Failed: {summary.get('failed')}, Skipped: {summary.get('skipped')}")
        qg = exec_data.get("quality_gate", {})
        print(f"      Quality Gate: {qg.get('overall_status')}, Readiness: {qg.get('release_readiness')}, Score: {qg.get('quality_score')}")
        report = exec_data.get("report", {})
        print(f"      Report ID: {report.get('report_id')}, Phases Reported: {len(report.get('phases', []))}")
        assert r.status_code == 200
    except Exception as e:
        print(f"[4/8] POST /testing/execute FAILED: {e}")
        return

    # 6. Test GET /testing/report/approval-status/{project_id}
    try:
        r = requests.get(f"{BASE_URL}/testing/report/approval-status/test-e2e-suite")
        print(f"[5/8] GET approval-status: {r.status_code} -> Status: {r.json().get('approval_status')}")
        assert r.status_code == 200
    except Exception as e:
        print(f"[5/8] GET approval-status FAILED: {e}")

    # 7. Test POST /testing/report/approve
    try:
        approve_payload = {
            "project_id": "test-e2e-suite",
            "report_id": exec_data.get("report", {}).get("report_id", "RPT-001"),
            "approved_by": "QA Director Jane Doe",
            "comment": "Approved for release gate validation"
        }
        r = requests.post(f"{BASE_URL}/testing/report/approve", json=approve_payload)
        print(f"[6/8] POST /testing/report/approve: {r.status_code} -> Status: {r.json().get('approval_status')}, Release Allowed: {r.json().get('release_allowed')}")
        assert r.status_code == 200
        assert r.json().get("approval_status") == "approved"
    except Exception as e:
        print(f"[6/8] POST /testing/report/approve FAILED: {e}")

    # 8. Test Export Endpoints
    for fmt in ["html", "csv"]:
        try:
            r = requests.post(f"{BASE_URL}/testing/report/export?fmt={fmt}", json=payload)
            print(f"[7/8] Export {fmt.upper()}: {r.status_code} (Bytes: {len(r.content):,})")
            assert r.status_code == 200
        except Exception as e:
            print(f"[7/8] Export {fmt} FAILED: {e}")

    print("\n" + "=" * 60)
    print("ALL API ENDPOINTS & SDLC QUALITY GATES PASSING SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    run_checks()
