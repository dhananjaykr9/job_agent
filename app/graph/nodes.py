"""
LangGraph Node Functions.

Each function is a node in the job discovery graph.
Nodes read from state, do their work, and return state updates.

Error isolation: if any source node fails, the others continue.
"""
from __future__ import annotations

from datetime import datetime

from .state import JobSearchState
from ..config.settings import get_settings, get_preferences
from ..sources.web_search import WebSearchSource
from ..sources.linkedin_posts import LinkedInPostsSource
from ..sources.company_careers import CompanyCareersSource
from ..sources.direct_job_boards import DirectJobBoardSource
from ..agents.extraction import ExtractionAgent
from ..agents.classification import ClassificationAgent
from ..agents.validation import ValidationAgent
from ..matching.engine import MatchingEngine
from ..dedup.engine import DeduplicationEngine
from ..database.repository import JobRepository
from ..excel.reader import ExcelReader
from ..excel.mapper import ExcelMapper
from ..excel.writer import ExcelWriter
from ..excel.google_sheets import fetch_live_google_sheet, append_to_google_sheet_webhook
from ..schemas import RawJobResult, SourceType
from ..utils.logger import get_logger

logger = get_logger("job_agent.graph")


# ═══════════════════════════════════════════════════════
# Node: Load Configuration
# ═══════════════════════════════════════════════════════
def load_config(state: JobSearchState) -> dict:
    """Initialize configuration and load Excel state."""
    logger.info("━" * 60)
    logger.info("[bold]🚀 Job Discovery Agent — Starting Run[/]")
    logger.info("━" * 60)

    settings = get_settings()
    prefs = get_preferences()

    # Sync latest data from live Google Sheet if configured
    if settings.google_sheet_url:
        fetch_live_google_sheet(settings.google_sheet_url, settings.excel_file_path)

    # Read existing Excel to check for already-tracked jobs
    excel_headers = []
    excel_urls: set[str] = set()

    reader = ExcelReader(settings.excel_file_path)
    if reader.load():
        excel_headers = reader.headers
        excel_urls = reader.get_existing_urls()
        logger.info(
            f"Excel loaded: {reader.row_count} existing rows, "
            f"{len(excel_urls)} tracked URLs"
        )
        reader.close()

    return {
        "search_queries": prefs.search_queries,
        "linkedin_keywords": prefs.linkedin_keywords,
        "target_companies": prefs.target_companies,
        "company_discovery_queries": prefs.company_discovery_queries,
        "walkin_queries": prefs.walkin_queries,
        "excel_path": settings.excel_file_path,
        "excel_headers": excel_headers,
        "excel_existing_urls": excel_urls,
        "raw_results": [],
        "errors": [],
    }


# ═══════════════════════════════════════════════════════
# Node: Web Search Discovery
# ═══════════════════════════════════════════════════════
def search_web(state: JobSearchState) -> dict:
    """Discover jobs through DuckDuckGo search (free, unlimited) — includes walk-in drives."""
    try:
        source = WebSearchSource()
        # Combine regular search queries + walk-in queries for broad coverage
        all_queries = list(state.get("search_queries", []))
        all_queries.extend(state.get("walkin_queries", []))
        results = source._safe_search(all_queries)
        return {"raw_results": results}
    except Exception as e:
        logger.error(f"Web search node failed: {e}")
        return {"raw_results": [], "errors": [f"Web search error: {e}"]}


# ═══════════════════════════════════════════════════════
# Node: LinkedIn Posts Discovery
# ═══════════════════════════════════════════════════════
def search_linkedin_posts(state: JobSearchState) -> dict:
    """Discover jobs from LinkedIn hiring posts via DuckDuckGo (free)."""
    try:
        source = LinkedInPostsSource()
        results = source._safe_search(state.get("linkedin_keywords", []))
        return {"raw_results": results}
    except Exception as e:
        logger.error(f"LinkedIn posts node failed: {e}")
        return {"raw_results": [], "errors": [f"LinkedIn posts error: {e}"]}


# ═══════════════════════════════════════════════════════
# Node: Company Career Pages Discovery
# ═══════════════════════════════════════════════════════
def search_company_careers(state: JobSearchState) -> dict:
    """Discover jobs from company career pages + dynamic company discovery via DuckDuckGo."""
    try:
        source = CompanyCareersSource()
        results = source._safe_search(
            state.get("search_queries", [])[:5],
            target_companies=state.get("target_companies", []),
            discovery_queries=state.get("company_discovery_queries", []),
            walkin_queries=state.get("walkin_queries", []),
        )
        return {"raw_results": results}
    except Exception as e:
        logger.error(f"Career pages node failed: {e}")
        return {"raw_results": [], "errors": [f"Career pages error: {e}"]}


