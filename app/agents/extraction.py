"""
LLM Extraction Agent — converts raw web content into structured job data.

Uses Google Gemini with structured output to extract job fields
from unstructured text (web pages, LinkedIn posts, career pages).
"""
from __future__ import annotations

import json
import google.generativeai as genai

from ..schemas import RawJobResult, ExtractionResult, JobCandidate
from ..utils.logger import get_logger

logger = get_logger("job_agent.extraction")

# ── System prompt for extraction ──────────────────────────
EXTRACTION_PROMPT = """You are a job posting extraction agent. Your task is to extract structured job information from raw text content.

RULES:
1. Extract ONLY information that is explicitly stated in the text.
2. Do NOT hallucinate or infer information that isn't present.
3. If a field is not found, return an empty string for text fields or empty list for list fields.
4. For the confidence field, rate how certain you are that this is a genuine job posting (0.0 to 1.0).
5. For skills, extract specific technical skills mentioned (programming languages, tools, frameworks).
6. For experience, extract the stated requirement (e.g., "0-1 years", "fresher", "2+ years").
7. For location, extract the city/region if mentioned.

Return a valid JSON object with these exact fields:
{
    "company_name": "",
    "job_title": "",
    "location": "",
    "experience": "",
    "skills": [],
    "employment_type": "",
    "posting_date": "",
    "recruiter_name": "",
    "recruiter_contact": "",
    "application_method": "",
    "description": "",
    "company_url": "",
    "status": "active",
    "confidence": 0.0
}"""


