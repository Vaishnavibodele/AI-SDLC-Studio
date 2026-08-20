import datetime
import uuid
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text, Float
from sqlalchemy.orm import relationship
from .database import Base

def generate_uuid():
    return str(uuid.uuid4())

class Project(Base):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    current_phase = Column(String(50), default="REQUIREMENT")  # REQUIREMENT, DESIGN, DEVELOPMENT
    status = Column(String(50), default="IN_PROGRESS")  # IN_PROGRESS, AWAITING_APPROVAL, APPROVED, REJECTED
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    requirements = relationship("Requirement", back_populates="project", cascade="all, delete-orphan")
    designs = relationship("DesignDocument", back_populates="project", cascade="all, delete-orphan")
    reviews = relationship("HumanReview", back_populates="project", cascade="all, delete-orphan")
    activity_logs = relationship("ActivityLog", back_populates="project", cascade="all, delete-orphan")


class Requirement(Base):
    __tablename__ = "requirements"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    approval_status = Column(String(50), default="PENDING")  # PENDING, APPROVED, REJECTED
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    project = relationship("Project", back_populates="requirements")
    versions = relationship("RequirementVersion", back_populates="requirement", cascade="all, delete-orphan")


class RequirementVersion(Base):
    __tablename__ = "requirement_versions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    requirement_id = Column(String(36), ForeignKey("requirements.id"), nullable=False)
    version_num = Column(Integer, default=1)
    raw_srs = Column(Text, nullable=False)  # Stored as JSON string
    reviewer_comments = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    requirement = relationship("Requirement", back_populates="versions")


class HumanReview(Base):
    __tablename__ = "human_reviews"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    phase = Column(String(50), nullable=False)  # REQUIREMENT, DESIGN
    stage = Column(String(50), nullable=True)  # EXTRACTION, GAP_DETECTION, VALIDATION, FINALIZATION, DESIGN
    status = Column(String(50), nullable=False)  # APPROVED, REJECTED
    comments = Column(Text, nullable=True)
    reviewer_name = Column(String(100), default="Human Administrator")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    project = relationship("Project", back_populates="reviews")


class ActivityLog(Base):
    __tablename__ = "activity_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    action = Column(String(255), nullable=False)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    project = relationship("Project", back_populates="activity_logs")


class DesignDocument(Base):
    __tablename__ = "design_documents"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    requirement_version_id = Column(String(36), ForeignKey("requirement_versions.id"), nullable=False)
    approval_status = Column(String(50), default="PENDING")  # PENDING, APPROVED, REJECTED
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    project = relationship("Project", back_populates="designs")
    versions = relationship("DesignVersion", back_populates="design_document", cascade="all, delete-orphan")


class DesignVersion(Base):
    __tablename__ = "design_versions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    design_document_id = Column(String(36), ForeignKey("design_documents.id"), nullable=False)
    version_num = Column(Integer, default=1)
    raw_sdd = Column(Text, nullable=False)  # Stored as JSON string
    reviewer_comments = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    design_document = relationship("DesignDocument", back_populates="versions")


class DevelopmentVersion(Base):
    __tablename__ = "development_versions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    design_version_id = Column(String(36), ForeignKey("design_versions.id"), nullable=True)
    version_num = Column(Integer, default=1)
    raw_manifest = Column(Text, nullable=False)  # Stored as JSON string (manifest + file metadata)
    artifact_zip_path = Column(String(255), nullable=True)
    artifact_paths = Column(Text, nullable=True)  # JSON string mapping key -> path
    approval_status = Column(String(50), default="PENDING")  # PENDING, APPROVED, REJECTED
    parent_version_id = Column(String(36), ForeignKey("development_versions.id"), nullable=True)
    changed_files = Column(Text, nullable=True)  # JSON string array
    reason_for_revision = Column(Text, nullable=True)
    review_comments = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    project = relationship("Project")
    design_version = relationship("DesignVersion")
    parent_version = relationship("DevelopmentVersion", remote_side=[id])


class DevelopmentReview(Base):
    __tablename__ = "development_reviews"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    version_id = Column(String(36), nullable=True)  # Links to DevelopmentVersion
    status = Column(String(50), nullable=False)  # APPROVED, REJECTED
    comments = Column(Text, nullable=True)
    reviewer_name = Column(String(100), default="Human Administrator")
    rejected_modules = Column(Text, nullable=True)  # JSON list of rejected modules
    quality_score = Column(Float, nullable=True)
    security_score = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    project = relationship("Project")


class DevelopmentLog(Base):
    __tablename__ = "development_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    action = Column(String(255), nullable=False)
    details = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    project = relationship("Project")


