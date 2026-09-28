"""
Pydantic schemas for the entire job discovery pipeline.

Every source adapter, agent, and engine operates on these standard models
so downstream code never needs to care where a job came from.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════
# Enums
# ═══════════════════════════════════════════════════════
class SourceType(str, Enum):
    LINKEDIN_JOB = "linkedin_job"
    LINKEDIN_POST = "linkedin_post"
    COMPANY_CAREER = "company_career"
    NAUKRI = "naukri"
    INDEED = "indeed"
    WELLFOUND = "wellfound"
    WEB_SEARCH = "web_search"


class PostClassification(str, Enum):
    GENUINE_JOB = "genuine_job"
    REFERRAL = "referral"
    WALK_IN = "walk_in"
    CAMPUS_HIRING = "campus_hiring"
    RECRUITER_POST = "recruiter_post"
    GENERAL_DISCUSSION = "general_discussion"
    EXPIRED = "expired"
    UNCLEAR = "unclear"


class MatchResult(str, Enum):
    MATCH = "match"
    REJECT = "reject"
    REVIEW = "review"


class DuplicateLevel(str, Enum):
    EXACT_URL = "exact_url"
    JOB_ID = "job_id"
    FINGERPRINT = "fingerprint"
    UNIQUE = "unique"


# ═══════════════════════════════════════════════════════
# Raw discovery result (from any source adapter)
# ═══════════════════════════════════════════════════════
class RawJobResult(BaseModel):
    """A single raw result returned by a source adapter before extraction."""

    source: str = ""
    source_type: SourceType = SourceType.WEB_SEARCH
    url: str = ""
    raw_content: str = ""
    title: Optional[str] = None
    company: Optional[str] = None
    location: Optional[str] = None
    experience: Optional[str] = None
    snippet: Optional[str] = None
    discovered_at: datetime = Field(default_factory=datetime.now)


# ═══════════════════════════════════════════════════════
# Structured job candidate (after LLM extraction)
# ═══════════════════════════════════════════════════════
class JobCandidate(BaseModel):
    """
    The universal job record used throughout the pipeline.

    Every source adapter converts its raw output into this schema.
    The matching engine, dedup engine, and Excel writer all consume it.
    """

    # Core identity
    company_name: str = ""
    job_title: str = ""
    role: str = ""
    location: str = ""
    experience: str = ""
    employment_type: str = ""

    # Dates
    posting_date: Optional[str] = None
    discovered_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    # Source tracing
    source: str = ""
    source_type: str = ""
    job_url: str = ""
    company_url: str = ""

    # Contact
    recruiter_name: str = ""
    recruiter_contact: str = ""
    application_method: str = ""

    # Content
    skills: list[str] = Field(default_factory=list)
    description: str = ""

    # Status & scoring
    status: str = "active"
    confidence_score: float = 0.0

    # Pipeline metadata (set by matching / dedup / classification)
    match_result: Optional[str] = None
    match_reason: Optional[str] = None
    duplicate_of: Optional[str] = None
    duplicate_level: Optional[str] = None
    post_classification: Optional[str] = None
    review_reason: Optional[str] = None


# ═══════════════════════════════════════════════════════
# LLM output schemas
# ═══════════════════════════════════════════════════════
class ExtractionResult(BaseModel):
    """Structured output expected from the LLM extraction agent."""

    company_name: str = ""
    job_title: str = ""
    location: str = ""
    experience: str = ""
    skills: list[str] = Field(default_factory=list)
    employment_type: str = ""
    posting_date: str = ""
    recruiter_name: str = ""
    recruiter_contact: str = ""
    application_method: str = ""
    description: str = ""
    company_url: str = ""
    status: str = "active"
    confidence: float = 0.0


class ClassificationResult(BaseModel):
    """Structured output from the LinkedIn post classifier."""

    classification: str = "unclear"
    is_hiring: bool = False
    confidence: float = 0.0
    reasoning: str = ""


# ═══════════════════════════════════════════════════════
# Matching details
# ═══════════════════════════════════════════════════════
class MatchDetails(BaseModel):
    """Result of the rule-based + AI matching engine."""

    result: MatchResult = MatchResult.REVIEW
    reasons: list[str] = Field(default_factory=list)
    score: float = 0.0


# ═══════════════════════════════════════════════════════
# Run report
# ═══════════════════════════════════════════════════════
class RunReport(BaseModel):
    """Summary produced at the end of each discovery run."""

    started_at: str = ""
    completed_at: str = ""
    sources_searched: dict[str, int] = Field(default_factory=dict)
    total_raw: int = 0
    total_extracted: int = 0
    total_matched: int = 0
    total_duplicates: int = 0
    total_rejected: int = 0
    total_review: int = 0
    total_added: int = 0
    errors: list[str] = Field(default_factory=list)
