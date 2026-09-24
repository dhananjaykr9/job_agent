"""
LangGraph State definition.

This TypedDict defines the complete state that flows through
every node in the job discovery graph.
"""
from __future__ import annotations

from typing import TypedDict, Annotated
from operator import add

from ..schemas import RawJobResult, JobCandidate, RunReport


class JobSearchState(TypedDict, total=False):
    """
    State carried through the LangGraph workflow.

    Each node reads what it needs and writes its outputs.
    Using Annotated[list, add] for list fields so that parallel
    source nodes can safely append results.
    """

    # ── Configuration (set once at start) ──────────────
    search_queries: list[str]
    linkedin_keywords: list[str]
    target_companies: list[dict]
    company_discovery_queries: list[str]
    walkin_queries: list[str]
    excel_path: str

    # ── Discovery results (appended by source nodes) ───
    raw_results: Annotated[list[RawJobResult], add]

    # ── Pipeline outputs ───────────────────────────────
    extracted_jobs: list[JobCandidate]
    validated_jobs: list[JobCandidate]
    invalid_jobs: list[JobCandidate]
    matched_jobs: list[JobCandidate]
    rejected_jobs: list[JobCandidate]
    review_jobs: list[JobCandidate]
    unique_jobs: list[JobCandidate]
    duplicate_jobs: list[JobCandidate]

    # ── Final output ───────────────────────────────────
    jobs_to_insert: list[JobCandidate]
    jobs_written: int

    # ── Excel state ────────────────────────────────────
    excel_headers: list[str]
    excel_existing_urls: set[str]

    # ── Reporting ──────────────────────────────────────
    report: dict
    errors: Annotated[list[str], add]
