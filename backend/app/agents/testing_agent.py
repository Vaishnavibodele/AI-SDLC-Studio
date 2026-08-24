"""
Testing Agent — AI SDLC Studio
Runs only when project.current_phase == "TESTING".

Phases:
  1. File Scope Validation    — diff manifest vs disk
  2. Service Verification     — spawn generated app on isolated port
  3. Endpoint Tests           — HTTP requests from API.json spec
  4. Data Integrity Checks    — verify DB mutations in isolated test DB
  5. Regression Tests         — compare with previous PASS reports
  6. Manual Verification      — list items requiring human eyeballing
  7. Verdict                  — PASS | FAIL | PASS_WITH_WARNINGS
"""

import os
import sys
import json
import time
import zipfile
import subprocess
import sqlite3
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional

from sqlalchemy.orm import Session
from .. import models


# ─── Process Registry ───────────────────────────────────────────────────────
_active_processes: Dict[str, subprocess.Popen] = {}

def register_running_process(project_id: str, proc: subprocess.Popen):
    _active_processes[project_id] = proc

def unregister_running_process(project_id: str):
    _active_processes.pop(project_id, None)

def kill_running_process(project_id: str):
    proc = _active_processes.pop(project_id, None)
    if proc:
        try:
            proc.kill()
            proc.wait(timeout=3)
        except Exception:
            pass


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _derive_port(project_id: str) -> int:
    """Map project_id to a stable port in 8200–8900 (avoids 8000 backend)."""
    return 8200 + (sum(ord(c) for c in project_id) % 700)


def _extract_zip(zip_path: str, extract_to: str) -> None:
    os.makedirs(extract_to, exist_ok=True)
    if os.path.exists(zip_path):
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extract_to)


def _scan_disk(base_dir: str) -> List[str]:
    """Return relative posix paths of all non-cache, non-db files under base_dir."""
    result = []
    for root, dirs, files in os.walk(base_dir):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for f in files:
            if f.endswith(".db"):
                continue
            full = os.path.join(root, f)
            rel = os.path.relpath(full, base_dir).replace("\\", "/")
            result.append(rel)
    return result


