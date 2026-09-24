"""
Database repository — all SQLite operations in one place.

The repository provides methods for duplicate checking, job storage,
Excel-sync tracking, and run audit logging.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from .models import JobRecord, SearchRun, init_database
from ..schemas import JobCandidate
from ..utils.normalization import compute_fingerprint, compute_description_hash
from ..utils.logger import get_logger

logger = get_logger("job_agent.db")


class JobRepository:
    """Facade over the SQLite job history database."""

    def __init__(self, database_url: str):
        self.engine, self._SessionFactory = init_database(database_url)

    def _session(self):
        return self._SessionFactory()

    # ═══════════════════════════════════════════════════
    # Duplicate checks
    # ═══════════════════════════════════════════════════
    def url_exists(self, url: str) -> bool:
        """Level 1: exact URL match."""
        session = self._session()
        try:
            return (
                session.query(JobRecord)
                .filter(JobRecord.job_url == url)
                .first()
                is not None
            )
        finally:
            session.close()

    def fingerprint_exists(
        self, company: str, title: str, location: str
    ) -> tuple[bool, Optional[int]]:
        """Level 3: normalized fingerprint match."""
        fp = compute_fingerprint(company, title, location)
        session = self._session()
        try:
            record = (
                session.query(JobRecord)
                .filter(JobRecord.fingerprint == fp)
                .first()
            )
            if record:
                return True, record.id
            return False, None
        finally:
            session.close()

    def find_similar(self, company: str, title: str) -> list[JobRecord]:
        """Fuzzy search for possible duplicates by company + title substring."""
        session = self._session()
        try:
            return (
                session.query(JobRecord)
                .filter(
                    JobRecord.company_name.ilike(f"%{company}%"),
                    JobRecord.job_title.ilike(f"%{title}%"),
                )
                .all()
            )
        finally:
            session.close()

    # ═══════════════════════════════════════════════════
    # Bulk lookups (cached per run for speed)
    # ═══════════════════════════════════════════════════
    def get_all_urls(self) -> set[str]:
        session = self._session()
        try:
            rows = session.query(JobRecord.job_url).all()
            return {r[0] for r in rows if r[0]}
        finally:
            session.close()

    def get_all_fingerprints(self) -> set[str]:
        session = self._session()
        try:
            rows = session.query(JobRecord.fingerprint).all()
            return {r[0] for r in rows if r[0]}
        finally:
            session.close()

    # ═══════════════════════════════════════════════════
    # Save operations
    # ═══════════════════════════════════════════════════
    def save_job(self, job: JobCandidate) -> JobRecord:
        """Insert a new job record into the database."""
        session = self._session()
        try:
            record = JobRecord(
                company_name=job.company_name,
                job_title=job.job_title,
                role=job.role or job.job_title,
                location=job.location,
                experience=job.experience,
                employment_type=job.employment_type,
                source=job.source,
                source_type=job.source_type,
                job_url=job.job_url,
                company_url=job.company_url,
                recruiter_name=job.recruiter_name,
                recruiter_contact=job.recruiter_contact,
                application_method=job.application_method,
                skills=json.dumps(job.skills),
                description=job.description,
                description_hash=(
                    compute_description_hash(job.description)
                    if job.description
                    else ""
                ),
                posting_date=job.posting_date or "",
                status=job.status,
                confidence_score=job.confidence_score,
                post_classification=job.post_classification or "",
                match_result=job.match_result or "",
                match_reason=job.match_reason or "",
                fingerprint=compute_fingerprint(
                    job.company_name, job.job_title, job.location
                ),
                duplicate_level=job.duplicate_level or "",
                review_reason=job.review_reason,
                added_to_excel=False,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            logger.info(
                f"[success]Saved[/] {job.company_name} — {job.job_title} (id={record.id})"
            )
            return record
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to save job: {e}")
            raise
        finally:
            session.close()

    def mark_added_to_excel(self, job_url: str):
        """Flag a job as successfully written to the Excel file."""
        session = self._session()
        try:
            record = (
                session.query(JobRecord)
                .filter(JobRecord.job_url == job_url)
                .first()
            )
            if record:
                record.added_to_excel = True
                record.added_to_excel_at = datetime.utcnow()
                session.commit()
        finally:
            session.close()

    # ═══════════════════════════════════════════════════
    # Review queue
    # ═══════════════════════════════════════════════════
    def get_review_jobs(self) -> list[JobRecord]:
        session = self._session()
        try:
            return (
                session.query(JobRecord)
                .filter(
                    JobRecord.match_result == "review",
                    JobRecord.reviewed == False,
                )
                .all()
            )
        finally:
            session.close()

    # ═══════════════════════════════════════════════════
    # Audit logging
    # ═══════════════════════════════════════════════════
    def save_run(self, report: dict) -> SearchRun:
        """Save a discovery run summary for auditing."""
        session = self._session()
        try:
            run = SearchRun(
                started_at=datetime.fromisoformat(
                    report.get("started_at", datetime.utcnow().isoformat())
                ),
                completed_at=datetime.fromisoformat(
                    report.get("completed_at", datetime.utcnow().isoformat())
                ),
                total_raw=report.get("total_raw", 0),
                total_extracted=report.get("total_extracted", 0),
                total_matched=report.get("total_matched", 0),
                total_duplicates=report.get("total_duplicates", 0),
                total_rejected=report.get("total_rejected", 0),
                total_review=report.get("total_review", 0),
                total_added=report.get("total_added", 0),
                errors=json.dumps(report.get("errors", [])),
                report_json=json.dumps(report),
            )
            session.add(run)
            session.commit()
            return run
        finally:
            session.close()
