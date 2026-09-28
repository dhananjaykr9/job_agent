"""
Validation Agent — checks field completeness and data quality.

Runs after LLM extraction to ensure we have enough information
to insert a job into the Excel tracker.
"""
from __future__ import annotations

from ..schemas import JobCandidate
from ..utils.logger import get_logger
from ..utils.normalization import is_blocked_url, is_aggregator_page, has_invalid_content, is_senior_title

logger = get_logger("job_agent.validation")

# Fields that MUST be present for a valid job record
REQUIRED_FIELDS = ["company_name", "job_title"]
# Fields that SHOULD be present (affect confidence)
IMPORTANT_FIELDS = ["location", "job_url"]


class ValidationAgent:
    """Validates extracted job data for completeness and quality."""

    def validate(self, job: JobCandidate) -> tuple[bool, list[str]]:
        """
        Validate a single JobCandidate.

        Returns:
            (is_valid, list_of_issues)
        """
        issues: list[str] = []

        # ── Required fields ─────────────────────────────
        for field in REQUIRED_FIELDS:
            value = getattr(job, field, "")
            if not value or not value.strip():
                issues.append(f"Missing required field: {field}")

        # ── Important fields (warnings, not blockers) ───
        for field in IMPORTANT_FIELDS:
            value = getattr(job, field, "")
            if not value or not value.strip():
                issues.append(f"Missing important field: {field}")

        # ── URL validation ──────────────────────────────
        if job.job_url:
            if not job.job_url.startswith(("http://", "https://")):
                issues.append(f"Invalid URL format: {job.job_url}")
            elif is_blocked_url(job.job_url):
                issues.append(f"Blocked non-job domain URL (e.g. Wikipedia/YouTube): {job.job_url}")
            elif is_aggregator_page(job.job_url):
                issues.append(f"Generic aggregator listing/search page (not a specific job): {job.job_url}")

        # ── Closed / inactive posting ───────────────────
        combined_text = f"{job.job_title} {job.description or ''}"
        if has_invalid_content(combined_text):
            issues.append(f"Posting marked as inactive or closed: '{job.job_title}'")

        # ── Senior title — hard reject for fresher agent ──
        if is_senior_title(job.job_title):
            issues.append(f"Senior/experienced title not suitable for fresher agent: '{job.job_title}'")

        # ── Suspicious patterns ─────────────────────────
        title_lower = job.job_title.lower()
        suspicious_keywords = [
            "work from home earn",
            "data entry operator",
            "form filling",
            "copy paste",
            "typing job",
            "sms sending",
            "ad posting",
        ]
        if any(kw in title_lower for kw in suspicious_keywords):
            issues.append(f"Suspicious job title: {job.job_title}")

        # ── Job role check (must be a job opening, not a general topic/article) ──
        valid_role_indicators = [
            "engineer", "developer", "intern", "associate", "analyst", "specialist",
            "trainee", "programmer", "architect", "lead", "consultant", "scientist",
            "walk in", "walkin", "hiring", "drive", "officer", "executive", "member",
            "sde", "swe", "fresher", "opening", "role", "position"
        ]
        if not any(ind in title_lower for ind in valid_role_indicators):
            issues.append(f"Title appears to be a generic topic/article rather than a job opening: '{job.job_title}'")

        # ── Company name sanity ─────────────────────────
        if job.company_name:
            clean_company = job.company_name.strip().lower()
            if len(clean_company) <= 2:
                issues.append(f"Company name too short/invalid: '{job.company_name}'")
            invalid_companies = [
                "en", "in", "it", "to", "at", "by", "for", "the", "an", "a",
                "n/a", "na", "unknown", "--", "-", "it company", "company",
                "wikipedia", "youtube", "reddit", "quora", "medium",
                "builtin", "topstartups", "techstartupslist", "builtinbengaluru",
                "roadmap", "marketwatch", "findmyjobss", "freshershunt",
                "placementindia", "simplyhired", "ycombinator",
                "foundit", "bayt", "hirist", "instahyre", "cutshort", "careesma",
                "shine", "timesjobs", "freshersworld", "monsterindia",
            ]
            if clean_company in invalid_companies:
                issues.append(f"Placeholder or aggregator name (not a real employer): '{job.company_name}'")
            if any(pfx in clean_company for pfx in ["linkedin_jobs", "naukri_", "shine_", "duckduckgo", "freshersworld"]):
                issues.append(f"Company name is a source tag or search query (not a real employer): '{job.company_name}'")

        # ── Determine validity ──────────────────────────
        has_required = not any("Missing required" in i for i in issues)
        is_suspicious = any("Suspicious" in i for i in issues)
        is_blocked = any(
            "Blocked non-job" in i or "generic topic" in i
            or "Company name too short" in i or "Placeholder or aggregator" in i
            or "is a source tag" in i or "Generic aggregator" in i
            or "inactive or closed" in i or "Senior/experienced title" in i
            for i in issues
        )

        is_valid = has_required and not is_suspicious and not is_blocked

        if issues:
            logger.info(
                f"Validation {'✅ PASS' if is_valid else '❌ FAIL'}: "
                f"{job.company_name} — {job.job_title} | "
                f"Issues: {', '.join(issues)}"
            )

        return is_valid, issues

    def validate_batch(
        self, jobs: list[JobCandidate]
    ) -> tuple[list[JobCandidate], list[JobCandidate]]:
        """
        Validate a batch of jobs.

        Returns:
            (valid_jobs, invalid_jobs)
        """
        valid = []
        invalid = []

        for job in jobs:
            is_valid, issues = self.validate(job)
            if is_valid:
                valid.append(job)
            else:
                job.match_result = "reject"
                job.match_reason = "; ".join(issues)
                invalid.append(job)

        logger.info(
            f"Validation: [success]{len(valid)} valid[/], "
            f"[error]{len(invalid)} invalid[/] / {len(jobs)} total"
        )
        return valid, invalid