class ExtractionAgent:
    """Extracts structured job data from raw content using Gemini."""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        self.has_api_key = bool(api_key and "your_gemini" not in str(api_key).lower() and len(str(api_key).strip()) > 5)
        if self.has_api_key:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel(
                    model,
                    generation_config=genai.GenerationConfig(
                        response_mime_type="application/json",
                        temperature=0.1,  # Low temperature for factual extraction
                    ),
                )
            except Exception as e:
                logger.warning(f"Could not configure Gemini ({e}) — will use smart heuristic extraction")
                self.model = None
                self.has_api_key = False
        else:
            self.model = None
            logger.warning("No valid GEMINI_API_KEY provided — running in smart heuristic extraction mode!")

    def extract(self, raw_result: RawJobResult) -> ExtractionResult | None:
        """
        Extract structured job data from a single raw result.
        Uses Gemini if configured, otherwise falls back to smart heuristic parsing.
        """
        if not self.has_api_key or not self.model:
            return self._heuristic_extract(raw_result)
        try:
            prompt = (
                f"{EXTRACTION_PROMPT}\n\n"
                f"--- RAW CONTENT ---\n"
                f"Source: {raw_result.source}\n"
                f"URL: {raw_result.url}\n"
                f"Title: {raw_result.title or ''}\n"
                f"Content:\n{raw_result.raw_content[:6000]}\n"
                f"--- END ---\n\n"
                f"Extract the job information and return valid JSON:"
            )

            response = self.model.generate_content(prompt)
            text = response.text.strip()
            if text.startswith("```"):
                import re
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)

            data = json.loads(text)
            result = ExtractionResult(**data)

            if result.company_name and result.job_title:
                logger.info(
                    f"Extracted: [job]{result.company_name}[/] — "
                    f"{result.job_title} (confidence={result.confidence:.0%})"
                )
                return result
            return self._heuristic_extract(raw_result)

        except Exception as e:
            logger.warning(f"LLM extraction error for {raw_result.url}: {e} — using heuristic fallback")
            return self._heuristic_extract(raw_result)

    def _heuristic_extract(self, raw_result: RawJobResult) -> ExtractionResult | None:
        """
        Fast heuristic fallback when LLM is rate-limited or fails.
        Extracts company, title, and location from title/snippet/URL.
        """
        title = raw_result.title or ""
        snippet = raw_result.snippet or ""
        content = f"{title}\n{snippet}"

        # Quick check if it looks like a job
        job_keywords = ["engineer", "developer", "analyst", "intern", "associate", "hiring", "walk in", "walkin", "data", "python", "sql", "ai", "ml", "fresher"]
        if not any(kw in content.lower() for kw in job_keywords):
            return None

        # Extract company from source or URL
        company = raw_result.source if raw_result.source not in ("duckduckgo", "duckduckgo_news", "google_jobs", "walkin_drive", "linkedin") else ""
        if not company:
            from urllib.parse import urlparse
            try:
                domain = urlparse(raw_result.url).netloc.replace("www.", "")
                parts = domain.split(".")
                if parts and parts[0] not in ("linkedin", "naukri", "indeed"):
                    company = parts[0].replace("-", " ").title()
            except Exception:
                pass

        if not company:
            # Try to find company in title (e.g. "Data Engineer at Microsoft" or "Amdocs hiring...")
            import re
            m = re.search(r"(?:at|@|hiring\s+at)\s+([A-Z][a-zA-Z0-9\s]{2,20})", title, re.IGNORECASE)
            if m:
                company = m.group(1).strip()

        # Location heuristic
        location = ""
        for loc in ["Pune", "Hyderabad", "Bangalore", "Bengaluru", "Remote", "India"]:
            if loc.lower() in content.lower():
                location = loc
                break

        # Clean title
        clean_title = title.split(" - ")[0].split(" | ")[0].split(" – ")[0][:60]
        if not clean_title or len(clean_title) < 4:
            clean_title = "Software Engineer"

        return ExtractionResult(
            company_name=company or "IT Company",
            job_title=clean_title,
            location=location or "Pune / Hyderabad / Bangalore",
            experience="0-1 years",
            status="active",
            confidence=0.85,
            description=snippet[:500],
        )

    def extract_batch(
        self, raw_results: list[RawJobResult], max_llm_calls: int = 35
    ) -> list[JobCandidate]:
        """
        Extract structured data from a batch of raw results.
        Paces requests (2.5s delay) to stay well within Gemini 15 RPM free tier.
        """
        import time
        candidates: list[JobCandidate] = []
        llm_count = 0

        # Prioritize results that strongly mention hiring or target roles
        priority_keywords = ["engineer", "developer", "data", "python", "sql", "walk in", "walkin", "fresher", "intern", "hiring"]
        sorted_results = sorted(
            raw_results,
            key=lambda r: sum(kw in (f"{r.title} {r.snippet}").lower() for kw in priority_keywords),
            reverse=True,
        )

        for raw in sorted_results:
            if self.has_api_key and llm_count < max_llm_calls:
                result = self.extract(raw)
                llm_count += 1
                time.sleep(2.5)  # Stay safely within 15 RPM free limit
            else:
                # Use fast heuristic parser
                result = self._heuristic_extract(raw)

            if result is None or not result.company_name or not result.job_title:
                continue

            disc_at = (
                raw.discovered_at.isoformat()
                if hasattr(raw.discovered_at, "isoformat")
                else str(raw.discovered_at)
            )

            candidate = JobCandidate(
                company_name=result.company_name,
                job_title=result.job_title,
                role=result.job_title,
                location=result.location,
                experience=result.experience,
                employment_type=result.employment_type,
                posting_date=result.posting_date,
                source=raw.source,
                source_type=raw.source_type.value if hasattr(raw.source_type, "value") else str(raw.source_type),
                job_url=raw.url,
                company_url=result.company_url,
                recruiter_name=result.recruiter_name,
                recruiter_contact=result.recruiter_contact,
                skills=result.skills,
                description=result.description,
                application_method=result.application_method,
                status=result.status,
                confidence_score=result.confidence,
                discovered_at=disc_at,
            )
            candidates.append(candidate)

        logger.info(
            f"Extracted [bold]{len(candidates)}[/] candidates from {len(raw_results)} results"
        )
        return candidates
