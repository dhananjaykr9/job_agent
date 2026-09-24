"""
Job Matching Engine — Rule-based + AI-assisted filtering.

Applies deterministic rules first (location, experience, excluded roles),
then uses LLM for ambiguous cases (fuzzy title matching).

DESIGN PRINCIPLE: Deterministic rules ALWAYS win over AI confidence.
A job titled "Data Analyst" gets rejected by the exclusion rule
even if the AI gives it 98% confidence.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

import google.generativeai as genai

from ..schemas import JobCandidate, MatchDetails, MatchResult
from ..config.settings import JobPreferences
from ..utils.normalization import normalize_title, normalize_location, extract_years
from ..utils.logger import get_logger

logger = get_logger("job_agent.matching")

ROLE_MATCHING_PROMPT = """You are a job title matching agent. Determine if the given job title matches any of the target roles.

TARGET ROLES: {target_roles}
EXCLUDED ROLES: {excluded_roles}

JOB TITLE: "{job_title}"
JOB DESCRIPTION EXCERPT: "{description}"

Consider:
- Equivalent titles (e.g., "ETL Pipeline Developer" ≈ "ETL Developer")
- Titles describing the same work differently
- Implicit role matches from the description

Return JSON:
{{
    "matches_target": true/false,
    "matches_exclusion": true/false,
    "matched_role": "which target role it matches (if any)",
    "confidence": 0.0 to 1.0,
    "reasoning": "brief explanation"
}}"""


class MatchingEngine:
    """
    Multi-stage job matching against configured preferences.

    Pipeline:
        Location → Experience → Role Inclusion → Exclusion → Date → Final
    """

    def __init__(
        self,
        preferences: JobPreferences,
        api_key: str | None = None,
        model: str = "gemini-2.0-flash",
    ):
        self.prefs = preferences
        self.api_key = api_key
        self.model_name = model

        # Pre-compute normalized lists for fast matching
        self._locations = [normalize_location(loc) for loc in preferences.locations]
        self._included = [normalize_title(r) for r in preferences.included_roles]
        self._excluded = [normalize_title(r) for r in preferences.excluded_roles]

    # ═══════════════════════════════════════════════════
    # Public API
    # ═══════════════════════════════════════════════════
    def match(self, job: JobCandidate) -> MatchDetails:
        """Run the full matching pipeline on a single job."""
        reasons: list[str] = []

        # ── Stage 1: Location ───────────────────────────
        loc_ok = self._check_location(job)
        if not loc_ok:
            reasons.append(f"Location mismatch: '{job.location}' not in {self.prefs.locations}")

        # ── Stage 2: Experience ─────────────────────────
        exp_ok = self._check_experience(job)
        if not exp_ok:
            reasons.append(
                f"Experience too high: '{job.experience}' > "
                f"{self.prefs.max_experience_years} years"
            )

        # ── Stage 3: Role exclusion (hard rule) ─────────
        is_excluded = self._check_exclusion(job)
        if is_excluded:
            reasons.append(f"Excluded role: '{job.job_title}'")

        # ── Stage 4: Role inclusion ─────────────────────
        role_match = self._check_role_inclusion(job)
        if not role_match and not is_excluded:
            # Try AI-based fuzzy matching for ambiguous titles
            if self.api_key:
                ai_match = self._ai_role_match(job)
                if ai_match:
                    role_match = True
                    reasons.append(f"AI-matched to: {ai_match}")
                else:
                    reasons.append(f"Role not in target list: '{job.job_title}'")
            else:
                reasons.append(f"Role not in target list: '{job.job_title}'")

        # ── Stage 5: Posting date freshness ─────────────
        date_ok = self._check_posting_date(job)
        if not date_ok:
            reasons.append(f"Post too old: '{job.posting_date}'")

        # ── Final decision ──────────────────────────────
        if is_excluded:
            result = MatchResult.REJECT
        elif not loc_ok and job.location:  # Only reject if location is known
            result = MatchResult.REJECT
        elif not exp_ok and job.experience:
            result = MatchResult.REJECT
        elif not date_ok:
            result = MatchResult.REJECT
        elif role_match and (loc_ok or not job.location):
            result = MatchResult.MATCH
        elif not role_match and not reasons:
            result = MatchResult.REVIEW
        else:
            result = MatchResult.REVIEW

        score = self._compute_score(job, loc_ok, exp_ok, role_match, date_ok)

        details = MatchDetails(result=result, reasons=reasons, score=score)

        log_style = {
            MatchResult.MATCH: "[success]MATCH[/]",
            MatchResult.REJECT: "[error]REJECT[/]",
            MatchResult.REVIEW: "[warning]REVIEW[/]",
        }
        logger.info(
            f"{log_style[result]} {job.company_name} — {job.job_title} "
            f"({score:.0%}) {'; '.join(reasons) if reasons else ''}"
        )

        return details

    def match_batch(self, jobs: list[JobCandidate]) -> dict[str, list[JobCandidate]]:
        """
        Match a batch of jobs and return them grouped by outcome.

        Returns dict with keys: 'matched', 'rejected', 'review'
        """
        matched, rejected, review = [], [], []

        for job in jobs:
            details = self.match(job)
            job.match_result = details.result.value
            job.match_reason = "; ".join(details.reasons)
            job.confidence_score = max(job.confidence_score, details.score)

            if details.result == MatchResult.MATCH:
                matched.append(job)
            elif details.result == MatchResult.REJECT:
                rejected.append(job)
            else:
                job.review_reason = job.match_reason
                review.append(job)

        logger.info(
            f"Matching results: [success]{len(matched)} matched[/], "
            f"[error]{len(rejected)} rejected[/], "
            f"[warning]{len(review)} review[/]"
        )
        return {"matched": matched, "rejected": rejected, "review": review}

    # ═══════════════════════════════════════════════════
    # Internal checks
    # ═══════════════════════════════════════════════════
    def _check_location(self, job: JobCandidate) -> bool:
        if not job.location:
            return True  # Unknown location — don't reject
        loc = normalize_location(job.location)
        return any(target in loc or loc in target for target in self._locations)

    def _check_experience(self, job: JobCandidate) -> bool:
        if not job.experience:
            return True  # Unknown experience — don't reject
        years = extract_years(job.experience)
        if years is None:
            return True
        return years <= self.prefs.max_experience_years

    def _check_exclusion(self, job: JobCandidate) -> bool:
        title = normalize_title(job.job_title)
        return any(excl in title or title in excl for excl in self._excluded)

    def _check_role_inclusion(self, job: JobCandidate) -> bool:
        title = normalize_title(job.job_title)
        return any(incl in title or title in incl for incl in self._included)

    def _check_posting_date(self, job: JobCandidate) -> bool:
        if not job.posting_date:
            return True  # Unknown date — don't reject
        try:
            # Try common date formats
            for fmt in ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y"]:
                try:
                    posted = datetime.strptime(job.posting_date, fmt)
                    cutoff = datetime.now() - timedelta(days=self.prefs.max_age_days)
                    return posted >= cutoff
                except ValueError:
                    continue
            return True  # Can't parse — don't reject
        except Exception:
            return True

    def _compute_score(
        self,
        job: JobCandidate,
        loc_ok: bool,
        exp_ok: bool,
        role_ok: bool,
        date_ok: bool,
    ) -> float:
        score = job.confidence_score
        if loc_ok:
            score = max(score, score + 0.1)
        if exp_ok:
            score = max(score, score + 0.1)
        if role_ok:
            score = max(score, score + 0.2)
        if date_ok:
            score = max(score, score + 0.05)
        return min(score, 1.0)

    def _ai_role_match(self, job: JobCandidate) -> str | None:
        """Use Gemini to determine if an ambiguous title matches target roles."""
        try:
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(
                self.model_name,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                ),
            )

            prompt = ROLE_MATCHING_PROMPT.format(
                target_roles=", ".join(self.prefs.included_roles),
                excluded_roles=", ".join(self.prefs.excluded_roles),
                job_title=job.job_title,
                description=job.description[:500],
            )

            response = model.generate_content(prompt)
            data = json.loads(response.text)

            if data.get("matches_target") and not data.get("matches_exclusion"):
                return data.get("matched_role", "unknown")
            return None

        except Exception as e:
            logger.warning(f"AI role matching failed: {e}")
            return None