# ═══════════════════════════════════════════════════════
# Node: Direct Job Board Scraping (Naukri, Shine, Freshersworld, LinkedIn)
# ═══════════════════════════════════════════════════════
def search_direct_boards(state: JobSearchState) -> dict:
    """Scrape Naukri walk-ins, Shine, Freshersworld & LinkedIn Jobs directly."""
    try:
        source = DirectJobBoardSource()
        results = source._safe_search([])
        return {"raw_results": results}
    except Exception as e:
        logger.error(f"Direct job boards node failed: {e}")
        return {"raw_results": [], "errors": [f"Direct boards error: {e}"]}



# ═══════════════════════════════════════════════════════
# Node: Extract Job Data (LLM)
# ═══════════════════════════════════════════════════════
def extract_jobs(state: JobSearchState) -> dict:
    """Use Gemini to extract structured job data from raw results."""
    raw_results = state.get("raw_results", [])
    if not raw_results:
        logger.warning("No raw results to extract.")
        return {"extracted_jobs": []}

    logger.info(f"Processing [bold]{len(raw_results)}[/] raw results...")

    settings = get_settings()

    # Pre-filter: only keep results that have job-related keywords to avoid noise
    job_kws = ["engineer", "developer", "data", "python", "sql", "ai", "ml", "fresher", "walk in", "walkin", "intern", "hiring", "openings"]
    promising_results = [
        r for r in raw_results
        if any(kw in f"{r.title or ''} {r.snippet or ''} {r.url}".lower() for kw in job_kws)
    ]
    logger.info(f"Filtered to [bold]{len(promising_results)}[/] high-relevance candidates")

    extractor = ExtractionAgent(settings.gemini_api_key, settings.gemini_model)
    candidates = extractor.extract_batch(promising_results or raw_results[:30])

    return {"extracted_jobs": candidates}


# ═══════════════════════════════════════════════════════
# Node: Validate Data
# ═══════════════════════════════════════════════════════
def validate_jobs(state: JobSearchState) -> dict:
    """Validate extracted jobs for completeness and quality."""
    extracted = state.get("extracted_jobs", [])
    if not extracted:
        return {"validated_jobs": [], "invalid_jobs": []}

    validator = ValidationAgent()
    valid, invalid = validator.validate_batch(extracted)

    return {"validated_jobs": valid, "invalid_jobs": invalid}


# ═══════════════════════════════════════════════════════
# Node: Apply Matching Criteria
# ═══════════════════════════════════════════════════════
def match_jobs(state: JobSearchState) -> dict:
    """Apply rule-based + AI matching criteria."""
    validated = state.get("validated_jobs", [])
    if not validated:
        return {"matched_jobs": [], "rejected_jobs": [], "review_jobs": []}

    settings = get_settings()
    prefs = get_preferences()
    engine = MatchingEngine(prefs, settings.gemini_api_key, settings.gemini_model)
    results = engine.match_batch(validated)

    return {
        "matched_jobs": results["matched"],
        "rejected_jobs": results["rejected"],
        "review_jobs": results["review"],
    }


# ═══════════════════════════════════════════════════════
# Node: Deduplicate
# ═══════════════════════════════════════════════════════
def deduplicate_jobs(state: JobSearchState) -> dict:
    """Check for duplicates against DB and Excel."""
    matched = state.get("matched_jobs", [])
    if not matched:
        return {"unique_jobs": [], "duplicate_jobs": [], "jobs_to_insert": []}

    settings = get_settings()
    repo = JobRepository(settings.database_url)
    engine = DeduplicationEngine(repo)

    # Also check against existing Excel URLs
    excel_urls = state.get("excel_existing_urls", set())
    pre_filtered = []
    excel_dupes = []
    for job in matched:
        if job.job_url in excel_urls:
            job.duplicate_level = "excel_existing"
            job.match_result = "reject"
            job.match_reason = "Already in Excel"
            excel_dupes.append(job)
        else:
            pre_filtered.append(job)

    unique, db_dupes = engine.deduplicate_batch(pre_filtered)
    all_dupes = excel_dupes + db_dupes

    # Confidence gate — split into auto-add vs review
    prefs = get_preferences()
    auto_add = []
    for job in unique:
        if job.confidence_score >= prefs.auto_add_threshold:
            auto_add.append(job)
        elif job.confidence_score >= prefs.review_threshold:
            job.review_reason = f"Confidence {job.confidence_score:.0%} below auto-add threshold"
            state.get("review_jobs", []).append(job)
        else:
            job.match_result = "reject"
            job.match_reason = f"Low confidence: {job.confidence_score:.0%}"

    # If no jobs hit the strict auto_add_threshold, promote top verified matches (>=0.50)
    if not auto_add and unique:
        top_candidates = [j for j in unique if j.confidence_score >= 0.50]
        if top_candidates:
            logger.info(f"Promoting {len(top_candidates)} verified matches to auto-add")
            auto_add = top_candidates[:20]

    return {
        "unique_jobs": unique,
        "duplicate_jobs": all_dupes,
        "jobs_to_insert": auto_add,
    }


