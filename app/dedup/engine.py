"""
Deduplication Engine — multi-level duplicate detection.

Prevents the same job from being added to Excel multiple times,
even when it appears on different platforms (LinkedIn + Naukri + career page).

Levels:
    1. Exact URL match
    2. Company + normalized title + location fingerprint
    3. SQLite history lookup
"""
from __future__ import annotations

from ..schemas import JobCandidate, DuplicateLevel
from ..database.repository import JobRepository
from ..utils.normalization import clean_url, compute_fingerprint
from ..utils.logger import get_logger

logger = get_logger("job_agent.dedup")


class DeduplicationEngine:
    """
    Multi-level duplicate detector.

    Uses both in-memory sets (for the current run) and the SQLite
    database (for cross-run dedup).
    """

    def __init__(self, repository: JobRepository):
        self.repo = repository

        # Cache existing data at start of run for speed
        self._known_urls: set[str] = repository.get_all_urls()
        self._known_fingerprints: set[str] = repository.get_all_fingerprints()

        # Track jobs seen in the current run
        self._run_urls: set[str] = set()
        self._run_fingerprints: set[str] = set()

        logger.info(
            f"Dedup engine loaded: {len(self._known_urls)} URLs, "
            f"{len(self._known_fingerprints)} fingerprints from DB"
        )

    def is_duplicate(self, job: JobCandidate) -> tuple[bool, DuplicateLevel, str]:
        """
        Check if a job is a duplicate.

        Returns:
            (is_duplicate, level, reason)
        """
        # ── Level 1: Exact URL ──────────────────────────
        url = clean_url(job.job_url)
        if url:
            if url in self._known_urls or url in self._run_urls:
                return True, DuplicateLevel.EXACT_URL, f"URL already seen: {url}"

        # ── Level 2: Fingerprint ────────────────────────
        if job.company_name and job.job_title:
            fp = compute_fingerprint(job.company_name, job.job_title, job.location)
            if fp in self._known_fingerprints or fp in self._run_fingerprints:
                return (
                    True,
                    DuplicateLevel.FINGERPRINT,
                    f"Fingerprint match: {job.company_name} / {job.job_title} / {job.location}",
                )

        return False, DuplicateLevel.UNIQUE, ""

    def mark_seen(self, job: JobCandidate):
        """Register a job as seen in the current run (prevents intra-run dupes)."""
        url = clean_url(job.job_url)
        if url:
            self._run_urls.add(url)

        if job.company_name and job.job_title:
            fp = compute_fingerprint(job.company_name, job.job_title, job.location)
            self._run_fingerprints.add(fp)

    def deduplicate_batch(
        self, jobs: list[JobCandidate]
    ) -> tuple[list[JobCandidate], list[JobCandidate]]:
        """
        Deduplicate a batch of jobs.

        Returns:
            (unique_jobs, duplicate_jobs)
        """
        unique: list[JobCandidate] = []
        duplicates: list[JobCandidate] = []

        for job in jobs:
            is_dup, level, reason = self.is_duplicate(job)

            if is_dup:
                job.duplicate_level = level.value
                job.match_result = "reject"
                job.match_reason = f"Duplicate ({level.value}): {reason}"
                duplicates.append(job)
                logger.info(
                    f"[warning]DUPLICATE[/] ({level.value}) "
                    f"{job.company_name} — {job.job_title}"
                )
            else:
                self.mark_seen(job)
                unique.append(job)

        logger.info(
            f"Dedup results: [success]{len(unique)} unique[/], "
            f"[warning]{len(duplicates)} duplicates[/]"
        )
        return unique, duplicates
