import json
import os
import requests
from fastapi import FastAPI, Depends, HTTPException, Response, Security, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session
from typing import List, Optional

from .database import Base, engine, get_db
from . import schemas, models
from .services import project_service, agent_service, design_service, document_generator, development_service

from sqlalchemy import text

# Initialize tables
Base.metadata.create_all(bind=engine)

API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)

def verify_api_key(request: Request, api_key: Optional[str] = Security(api_key_header)):
    # Allow health check, root, and docs to pass without key
    if request.url.path in ["/", "/health", "/docs", "/openapi.json", "/redoc"]:
        return
    # Support both header and query param for downloads/window.open
    actual_key = api_key or request.query_params.get("api_key")
    expected_key = os.getenv("STUDIO_API_KEY", "default_secret_key_12345")
    if not actual_key or actual_key != expected_key:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing API Key"
        )

app = FastAPI(
    title="AI SDLC Studio API",
    version="1.0.0",
    dependencies=[Depends(verify_api_key)]
)

@app.get("/")
def read_root():
    return {
        "status": "online",
        "service": "AI SDLC Studio Backend API",
        "version": "2.0.0",
        "frontend_url": "http://localhost:3000",
        "api_docs": "http://127.0.0.1:8000/docs",
        "message": "AI SDLC Studio Backend API is running successfully. Please open the user interface at http://localhost:3000"
    }

# CORS middleware config
origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/api/projects", response_model=schemas.ProjectResponse)
def create_project(project: schemas.ProjectCreate, db: Session = Depends(get_db)):
    return project_service.create_project(db, project)

@app.get("/api/projects", response_model=List[schemas.ProjectResponse])
def list_projects(db: Session = Depends(get_db)):
    return project_service.list_projects(db)

