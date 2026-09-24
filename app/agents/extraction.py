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
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1,  # Low temperature for factual extraction
            ),
        )

    def extract(self, raw_result: RawJobResult) -> ExtractionResult | None:
        """
        Extract structured job data from a single raw result.

        Returns None if extraction fails or confidence is too low.
        """
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
            data = json.loads(response.text)
            result = ExtractionResult(**data)

            logger.info(
                f"Extracted: [job]{result.company_name}[/] — "
                f"{result.job_title} (confidence={result.confidence:.0%})"
            )
            return result

        except Exception as e:
            logger.warning(f"Extraction failed for {raw_result.url}: {e}")
            return None

    def extract_batch(
        self, raw_results: list[RawJobResult]
    ) -> list[JobCandidate]:
        """
        Extract structured data from a batch of raw results.

        Returns a list of JobCandidate objects with extraction data merged in.
        """
        candidates: list[JobCandidate] = []

        for raw in raw_results:
            result = self.extract(raw)
            if result is None:
                continue

            candidate = JobCandidate(
                company_name=result.company_name,
                job_title=result.job_title,
                role=result.job_title,  # Role defaults to title
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
                discovered_at=raw.discovered_at.isoformat(),
            )
            candidates.append(candidate)

        logger.info(
            f"Extracted [bold]{len(candidates)}[/] / {len(raw_results)} results"
        )
        return candidates
