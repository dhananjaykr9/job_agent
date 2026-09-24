"""
Validation Agent — checks field completeness and data quality.

Runs after LLM extraction to ensure we have enough information
to insert a job into the Excel tracker.
"""
from __future__ import annotations

from ..schemas import JobCandidate
from ..utils.logger import get_logger

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

        # ── Company name sanity ─────────────────────────
        if job.company_name:
            if len(job.company_name) < 2:
                issues.append("Company name too short")
            if job.company_name.lower() in ["n/a", "na", "unknown", "--", "-"]:
                issues.append("Placeholder company name")

        # ── Determine validity ──────────────────────────
        has_required = not any("Missing required" in i for i in issues)
        is_suspicious = any("Suspicious" in i for i in issues)

        is_valid = has_required and not is_suspicious

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