@app.get("/api/projects/{project_id}", response_model=schemas.ProjectResponse)
def get_project(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return proj

@app.post("/api/projects/{project_id}/chat", response_model=schemas.ChatResponse)
def chat_with_agent(project_id: str, request: schemas.ChatRequest, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
        
    try:
        result = agent_service.run_chat_step(db, project_id, request.message)
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Agent runtime error: {str(e)}")

@app.post("/api/projects/{project_id}/approve")
def approve_or_reject_srs(project_id: str, review: schemas.HumanReviewSubmit, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        result = agent_service.resume_approval_step(
            db=db, 
            project_id=project_id, 
            status=review.status, 
            comments=review.comments,
            reviewer_name=review.reviewer_name,
            stage=review.stage
        )
        proj_updated = project_service.get_project(db, project_id)
        if review.status == "APPROVED" and proj_updated and proj_updated.current_phase == "DESIGN":
            return {
                "success": True,
                "current_phase": "DESIGN",
                "status": "IN_PROGRESS",
                "redirect": "/design",
                "design_initialized": True
            }
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Approval state processing error: {str(e)}")

@app.get("/api/projects/{project_id}/requirements/state")
def get_requirements_state(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return agent_service.get_agent_state_details(project_id)

@app.post("/api/projects/{project_id}/requirements/approve")
def approve_requirements_stage(project_id: str, review: schemas.HumanReviewSubmit, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return agent_service.resume_approval_step(
            db=db,
            project_id=project_id,
            status="APPROVED",
            comments=review.comments,
            reviewer_name=review.reviewer_name,
            stage=review.stage
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        # Fallback to force transition to DESIGN phase with approved SRS
        try:
            effective_srs, _ = project_service.get_effective_srs_data(db, project_id)
            if effective_srs:
                project_service.create_or_update_requirement_srs(db, project_id, effective_srs, status="APPROVED", comments=review.comments or "SRS Approved")
        except Exception as se:
            print(f"Fallback SRS save error: {se}")
        proj.current_phase = "DESIGN"
        proj.status = "APPROVED"
        db.commit()
        try:
            design_service.start_design_generation(db, project_id)
        except Exception as de:
            print(f"Fallback design generation error: {de}")
        return {"status": "completed", "current_phase": "DESIGN"}

@app.post("/api/projects/{project_id}/requirements/reject")
def reject_requirements_stage(project_id: str, review: schemas.HumanReviewSubmit, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return agent_service.resume_approval_step(
            db=db,
            project_id=project_id,
            status="REJECTED",
            comments=review.comments,
            reviewer_name=review.reviewer_name,
            stage=review.stage
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/projects/{project_id}/requirements/upload")
async def upload_requirement_document(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    if not file:
        raise HTTPException(status_code=400, detail="No file uploaded.")
        
    try:
        file_bytes = await file.read()
        from .services import document_parser, input_guardrails
        text = document_parser.parse_document(file_bytes, file.filename)
        
        # Guardrails check
        if not input_guardrails.check_relevance(text):
            raise HTTPException(status_code=400, detail="Relevance Guardrail failed: Content is not relevant to software development.")
        if input_guardrails.detect_prompt_injection(text):
            raise HTTPException(status_code=400, detail="Guardrail alert: Prompt injection detected.")
            
        result = agent_service.run_chat_step(db, project_id, f"Document Uploaded: {file.filename}\n\nContent:\n{text}")
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"File processing error: {str(e)}")

@app.get("/api/projects/{project_id}/design/state")
def get_design_state(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return design_service.get_design_state_details(project_id, db)

@app.post("/api/projects/{project_id}/design/approve")
def approve_design_stage(project_id: str, review: schemas.HumanReviewSubmit, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return design_service.resume_design_approval(
            db=db,
            project_id=project_id,
            status="APPROVED",
            comments=review.comments,
            reviewer_name=review.reviewer_name,
            stage=review.stage
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/projects/{project_id}/design/reject")
def reject_design_stage(project_id: str, review: schemas.HumanReviewSubmit, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        return design_service.resume_design_approval(
            db=db,
            project_id=project_id,
            status="REJECTED",
            comments=review.comments,
            reviewer_name=review.reviewer_name,
            stage=review.stage
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/projects/{project_id}/status")
def get_project_status(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
        
    # Fetch details from requirement checkpointer memory
    state_details = agent_service.get_agent_state_details(project_id)
    
    # Fetch details from design checkpointer memory
    design_state = design_service.get_design_state_details(project_id, db)

    # Fetch details from development checkpointer memory
    dev_state = development_service.get_development_state(project_id, db)
    
    # Fetch database record for SRS
    latest_srs = project_service.get_latest_srs_version(db, project_id)
    srs_data = None
    if latest_srs and latest_srs.raw_srs:
        try:
            srs_data = json.loads(latest_srs.raw_srs)
        except Exception:
            pass
    if not srs_data and (proj.status == "APPROVED" or proj.current_phase in ["DESIGN", "DEVELOPMENT", "TESTING"]):
        srs_data, _ = project_service.get_effective_srs_data(db, project_id)
        
    # Fetch database record for SDD
    design_doc, latest_design = design_service.get_latest_design_version(db, project_id)
    sdd_data = None
    if latest_design:
        sdd_data = json.loads(latest_design.raw_sdd)
    elif design_state and design_state.get("sdd"):
        sdd_data = design_state.get("sdd")
    elif proj.current_phase == "DESIGN" or proj.status == "APPROVED":
        agent_state = db.query(project_service.models.ProjectAgentState).filter(
            project_service.models.ProjectAgentState.project_id == project_id
        ).first()
        if agent_state and agent_state.document:
            try:
                approved_doc = schemas.ProjectDocument(**json.loads(agent_state.document))
                from .agents.design_agent import build_fallback_sdd
                sdd_data = build_fallback_sdd(approved_doc, {"srs_status": "APPROVED"})
            except Exception as fe:
                print(f"Fallback SDD generation error: {fe}")
                pass
        
    activity_logs = project_service.get_activity_logs(db, project_id)
    
    # 1. Calculate Requirement Completeness % logically
    mem_obj = state_details.get("memory")
    mem_dict = mem_obj.dict() if hasattr(mem_obj, "dict") else (mem_obj if isinstance(mem_obj, dict) else {})
    doc_obj = state_details.get("document")
    doc_dict = doc_obj.dict() if hasattr(doc_obj, "dict") else (doc_obj if isinstance(doc_obj, dict) else {})
    
    elicitation_completeness = project_service.calculate_elicitation_completeness(mem_dict)
    srs_completeness = project_service.calculate_srs_completeness(srs_data=srs_data, doc_dict=doc_dict)

    req_completeness = project_service.calculate_logical_requirement_completeness(
        memory_dict=mem_dict,
        srs_data=srs_data if (latest_srs or proj.status == "APPROVED") else None,
        doc_dict=doc_dict,
        is_approved=(proj.status == "APPROVED" or proj.current_phase != "REQUIREMENT")
    )
        
    # 2. Calculate Design Completeness %
    design_completeness = 0
    if sdd_data:
        sections = [
            "cover_page", "revision_history", "approval_history", "introduction", "design_goals",
            "system_overview", "high_level_architecture", "low_level_architecture", "module_breakdown",
            "system_context_diagram_mermaid", "use_case_diagram_mermaid", "component_diagram_mermaid",
            "class_diagram_mermaid", "sequence_diagram_mermaid", "activity_diagram_mermaid",
            "er_diagram_mermaid", "deployment_diagram_mermaid", "flow_diagram_mermaid",
            "db_relationship_diagram_mermaid", "database_design_overview", "database_tables",
            "database_relationships", "database_constraints", "api_design_overview", "api_endpoints",
            "authentication_flow", "authorization_flow", "security_design_policies", "logging_strategy",
            "exception_handling", "configuration_management", "technology_stack", "folder_structure",
            "coding_standards", "performance_design", "scalability_design", "availability_design",
            "monitoring_strategy", "backup_strategy", "disaster_recovery_runbook", "architectural_risks",
            "design_assumptions", "future_enhancements", "traceability_matrix"
        ]
        filled = sum(1 for k in sections if sdd_data.get(k) and (not isinstance(sdd_data[k], list) or len(sdd_data[k]) > 0))
        design_completeness = int((filled / len(sections)) * 100)
        
    # 3. Calculate API Count, Table Count, Diagram Count
    api_count = len(sdd_data.get("api_endpoints", [])) if sdd_data else 0
    table_count = len(sdd_data.get("database_tables", [])) if sdd_data else 0
    diagram_count = 0
    if sdd_data:
        diagram_fields = [
            "system_context_diagram_mermaid", "use_case_diagram_mermaid", "component_diagram_mermaid",
            "class_diagram_mermaid", "sequence_diagram_mermaid", "activity_diagram_mermaid",
            "er_diagram_mermaid", "deployment_diagram_mermaid", "flow_diagram_mermaid",
            "db_relationship_diagram_mermaid"
        ]
        diagram_count = sum(1 for f in diagram_fields if sdd_data.get(f))
        
    # 4. Calculate Requirement Coverage %
    coverage_percent = 0
    if srs_data and sdd_data:
        func_reqs = srs_data.get("functional_requirements", [])
        traceability_matrix = sdd_data.get("traceability_matrix", [])
        if func_reqs:
            mapped_ids = {item.get("requirement_id") for item in traceability_matrix if item.get("requirement_id")}
            srs_matrix = srs_data.get("requirement_traceability_matrix", [])
            total_reqs = len(srs_matrix) if srs_matrix else len(func_reqs)
            
            coverage_percent = int((len(mapped_ids) / total_reqs) * 100) if total_reqs > 0 else 0
            coverage_percent = min(coverage_percent, 100)
            
    # 5. Architecture Quality Score
    quality_score = 0
    if sdd_data:
        quality_score = 90
        if coverage_percent == 100:
            quality_score += 10
        if design_state.get("validation_errors"):
            quality_score -= len(design_state["validation_errors"]) * 5
        quality_score = max(50, min(100, quality_score))
        
    # 6. Fetch pending reviews count
    pending_reviews_count = 0
    if proj.current_phase == "REQUIREMENT" and proj.status == "AWAITING_APPROVAL":
        pending_reviews_count = 1
    elif proj.current_phase == "DESIGN" and proj.status == "AWAITING_APPROVAL":
        pending_reviews_count = 1
    elif proj.current_phase == "DEVELOPMENT" and proj.status == "AWAITING_APPROVAL":
        pending_reviews_count = 1
        
    return {
        "project": {
            "id": proj.id,
            "name": proj.name,
            "description": proj.description,
            "current_phase": proj.current_phase,
            "status": proj.status
        },
        "agent_state": {
            "messages": state_details["messages"],
            "memory": state_details["memory"],
            "document": state_details.get("document"),
            "gaps": state_details.get("gaps"),
            "phase": state_details["phase"],
            "missing_info": state_details["missing_info"],
            "validation_attempts": state_details["validation_attempts"],
            "active_stage": state_details.get("active_stage")
        },
        "design_agent_state": {
            "phase": design_state["phase"],
            "validation_attempts": design_state["validation_attempts"],
            "validation_errors": design_state["validation_errors"],
            "active_stage": design_state.get("active_stage"),
            "gaps": design_state.get("gaps")
        },
        "development_agent_state": {
            "phase": dev_state["phase"],
            "validation_attempts": dev_state["validation_attempts"],
            "validation_errors": dev_state["validation_errors"],
            "manifest": dev_state["manifest"]
        },
        "srs": srs_data,
        "sdd": sdd_data,
        "metrics": {
            "requirement_completeness_percent": req_completeness,
            "elicitation_completeness_percent": elicitation_completeness,
            "srs_completeness_percent": srs_completeness,
            "design_completeness_percent": design_completeness,
            "architecture_quality_score": quality_score,
            "api_count": api_count,
            "database_table_count": table_count,
            "diagram_count": diagram_count,
            "requirement_coverage_percent": coverage_percent,
            "pending_reviews_count": pending_reviews_count
        },
        "logs": [
            {
                "action": log.action,
                "details": log.details,
                "timestamp": log.timestamp
            } for log in activity_logs
        ]
    }

@app.get("/api/projects/{project_id}/history")
def get_version_history(project_id: str, db: Session = Depends(get_db)):
    req = project_service.get_requirements(db, project_id)
    if not req:
        return []
        
    versions = db.query(models.RequirementVersion).filter(models.RequirementVersion.requirement_id == req.id).order_by(models.RequirementVersion.version_num.desc()).all()
    
    result = []
    for v in versions:
        result.append({
            "version_num": v.version_num,
            "srs": json.loads(v.raw_srs),
            "reviewer_comments": v.reviewer_comments,
            "created_at": v.created_at
        })
    return result

@app.post("/api/projects/{project_id}/design/generate")
def generate_design(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
        
    try:
        result = design_service.start_design_generation(db, project_id)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=409, detail=str(ve))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Design Agent runtime error: {str(e)}")

@app.post("/api/projects/{project_id}/design/approve")
def approve_or_reject_design(project_id: str, review: schemas.HumanReviewSubmit, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
        
    design_doc, _ = design_service.get_latest_design_version(db, project_id)
    design_state = design_service.get_design_state_details(project_id, db)
    if not design_doc and (not design_state or not design_state.get("sdd")):
        raise HTTPException(status_code=400, detail="No design document generated yet for this project")
        
    try:
        result = design_service.resume_design_approval(
            db=db,
            project_id=project_id,
            status=review.status,
            comments=review.comments,
            reviewer_name=review.reviewer_name,
            stage=review.stage
        )
        return result
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Design Approval processing error: {str(e)}")

@app.get("/api/projects/{project_id}/design")
def get_current_design(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
        
    design_doc, latest_ver = design_service.get_latest_design_version(db, project_id)
    if not design_doc:
        return {"design_document": None, "latest_version": None}
        
    return {
        "design_document": {
            "id": design_doc.id,
            "project_id": design_doc.project_id,
            "approval_status": design_doc.approval_status,
            "created_at": design_doc.created_at
        },
        "latest_version": {
            "version_num": latest_ver.version_num,
            "sdd": json.loads(latest_ver.raw_sdd),
            "reviewer_comments": latest_ver.reviewer_comments,
            "created_at": latest_ver.created_at
        } if latest_ver else None
    }

@app.get("/api/projects/{project_id}/design/versions")
def get_design_version_history(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
        
    return design_service.get_design_history(db, project_id)

@app.get("/api/projects/{project_id}/requirements/download/pdf")
def download_requirements_pdf(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    srs_dict, ver_num = project_service.get_effective_srs_data(db, project_id)
    if not srs_dict:
        raise HTTPException(status_code=404, detail="No SRS or requirement data generated yet.")
    
    pdf_bytes = document_generator.generate_srs_pdf(
        project_name=proj.name,
        srs_data=srs_dict,
        version=ver_num,
        approval_status=proj.status
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=srs_{project_id}.pdf"}
    )

@app.get("/api/projects/{project_id}/requirements/download/docx")
def download_requirements_docx(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    srs_dict, ver_num = project_service.get_effective_srs_data(db, project_id)
    if not srs_dict:
        raise HTTPException(status_code=404, detail="No SRS or requirement data generated yet.")
    
    docx_bytes = document_generator.generate_srs_docx(
        project_name=proj.name,
        srs_data=srs_dict,
        version=ver_num,
        approval_status=proj.status
    )
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=srs_{project_id}.docx"}
    )

@app.get("/api/projects/{project_id}/requirements/download/markdown")
def download_requirements_markdown(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    srs_dict, ver_num = project_service.get_effective_srs_data(db, project_id)
    if not srs_dict:
        raise HTTPException(status_code=404, detail="No SRS or requirement data generated yet.")
    
    md_content = document_generator.generate_srs_markdown(
        project_name=proj.name,
        srs_data=srs_dict,
        version=ver_num,
        approval_status=proj.status
    )
    return Response(
        content=md_content,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=srs_{project_id}.md"}
    )

@app.get("/api/projects/{project_id}/requirements/download/json")
def download_requirements_json(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    srs_dict, ver_num = project_service.get_effective_srs_data(db, project_id)
    if not srs_dict:
        raise HTTPException(status_code=404, detail="No SRS or requirement data generated yet.")
    return Response(
        content=json.dumps(srs_dict, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=srs_{project_id}.json"}
    )

@app.get("/api/projects/{project_id}/design/download/pdf")
def download_design_pdf(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    sdd_dict, version_num, approval_status = design_service.get_effective_sdd_data(db, project_id)
    if not sdd_dict:
        raise HTTPException(status_code=404, detail="No Design Document generated yet")
    
    pdf_bytes = document_generator.generate_sdd_pdf(
        project_name=proj.name,
        sdd_data=sdd_dict,
        version=version_num,
        approval_status=approval_status
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=sdd_{project_id}.pdf"}
    )

@app.get("/api/projects/{project_id}/design/download/docx")
def download_design_docx(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    sdd_dict, version_num, approval_status = design_service.get_effective_sdd_data(db, project_id)
    if not sdd_dict:
        raise HTTPException(status_code=404, detail="No Design Document generated yet")
    
    docx_bytes = document_generator.generate_sdd_docx(
        project_name=proj.name,
        sdd_data=sdd_dict,
        version=version_num,
        approval_status=approval_status
    )
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=sdd_{project_id}.docx"}
    )

@app.get("/api/projects/{project_id}/design/download/markdown")
def download_design_markdown(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    sdd_dict, version_num, approval_status = design_service.get_effective_sdd_data(db, project_id)
    if not sdd_dict:
        raise HTTPException(status_code=404, detail="No Design Document generated yet")

    md_content = document_generator.generate_sdd_markdown(
        project_name=proj.name,
        sdd_data=sdd_dict,
        version=version_num,
        approval_status=approval_status
    )
    return Response(
        content=md_content,
        media_type="text/markdown",
        headers={"Content-Disposition": f"attachment; filename=sdd_{project_id}.md"}
    )

@app.get("/api/projects/{project_id}/design/download/json")
def download_design_json(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    sdd_dict, version_num, approval_status = design_service.get_effective_sdd_data(db, project_id)
    if not sdd_dict:
        raise HTTPException(status_code=404, detail="No Design Document generated yet")
    return Response(
        content=json.dumps(sdd_dict, indent=2),
        media_type="application/json",
        headers={"Content-Disposition": f"attachment; filename=sdd_{project_id}.json"}
    )

@app.post("/api/projects/{project_id}/design/review")
def review_design(project_id: str, review: schemas.HumanReviewSubmit, db: Session = Depends(get_db)):
    return approve_or_reject_design(project_id, review, db)


# --- DEVELOPMENT AGENT ROUTINGS ---

@app.post("/api/projects/{project_id}/development/start")
def start_code_development(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        res = development_service.start_development_generation(db, project_id)
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Development agent runtime error: {str(e)}")

@app.post("/api/projects/{project_id}/development/approve")
def submit_development_approval(project_id: str, review: schemas.DevelopmentReviewSubmit, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
        
    latest_dev = development_service.get_latest_development_version(db, project_id)
    if not latest_dev:
        raise HTTPException(status_code=400, detail="No code generated yet to approve.")
        
    try:
        res = development_service.resume_development_approval(
            db=db,
            project_id=project_id,
            status=review.status,
            comments=review.comments,
            reviewer_name=review.reviewer_name,
            rejected_modules=review.rejected_modules
        )
        return res
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Gated code review process error: {str(e)}")


@app.post("/api/projects/{project_id}/development/reject")
def reject_development_code(project_id: str, review: schemas.DevelopmentReviewSubmit, db: Session = Depends(get_db)):
    # Standard rejects maps status = REJECTED
    review.status = "REJECTED"
    return submit_development_approval(project_id, review, db)


@app.post("/api/projects/{project_id}/development/revise")
def revise_development_code(project_id: str, review: schemas.DevelopmentReviewSubmit, db: Session = Depends(get_db)):
    review.status = "REJECTED"
    return submit_development_approval(project_id, review, db)


@app.get("/api/projects/{project_id}/development/tasks")
def get_development_tasks_list(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"tasks": development_service.get_development_tasks(db, project_id)}


@app.get("/api/projects/{project_id}/development/agents")
def get_development_agents_statuses(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"agents": development_service.get_development_agents(db, project_id)}


@app.get("/api/projects/{project_id}/development/logs")
def get_development_execution_logs_list(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"logs": development_service.get_development_logs(db, project_id)}


@app.get("/api/projects/{project_id}/development/files")
def get_development_files_list(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return development_service.get_development_files(db, project_id)


@app.get("/api/projects/{project_id}/development/artifacts")
def get_development_artifacts_list(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"artifacts": development_service.get_development_artifacts(db, project_id)}


@app.get("/api/projects/{project_id}/development/tests")
def get_development_test_cases(project_id: str, type: Optional[str] = None, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    cases = development_service.get_test_cases(db, project_id, test_type=type)
    return {"cases": cases}


@app.get("/api/projects/{project_id}/development/tests/report")
def get_development_test_report(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    report = development_service.get_test_report(db, project_id)
    return report


@app.get("/api/projects/{project_id}/development/tests/download/pdf")
def download_development_test_report_pdf(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    try:
        pdf_bytes = development_service.generate_test_report_pdf_bytes(db, project_id)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=test_report_{project_id}.pdf"}
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"PDF generation error: {str(e)}")



@app.get("/api/projects/{project_id}/development")
def get_code_development_status(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
        
    dev_state = development_service.get_development_state(project_id, db)
    history = development_service.get_development_history(db, project_id)
    
    return {
        "state": dev_state,
        "history": history
    }

@app.get("/api/projects/{project_id}/development/download")
def download_development_zip(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
        
    latest_dev = development_service.get_latest_development_version(db, project_id)
    if not latest_dev or not latest_dev.artifact_zip_path:
        raise HTTPException(status_code=404, detail="No downloadable zip package compiled yet.")
        
    zip_path = latest_dev.artifact_zip_path
    if not os.path.exists(zip_path):
        raise HTTPException(status_code=404, detail=f"Zip archive file not found: {zip_path}")
        
    with open(zip_path, "rb") as f:
        zip_bytes = f.read()
        
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=project_code_{project_id}.zip"}
    )


@app.get("/api/projects/{project_id}/development/artifacts/download")
def download_development_artifact(project_id: str, type: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
        
    latest_dev = development_service.get_latest_development_version(db, project_id)
    if not latest_dev or not latest_dev.artifact_paths:
        raise HTTPException(status_code=404, detail="No artifacts compiled yet.")
        
    paths = json.loads(latest_dev.artifact_paths)
    file_path = paths.get(type)
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Artifact type '{type}' (file path '{file_path}') not found on server disk.")
        
    with open(file_path, "rb") as f:
        content = f.read()
        
    media_type = "application/octet-stream"
    if file_path.endswith(".zip"):
        media_type = "application/zip"
    elif file_path.endswith(".json"):
        media_type = "application/json"
    elif file_path.endswith(".sql") or file_path.endswith(".py"):
        media_type = "text/plain"
    elif file_path.endswith(".md"):
        media_type = "text/markdown"
        
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={os.path.basename(file_path)}"}
    )


@app.get("/api/projects/{project_id}/testing/payload")
def get_testing_agent_payload(project_id: str, db: Session = Depends(get_db)):
    proj = project_service.get_project(db, project_id)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    srs_data, srs_ver = project_service.get_effective_srs_data(db, project_id)
    sdd_data, sdd_ver, _ = design_service.get_effective_sdd_data(db, project_id)
    latest_dev = development_service.get_latest_development_version(db, project_id)

    raw_features = []
    if srs_data and srs_data.get("functional_requirements"):
        for r in srs_data.get("functional_requirements"):
            if isinstance(r, dict):
                raw_features.append(f"{r.get('name')}: {r.get('description', '')}")
            else:
                raw_features.append(str(r))
    if not raw_features:
        raw_features = [f"Full feature suite for {proj.name}"]

    file_paths = []
    if latest_dev and latest_dev.raw_manifest:
        try:
            manifest = json.loads(latest_dev.raw_manifest)
            raw_files = manifest.get("files", [])
            file_paths = [f.get("path") if isinstance(f, dict) else str(f) for f in raw_files]
        except Exception:
            pass
    if not file_paths:
        file_paths = ["app/main.py", "app/database.py", "frontend/index.html"]

    srs_dict = srs_data or {}
    sdd_dict = sdd_data or {}
    return {
        "project_id": project_id,
        "srs": {
            "title": srs_dict.get("project_name") or srs_dict.get("title") or proj.name,
            "version": f"{srs_ver}.0.0",
            "features": raw_features
        },
        "sdd": {
            "architecture": sdd_dict.get("high_level_architecture") or sdd_dict.get("architecture") or "Clean Architecture",
            "components": [
                m.get("name") if isinstance(m, dict) else str(m)
                for m in (sdd_dict.get("module_breakdown") or sdd_dict.get("components") or ["Core Engine"])
            ],
            "interfaces": [
                f"{ep.get('method', 'GET')} {ep.get('path', '/')}" if isinstance(ep, dict) else str(ep)
                for ep in (sdd_dict.get("api_endpoints") or sdd_dict.get("interfaces") or ["GET /health"])
            ]
        },
        "source_code": {
            "repository": f"github.com/enterprise/{proj.name.lower().replace(' ', '-')}",
            "language": "Python",
            "files": file_paths,
            "changes": {
                "changed_files": file_paths[:3] if len(file_paths) >= 3 else file_paths,
                "changed_functions": ["main", "service_handler"]
            }
        },
        "api_docs": {
            "base_url": "http://127.0.0.1:8000",
            "endpoints": [
                f"{ep.get('method', 'GET')} {ep.get('path', '/')}" if isinstance(ep, dict) else str(ep)
                for ep in sdd_dict.get("api_endpoints", [])
            ]
        } if sdd_dict.get("api_endpoints") else None,
        "database_schema": {
            "dialect": "PostgreSQL",
            "tables": [
                t.get("table_name") if isinstance(t, dict) else str(t)
                for t in sdd_dict.get("database_tables", [])
            ]
        } if sdd_dict.get("database_tables") else None,
        "environment": {
            "name": "staging-cluster"
        }
    }


TESTING_AGENT_URL = os.getenv("TESTING_AGENT_URL", "http://127.0.0.1:8085")


@app.post("/api/projects/{project_id}/testing/start")
def start_testing_flow(project_id: str, db: Session = Depends(get_db)):
    payload = get_testing_agent_payload(project_id, db)
    try:
        r = requests.post(f"{TESTING_AGENT_URL}/testing/start", json=payload, timeout=60)
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        data = r.json()
        project_service.log_activity(db, project_id, "TESTING_INTELLIGENCE_STARTED", f"Testing intelligence P1-P3 triggered. Validation: {data.get('validation_status')}")
        return data
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Testing Agent service error: {str(e)}")


@app.post("/api/projects/{project_id}/testing/execute")
def execute_testing_pipeline(project_id: str, body: Optional[dict] = None, db: Session = Depends(get_db)):
    payload = get_testing_agent_payload(project_id, db)
    if body:
        if "test_case_ids" in body:
            payload["test_case_ids"] = body["test_case_ids"]
        if "retry" in body:
            payload["retry"] = body["retry"]
    try:
        r = requests.post(f"{TESTING_AGENT_URL}/testing/execute", json=payload, timeout=300)
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        data = r.json()
        qg_status = data.get("quality_gate", {}).get("overall_status", "UNKNOWN")
        readiness = data.get("quality_gate", {}).get("release_readiness", "UNKNOWN")
        project_service.log_activity(
            db, project_id, "TESTING_EXECUTION_COMPLETED",
            f"Testing Agent P1-P8 executed. Quality Gate: {qg_status}, Readiness: {readiness}"
        )
        return data
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Testing Agent service error: {str(e)}")


@app.post("/api/projects/{project_id}/testing/retry")
def retry_testing_pipeline(project_id: str, body: Optional[dict] = None, db: Session = Depends(get_db)):
    payload = get_testing_agent_payload(project_id, db)
    payload["retry"] = True
    if body and "test_case_ids" in body:
        payload["test_case_ids"] = body["test_case_ids"]
    try:
        r = requests.post(f"{TESTING_AGENT_URL}/testing/retry", json=payload, timeout=300)
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        data = r.json()
        project_service.log_activity(
            db, project_id, "TESTING_RETRY_COMPLETED",
            f"Retried failed test cases. Executed {len(data.get('results', []))} tests."
        )
        return data
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Testing Agent service error: {str(e)}")


@app.get("/api/projects/{project_id}/testing/status")
def get_testing_agent_status(project_id: str):
    try:
        r = requests.get(f"{TESTING_AGENT_URL}/testing/status/{project_id}", timeout=15)
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        return r.json()
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Testing Agent service error: {str(e)}")


@app.post("/api/projects/{project_id}/testing/report/approve")
def approve_testing_report(project_id: str, body: dict, db: Session = Depends(get_db)):
    try:
        payload = dict(body)
        payload["project_id"] = project_id
        r = requests.post(f"{TESTING_AGENT_URL}/testing/report/approve", json=payload, timeout=30)
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        res = r.json()
        
        # Update SDLC project state to DEPLOYMENT / READY_FOR_DEPLOYMENT
        project_service.update_project_status(db, project_id, "DEPLOYMENT", "READY_FOR_DEPLOYMENT")
        project_service.log_activity(
            db, project_id, "TESTING_APPROVED",
            f"Testing phase approved by {body.get('approved_by', 'QA Lead')}. Project moved to DEPLOYMENT."
        )
        return res
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Testing Agent service error: {str(e)}")


@app.post("/api/projects/{project_id}/testing/report/reject")
def reject_testing_report(project_id: str, body: dict, db: Session = Depends(get_db)):
    try:
        payload = dict(body)
        payload["project_id"] = project_id
        r = requests.post(f"{TESTING_AGENT_URL}/testing/report/reject", json=payload, timeout=30)
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        res = r.json()
        
        # Update SDLC project state to DEVELOPMENT / DEVELOPMENT_PLANNING
        project_service.update_project_status(db, project_id, "DEVELOPMENT", "DEVELOPMENT_PLANNING")
        project_service.log_activity(
            db, project_id, "TESTING_REJECTED",
            f"Testing phase rejected by {body.get('approved_by', 'QA Lead')}. Reason: {body.get('comment', 'None')}"
        )
        return res
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Testing Agent service error: {str(e)}")


@app.get("/api/projects/{project_id}/testing/export/{fmt}")
@app.get("/api/projects/{project_id}/testing/download/{fmt}")
def export_testing_report(project_id: str, fmt: str, db: Session = Depends(get_db)):
    """Export the Testing Agent comprehensive report for a project in the requested format (pdf, docx, md, json, html, csv)."""
    fmt_lower = fmt.lower()
    if fmt_lower not in ["pdf", "docx", "md", "json", "html", "csv"]:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}. Must be pdf, docx, md, json, html, or csv.")

    media_types = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "md": "text/markdown; charset=utf-8",
        "json": "application/json",
        "html": "text/html; charset=utf-8",
        "csv": "text/csv; charset=utf-8",
    }

    # 1. Try to fetch stored report from Testing Agent
    try:
        r = requests.get(f"{TESTING_AGENT_URL}/testing/report/export/{project_id}?fmt={fmt_lower}", timeout=60)
        if r.status_code == 200:
            media_type = r.headers.get("content-type", media_types.get(fmt_lower, "application/octet-stream"))
            content_disposition = r.headers.get("content-disposition", f'attachment; filename="testing-report-{project_id}.{fmt_lower}"')
            return Response(content=r.content, media_type=media_type, headers={"Content-Disposition": content_disposition})
    except requests.exceptions.RequestException:
        pass

    # 2. If not stored or first run, export using real upstream SDLC project payload
    try:
        payload = get_testing_agent_payload(project_id, db)
        r = requests.post(f"{TESTING_AGENT_URL}/testing/report/export?fmt={fmt_lower}", json=payload, timeout=90)
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail=r.text)
        media_type = r.headers.get("content-type", media_types.get(fmt_lower, "application/octet-stream"))
        content_disposition = r.headers.get("content-disposition", f'attachment; filename="testing-report-{project_id}.{fmt_lower}"')
        return Response(content=r.content, media_type=media_type, headers={"Content-Disposition": content_disposition})
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Testing Agent export service error: {str(e)}")


@app.get("/health")
def health_check():
    return {"status": "ok"}