class DevelopmentExecutionLog(Base):
    __tablename__ = "development_execution_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    version_id = Column(String(36), nullable=True)
    agent_name = Column(String(100), nullable=True)
    stage = Column(String(100), nullable=True)
    node_name = Column(String(100), nullable=False)
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    duration = Column(Float, nullable=True)  # In seconds
    llm_provider = Column(String(50), nullable=True)
    prompt_tokens = Column(Integer, default=0)
    completion_tokens = Column(Integer, default=0)
    retry_count = Column(Integer, default=0)
    status = Column(String(50), default="RUNNING")  # RUNNING, SUCCESS, FAILED
    error_message = Column(Text, nullable=True)
    task_id = Column(String(100), nullable=True)
    files_generated = Column(Text, nullable=True)

    # Relationships
    project = relationship("Project")


class DevelopmentTask(Base):
    __tablename__ = "development_tasks"

    task_id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    version_id = Column(String(36), ForeignKey("development_versions.id"), nullable=True)
    module = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    owner_agent = Column(String(100), nullable=False)
    dependencies = Column(Text, nullable=True)  # JSON string array
    priority = Column(Integer, default=3)
    status = Column(String(50), default="PENDING")  # PENDING, RUNNING, COMPLETED, FAILED, REVISION_REQUIRED
    requirement_id = Column(String(100), nullable=True)
    design_section_id = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    project = relationship("Project")
    version = relationship("DevelopmentVersion")


class DevelopmentAgentOutput(Base):
    __tablename__ = "development_agent_outputs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    version_id = Column(String(36), ForeignKey("development_versions.id"), nullable=True)
    agent_name = Column(String(100), nullable=False)
    output_payload = Column(Text, nullable=False)  # JSON string containing file names and source contents
    status = Column(String(50), default="SUCCESS")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    project = relationship("Project")
    version = relationship("DevelopmentVersion")


class DevelopmentArtifact(Base):
    __tablename__ = "development_artifacts"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    version_id = Column(String(36), ForeignKey("development_versions.id"), nullable=True)
    artifact_type = Column(String(100), nullable=False)  # e.g., source_zip, database_scripts, api_docs, project_report, change_log
    file_path = Column(String(255), nullable=False)
    checksum = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # Relationships
    project = relationship("Project")
    version = relationship("DevelopmentVersion")


class Epic(Base):
    __tablename__ = "epics"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    epic_id = Column(String(50), nullable=False)  # e.g. EPIC-001
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="proposed")
    source_type = Column(String(50), nullable=True)
    source_reference = Column(String(255), nullable=True)
    source_text = Column(Text, nullable=True)
    confidence = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    project = relationship("Project")


class Feature(Base):
    __tablename__ = "features"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    epic_id = Column(String(50), nullable=True)  # parent epic ID
    feature_id = Column(String(50), nullable=False)  # e.g. FEAT-001
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="proposed")
    source_type = Column(String(50), nullable=True)
    source_reference = Column(String(255), nullable=True)
    source_text = Column(Text, nullable=True)
    confidence = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    project = relationship("Project")


class UserStory(Base):
    __tablename__ = "user_stories"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    feature_id = Column(String(50), nullable=True)  # parent feature ID
    story_id = Column(String(50), nullable=False)  # e.g. US-001
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    linked_requirement_ids = Column(Text, nullable=True)  # JSON list
    status = Column(String(50), default="proposed")
    source_type = Column(String(50), nullable=True)
    source_reference = Column(String(255), nullable=True)
    source_text = Column(Text, nullable=True)
    confidence = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    project = relationship("Project")


class AcceptanceCriterion(Base):
    __tablename__ = "acceptance_criteria"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    story_id = Column(String(50), nullable=True)  # parent story ID
    ac_id = Column(String(50), nullable=False)  # e.g. AC-001
    statement = Column(Text, nullable=False)
    status = Column(String(50), default="proposed")
    source_type = Column(String(50), nullable=True)
    source_reference = Column(String(255), nullable=True)
    source_text = Column(Text, nullable=True)
    confidence = Column(Float, default=1.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    project = relationship("Project")


class ProjectAgentState(Base):
    __tablename__ = "project_agent_states"

    project_id = Column(String(36), ForeignKey("projects.id"), primary_key=True)
    current_state = Column(String(100), default="draft")
    document = Column(Text, nullable=True)  # JSON ProjectDocument
    messages = Column(Text, nullable=True)  # JSON list of messages
    memory = Column(Text, nullable=True)  # JSON RequirementMemory
    missing_info = Column(Text, nullable=True)  # JSON list of strings
    validation_attempts = Column(Integer, default=0)
    last_reviewer_comments = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    project = relationship("Project")


class VersionSnapshot(Base):
    __tablename__ = "version_snapshots"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    version_num = Column(Integer, default=1)
    document = Column(Text, nullable=False)  # JSON ProjectDocument
    reviewer_comments = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    project = relationship("Project")


