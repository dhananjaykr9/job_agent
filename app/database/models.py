"""
SQLAlchemy models for the job history database.

SQLite is used as the persistent store so the agent remembers
everything it has ever seen — preventing re-processing and
enabling duplicate detection even if the Excel file is modified.
"""
from datetime import datetime

from sqlalchemy import (
    Column,
    String,
    Float,
    Integer,
    DateTime,
    Text,
    Boolean,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


class JobRecord(Base):
    """Every job the agent has ever discovered, regardless of outcome."""

    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # ── Core identity ──────────────────────────────────
    company_name = Column(String(255), index=True, default="")
    job_title = Column(String(255), index=True, default="")
    role = Column(String(255), default="")
    location = Column(String(255), index=True, default="")
    experience = Column(String(100), default="")
    employment_type = Column(String(100), default="")

    # ── Source tracing ─────────────────────────────────
    source = Column(String(100), default="")
    source_type = Column(String(100), default="")
    job_url = Column(String(1024), unique=True, index=True, default="")
    company_url = Column(String(1024), default="")

    # ── Contact ────────────────────────────────────────
    recruiter_name = Column(String(255), default="")
    recruiter_contact = Column(String(255), default="")
    application_method = Column(String(255), default="")

    # ── Content ────────────────────────────────────────
    skills = Column(Text, default="")  # JSON-encoded list
    description = Column(Text, default="")
    description_hash = Column(String(64), index=True, default="")

    # ── Dates & status ─────────────────────────────────
    posting_date = Column(String(50), default="")
    status = Column(String(50), default="active")
    confidence_score = Column(Float, default=0.0)
    post_classification = Column(String(100), default="")

    # ── Matching outcome ───────────────────────────────
    match_result = Column(String(50), default="")  # match | reject | review
    match_reason = Column(Text, default="")

    # ── Deduplication ──────────────────────────────────
    fingerprint = Column(String(255), index=True, default="")
    duplicate_of = Column(Integer, nullable=True)
    duplicate_level = Column(String(50), default="")

    # ── Lifecycle tracking ─────────────────────────────
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    added_to_excel = Column(Boolean, default=False)
    added_to_excel_at = Column(DateTime, nullable=True)

    # ── Human review ───────────────────────────────────
    review_reason = Column(Text, nullable=True)
    reviewed = Column(Boolean, default=False)


class SearchRun(Base):
    """Audit log of each discovery run for debugging."""

    __tablename__ = "search_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    total_raw = Column(Integer, default=0)
    total_extracted = Column(Integer, default=0)
    total_matched = Column(Integer, default=0)
    total_duplicates = Column(Integer, default=0)
    total_rejected = Column(Integer, default=0)
    total_review = Column(Integer, default=0)
    total_added = Column(Integer, default=0)
    errors = Column(Text, nullable=True)
    report_json = Column(Text, nullable=True)


def init_database(database_url: str) -> tuple:
    """
    Initialize the database engine and session factory.

    Returns:
        (engine, SessionFactory) tuple.
    """
    engine = create_engine(database_url, echo=False)
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine)
    return engine, SessionFactory