def _probe_url(url: str, timeout: int = 3) -> bool:
    """Return True if URL responds with any HTTP status."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return True
    except urllib.error.HTTPError:
        return True          # got a response — server is up
    except Exception:
        return False


def _http_request(method: str, url: str, body: Optional[bytes] = None,
                  headers: Optional[dict] = None, timeout: int = 6):
    """Make an HTTP request; return (status_code, body_dict)."""
    req = urllib.request.Request(url, data=body,
                                 headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status = r.status
            try:
                body_json = json.loads(r.read().decode())
            except Exception:
                body_json = {}
            return status, body_json
    except urllib.error.HTTPError as he:
        try:
            err_body = json.loads(he.read().decode())
        except Exception:
            err_body = {"error": he.reason}
        return he.code, err_body
    except Exception as ex:
        return 0, {"error": str(ex)}


# ─── Main Agent ──────────────────────────────────────────────────────────────

def run_testing_agent(db: Session, project_id: str, dev_version_id: str) -> Dict[str, Any]:
    """Execute all testing phases and return a structured report dict."""

    # ── Guard: must be in TESTING phase ──────────────────────────────────────
    project = db.query(models.Project).filter(models.Project.id == project_id).first()
    if not project:
        raise ValueError("Project not found")
    if project.current_phase != "TESTING":
        raise ValueError(f"PHASE_LOCKED: project is in {project.current_phase}, not TESTING")

    dev_version = db.query(models.DevelopmentVersion).filter(
        models.DevelopmentVersion.id == dev_version_id
    ).first()
    if not dev_version:
        raise ValueError("Development version not found")

    ver_num = dev_version.version_num
    print(f"[TestingAgent] Starting — project={project_id}, version={ver_num}")

    # ── Artifact paths ────────────────────────────────────────────────────────
    artifacts_root = os.path.join(os.getcwd(), "scratch", "dev_zips",
                                  f"{project_id}_v{ver_num}")
    manifest_path = os.path.join(artifacts_root, "Manifest.json")
    api_json_path = os.path.join(artifacts_root, "API.json")
    zip_path      = os.path.join(artifacts_root, "Source.zip")
    extracted_dir = os.path.join(artifacts_root, "extracted")

    # ── Load SRS (for manual verification hints) ──────────────────────────────
    req_ver = (
        db.query(models.RequirementVersion)
        .join(models.Requirement)
        .filter(models.Requirement.project_id == project_id)
        .order_by(models.RequirementVersion.version_num.desc())
        .first()
    )
    srs_text = req_ver.raw_srs if req_ver else ""

    # ── Collect failures and warnings ─────────────────────────────────────────
    failures: List[str] = []
    is_blocked = False

    # ═══════════════════════════════════════════════════════════════
    # PHASE 0 — Check artifact files exist (blocking if missing)
    # ═══════════════════════════════════════════════════════════════
    missing_artifacts = []
    if not os.path.exists(manifest_path):
        missing_artifacts.append("Manifest.json")
    if not os.path.exists(api_json_path):
        missing_artifacts.append("API.json")

    if missing_artifacts:
        msg = f"Missing required artifacts: {missing_artifacts}"
        failures.append(msg)
        return _blocked_report(project_id, dev_version_id, msg)

    # Load both files
    with open(manifest_path, encoding="utf-8") as f:
        manifest_items: list = json.load(f)
    with open(api_json_path, encoding="utf-8") as f:
        api_spec: dict = json.load(f)

    # ═══════════════════════════════════════════════════════════════
    # PHASE 1 — File Scope Validation
    # ═══════════════════════════════════════════════════════════════
    _extract_zip(zip_path, extracted_dir)

    expected_paths = {
        item.get("path") for item in manifest_items if item.get("path")
    }
    actual_paths   = set(_scan_disk(extracted_dir))

    missing_files    = sorted(expected_paths - actual_paths)
    undeclared_files = sorted(actual_paths   - expected_paths)
    file_scope_issues = []

    for p in missing_files:
        file_scope_issues.append({
            "file_path": p,
            "issue_type": "MISSING_FILE",
            "details": "Declared in Manifest but not found on disk."
        })
    for p in undeclared_files:
        file_scope_issues.append({
            "file_path": p,
            "issue_type": "UNDECLARED_CHANGE",
            "details": "File on disk not declared in Manifest."
        })

    if missing_files:
        failures.append(f"File scope FAIL — missing: {missing_files}")
        is_blocked = True

    # ═══════════════════════════════════════════════════════════════
    # PHASE 2 — Service Verification
    # ═══════════════════════════════════════════════════════════════
    port = _derive_port(project_id)
    service_started = False
    startup_log = ""
    proc = None

    if not is_blocked:
        env = os.environ.copy()
        env["DATABASE_URL"] = f"sqlite:///{os.path.join(extracted_dir, 'sdlc_studio_test.db')}"
        env["PORT"] = str(port)

        cmd = [sys.executable, "-m", "uvicorn", "app.main:app",
               "--host", "127.0.0.1", "--port", str(port)]
        print(f"[TestingAgent] Spawning generated app on port {port}…")

        try:
            proc = subprocess.Popen(
                cmd, cwd=extracted_dir,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=env, text=True
            )
            register_running_process(project_id, proc)
            # Give it time to start
            for _ in range(6):
                time.sleep(1)
                if _probe_url(f"http://127.0.0.1:{port}/") or \
                   _probe_url(f"http://127.0.0.1:{port}/api"):
                    service_started = True
                    break

            if not service_started:
                try:
                    out, _ = proc.communicate(timeout=3)
                    startup_log = out or ""
                except subprocess.TimeoutExpired:
                    proc.kill()
                    out, _ = proc.communicate()
                    startup_log = out or ""
                failures.append(f"Service failed to start on port {port}.")
                is_blocked = True
                proc = None

        except Exception as ex:
            startup_log = str(ex)
            failures.append(f"Could not spawn generated app: {ex}")
            is_blocked = True

    else:
        startup_log = "Skipped — blocked by file scope failure."

    # Build traceability map: file_path → requirement_id
    traceability: Dict[str, str] = {}
    for item in manifest_items:
        if item.get("path") and item.get("requirement_id"):
            traceability[item["path"]] = item["requirement_id"]

    # ═══════════════════════════════════════════════════════════════
    # PHASE 3 — Endpoint Tests
    # ═══════════════════════════════════════════════════════════════
    endpoint_tests: List[Dict] = []
    data_integrity_checks: List[Dict] = []

    paths_spec: Dict = api_spec.get("paths", {})

    if not is_blocked:
        for path_tpl, methods_map in paths_spec.items():
            for method, spec_detail in methods_map.items():
                method_upper = method.upper()
                url = f"http://127.0.0.1:{port}{path_tpl}"

                # Build a generic payload for mutating requests
                req_body  = None
                req_hdrs  = {}
                if method_upper in ("POST", "PUT", "PATCH"):
                    sample = _build_sample_payload(spec_detail)
                    req_body = json.dumps(sample).encode()
                    req_hdrs = {"Content-Type": "application/json"}

                t0 = time.time()
                status_code, resp_body = _http_request(
                    method_upper, url, req_body, req_hdrs
                )
                latency = round(time.time() - t0, 3)

                result = "PASS" if status_code in (200, 201, 204) else "FAIL"

                # Requirement traceability
                linked_req = "N/A"
                for fpath, rid in traceability.items():
                    if "main" in fpath or "router" in fpath:
                        linked_req = rid
                        break

                endpoint_tests.append({
                    "name": f"{method_upper} {path_tpl}",
                    "method": method_upper,
                    "path": path_tpl,
                    "url": url,
                    "payload": json.loads(req_body.decode()) if req_body else None,
                    "expected_status": 200,
                    "actual_status": status_code,
                    "actual_body": resp_body,
                    "latency": latency,
                    "result": result,
                    "requirement_id": linked_req
                })

                if result == "FAIL":
                    failures.append(f"Endpoint FAIL: {method_upper} {path_tpl} → {status_code}")

                # ── Data integrity check for POST endpoints ──────────────────
                if method_upper == "POST":
                    di = _check_db_integrity(extracted_dir, path_tpl, result)
                    data_integrity_checks.append(di)
                    if di["result"] == "FAIL":
                        failures.append(f"DB integrity FAIL: {path_tpl} — {di['details']}")

        # Shut down spawned server cleanly
        if proc:
            try:
                proc.kill()
                proc.wait(timeout=5)
            except Exception:
                pass
            unregister_running_process(project_id)

    else:
        # Mark all tests as NOT_EXECUTED
        for path_tpl, methods_map in paths_spec.items():
            for method in methods_map:
                endpoint_tests.append({
                    "name": f"{method.upper()} {path_tpl}",
                    "method": method.upper(),
                    "path": path_tpl,
                    "url": f"http://127.0.0.1:{port}{path_tpl}",
                    "payload": None,
                    "expected_status": 200,
                    "actual_status": None,
                    "actual_body": None,
                    "latency": 0,
                    "result": "NOT_EXECUTED",
                    "requirement_id": "N/A"
                })

    # ═══════════════════════════════════════════════════════════════
    # PHASE 4 — Regression Tests (compare with prior PASS reports)
    # ═══════════════════════════════════════════════════════════════
    regression_tests: List[Dict] = []
    prior_pass_reports = (
        db.query(models.TestingReport)
        .filter(
            models.TestingReport.project_id == project_id,
            models.TestingReport.status == "PASS"
        )
        .order_by(models.TestingReport.version_num.desc())
        .all()
    )
    for pr in prior_pass_reports:
        try:
            old = json.loads(pr.raw_report)
            for t in old.get("endpoint_tests", []):
                was_pass = t.get("result") == "PASS"
                # Find current result for same endpoint
                current = next(
                    (ct for ct in endpoint_tests
                     if ct["method"] == t.get("method") and ct["path"] == t.get("path")),
                    None
                )
                cur_result = current["result"] if current else "NOT_EXECUTED"
                regression_tests.append({
                    "name": f"[Regression v{pr.version_num}] {t.get('method')} {t.get('path')}",
                    "method": t.get("method"),
                    "path": t.get("path"),
                    "previous_result": "PASS",
                    "current_result": cur_result,
                    "result": cur_result,
                    "source_version": pr.version_num
                })
                if cur_result == "FAIL" and was_pass:
                    failures.append(
                        f"Regression: {t.get('method')} {t.get('path')} "
                        f"was PASS in v{pr.version_num}, now FAIL"
                    )
        except Exception:
            pass

    # ═══════════════════════════════════════════════════════════════
    # PHASE 5 — Manual Verification Checklist
    # ═══════════════════════════════════════════════════════════════
    manual_verification_needed: List[str] = []
    srs_lower = srs_text.lower()
    api_lower = json.dumps(api_spec).lower()

    if "stripe" in srs_lower or "payment" in srs_lower:
        manual_verification_needed.append(
            "Verify payment gateway processing with Stripe test credentials in the browser."
        )
    if "checkout" in api_lower:
        manual_verification_needed.append(
            "Manually confirm full checkout UX flow (cart → payment → confirmation) in browser."
        )
    if "tailwind" in srs_lower or "responsive" in srs_lower:
        manual_verification_needed.append(
            "Verify responsive UI layout on mobile (375px) and desktop (1440px)."
        )
    if "auth" in srs_lower or "login" in srs_lower:
        manual_verification_needed.append(
            "Manually test login/logout session management and protected route guards."
        )

    # ═══════════════════════════════════════════════════════════════
    # PHASE 6 — Determine Verdict
    # ═══════════════════════════════════════════════════════════════
    failed_endpoints = [t for t in endpoint_tests if t["result"] == "FAIL"]
    failed_di        = [t for t in data_integrity_checks if t["result"] == "FAIL"]
    failed_regressions = [t for t in regression_tests if t["current_result"] == "FAIL"]

    if failures or is_blocked:
        verdict = "FAIL"
        recommendation = "SEND_BACK_TO_DEV"
        summary = (
            f"Testing FAILED with {len(failures)} blocking issue(s). "
            f"Endpoint failures: {len(failed_endpoints)}. "
            f"DB integrity failures: {len(failed_di)}. "
            f"Regression failures: {len(failed_regressions)}."
        )
    elif undeclared_files or manual_verification_needed:
        verdict = "PASS_WITH_WARNINGS"
        recommendation = "NEEDS_HUMAN_REVIEW"
        summary = (
            f"Automated tests passed with {len(undeclared_files)} undeclared file(s) "
            f"and {len(manual_verification_needed)} manual verification item(s)."
        )
    else:
        verdict = "PASS"
        recommendation = "APPROVE"
        summary = (
            f"All {len(endpoint_tests)} endpoint tests passed. "
            f"{len(data_integrity_checks)} DB integrity check(s) verified. "
            f"No regressions detected."
        )

    return {
        "status": verdict,
        "project_id": project_id,
        "development_version_id": dev_version_id,
        "file_scope": {
            "expected_count": len(expected_paths),
            "actual_count": len(actual_paths),
            "missing": missing_files,
            "undeclared": undeclared_files
        },
        "service_verification": {
            "started": service_started,
            "port": port,
            "startup_log": startup_log[:2000]      # cap log size
        },
        "endpoint_tests": endpoint_tests,
        "regression_tests": regression_tests,
        "data_integrity_checks": data_integrity_checks,
        "manual_verification_needed": manual_verification_needed,
        "file_scope_issues": file_scope_issues,
        "failures": failures,
        "summary": summary,
        "recommendation": recommendation,
        "stats": {
            "total_endpoints": len(endpoint_tests),
            "passed": len([t for t in endpoint_tests if t["result"] == "PASS"]),
            "failed": len(failed_endpoints),
            "not_executed": len([t for t in endpoint_tests if t["result"] == "NOT_EXECUTED"]),
            "regressions": len(failed_regressions),
            "db_checks": len(data_integrity_checks),
            "db_failures": len(failed_di)
        }
    }


# ─── Private helpers ──────────────────────────────────────────────────────────

def _blocked_report(project_id: str, dev_version_id: str, msg: str) -> Dict:
    return {
        "status": "FAIL",
        "project_id": project_id,
        "development_version_id": dev_version_id,
        "file_scope": {"expected_count": 0, "actual_count": 0, "missing": [], "undeclared": []},
        "service_verification": {"started": False, "port": 0, "startup_log": msg},
        "endpoint_tests": [],
        "regression_tests": [],
        "data_integrity_checks": [],
        "manual_verification_needed": [],
        "file_scope_issues": [],
        "failures": [msg],
        "summary": f"Testing aborted: {msg}",
        "recommendation": "SEND_BACK_TO_DEV",
        "stats": {
            "total_endpoints": 0, "passed": 0, "failed": 0,
            "not_executed": 0, "regressions": 0,
            "db_checks": 0, "db_failures": 0
        }
    }


def _build_sample_payload(spec_detail: dict) -> dict:
    """Generate a minimal sample JSON body from OpenAPI requestBody schema."""
    try:
        schema = (
            spec_detail.get("requestBody", {})
            .get("content", {})
            .get("application/json", {})
            .get("schema", {})
        )
        props = schema.get("properties", {})
        sample = {}
        for key, val in props.items():
            t = val.get("type", "string")
            if t == "string":
                sample[key] = "test_value"
            elif t == "integer":
                sample[key] = 1
            elif t == "number":
                sample[key] = 9.99
            elif t == "boolean":
                sample[key] = True
            elif t == "array":
                sample[key] = []
            else:
                sample[key] = {}
        return sample if sample else {"item": "test", "quantity": 1, "price": 9.99}
    except Exception:
        return {"item": "test", "quantity": 1, "price": 9.99}


def _check_db_integrity(extracted_dir: str, path_tpl: str, endpoint_result: str) -> Dict:
    """Check the isolated test DB for state-change evidence after a POST call."""
    db_file = os.path.join(extracted_dir, "sdlc_studio_test.db")
    if not os.path.exists(db_file):
        return {
            "trigger": f"POST {path_tpl}",
            "assertion": "State-mutating endpoint should write to isolated DB.",
            "result": "FAIL" if endpoint_result == "PASS" else "NOT_EXECUTED",
            "details": "sdlc_studio_test.db was not created by the generated app."
        }
    try:
        conn = sqlite3.connect(db_file)
        c = conn.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in c.fetchall()]
        details = f"Tables in isolated DB: {tables}."
        found_data = False
        for tbl in tables:
            if any(kw in tbl.lower() for kw in ("order", "checkout", "cart", "item", "product")):
                c.execute(f"SELECT COUNT(*) FROM {tbl}")
                count = c.fetchone()[0]
                details += f" {tbl}: {count} rows."
                if count > 0:
                    found_data = True
        conn.close()
        di_result = "PASS" if (endpoint_result == "PASS" and found_data) else (
            "NOT_EXECUTED" if endpoint_result != "PASS" else "FAIL"
        )
        if di_result == "FAIL":
            details += " No rows written after successful endpoint call."
        return {
            "trigger": f"POST {path_tpl}",
            "assertion": "Rows should be written to the isolated test DB.",
            "result": di_result,
            "details": details
        }
    except Exception as ex:
        return {
            "trigger": f"POST {path_tpl}",
            "assertion": "Rows should be written to the isolated test DB.",
            "result": "FAIL",
            "details": f"SQLite inspection error: {ex}"
        }