# ═══════════════════════════════════════════════════════
# Node: Write to Excel
# ═══════════════════════════════════════════════════════
def write_to_excel(state: JobSearchState) -> dict:
    """Write confirmed jobs to the Excel tracker."""
    jobs = state.get("jobs_to_insert", [])
    if not jobs:
        logger.info("No new jobs to add to Excel.")
        return {"jobs_written": 0}

    settings = get_settings()
    prefs = get_preferences()

    mapper = ExcelMapper(
        excel_headers=state.get("excel_headers", []),
        custom_mapping=prefs.excel_column_mapping,
        user_owned_columns=prefs.user_owned_columns,
    )
    writer = ExcelWriter(settings.excel_file_path, mapper)
    written = writer.write_jobs(jobs)

    # Sync directly to live Google Sheet via webhook if configured
    if settings.google_sheet_webhook_url:
        append_to_google_sheet_webhook(
            webhook_url=settings.google_sheet_webhook_url,
            jobs=jobs,
            mapper=mapper,
            headers=state.get("excel_headers", []),
        )

    # Save to database and mark as added
    repo = JobRepository(settings.database_url)
    for job in jobs:
        try:
            repo.save_job(job)
            repo.mark_added_to_excel(job.job_url)
        except Exception as e:
            logger.warning(f"DB save failed for {job.job_url}: {e}")

    return {"jobs_written": written}


# ═══════════════════════════════════════════════════════
# Node: Save Review Jobs to DB & Google Sheet
# ═══════════════════════════════════════════════════════
def save_review_jobs(state: JobSearchState) -> dict:
    """Save jobs that need human review to the database and Pending Review sheet."""
    review_jobs = state.get("review_jobs", [])
    if not review_jobs:
        return {}

    settings = get_settings()
    prefs = get_preferences()
    repo = JobRepository(settings.database_url)

    for job in review_jobs:
        job.match_result = "review"
        try:
            repo.save_job(job)
        except Exception as e:
            logger.warning(f"Failed to save review job: {e}")

    # Write borderline jobs to "Pending Review" tab in Google Sheet if configured
    if settings.google_sheet_webhook_url:
        mapper = ExcelMapper(
            excel_headers=state.get("excel_headers", []),
            custom_mapping=prefs.excel_column_mapping,
            user_owned_columns=prefs.user_owned_columns,
        )
        append_to_google_sheet_webhook(
            webhook_url=settings.google_sheet_webhook_url,
            jobs=review_jobs,
            mapper=mapper,
            headers=state.get("excel_headers", []),
            sheet_name="Pending Review",
        )

    logger.info(f"Saved [warning]{len(review_jobs)} jobs[/] for human review")
    return {}


# ═══════════════════════════════════════════════════════
# Node: Generate Report
# ═══════════════════════════════════════════════════════
def generate_report(state: JobSearchState) -> dict:
    """Generate a summary report of the discovery run."""
    report = {
        "completed_at": datetime.now().isoformat(),
        "total_raw": len(state.get("raw_results", [])),
        "total_extracted": len(state.get("extracted_jobs", [])),
        "total_validated": len(state.get("validated_jobs", [])),
        "total_matched": len(state.get("matched_jobs", [])),
        "total_duplicates": len(state.get("duplicate_jobs", [])),
        "total_rejected": len(state.get("rejected_jobs", [])),
        "total_review": len(state.get("review_jobs", [])),
        "total_added": state.get("jobs_written", 0),
        "errors": state.get("errors", []),
    }

    # Save run to DB
    try:
        settings = get_settings()
        repo = JobRepository(settings.database_url)
        repo.save_run(report)
    except Exception:
        pass

    # Pretty print report
    logger.info("━" * 60)
    logger.info("[bold]📊 Discovery Run Report[/]")
    logger.info("━" * 60)
    logger.info(f"  Raw results:     {report['total_raw']}")
    logger.info(f"  Extracted:       {report['total_extracted']}")
    logger.info(f"  Validated:       {report['total_validated']}")
    logger.info(f"  Matched:         {report['total_matched']}")
    logger.info(f"  Duplicates:      {report['total_duplicates']}")
    logger.info(f"  Rejected:        {report['total_rejected']}")
    logger.info(f"  Review needed:   {report['total_review']}")
    logger.info(f"  [success]Added to Excel: {report['total_added']}[/]")
    if report["errors"]:
        logger.warning(f"  Errors: {len(report['errors'])}")
        for err in report["errors"]:
            logger.warning(f"    → {err}")
    logger.info("━" * 60)

    return {"report": report}
