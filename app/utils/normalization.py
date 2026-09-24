"""
Text normalization utilities for consistent comparison
across job titles, company names, locations, and skills.
"""
from __future__ import annotations

import re
import hashlib
from typing import Optional


def normalize_text(text: str) -> str:
    """Lowercase, strip, collapse whitespace."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip().lower())


def normalize_company(name: str) -> str:
    """
    Normalize company names for comparison.
    Removes common suffixes like Pvt Ltd, Inc, LLC, etc.
    """
    if not name:
        return ""
    name = normalize_text(name)
    # Remove common corporate suffixes
    suffixes = [
        r"\b(pvt\.?\s*ltd\.?)",
        r"\b(private\s+limited)",
        r"\b(limited)",
        r"\b(inc\.?)",
        r"\b(llc\.?)",
        r"\b(corp\.?)",
        r"\b(corporation)",
        r"\b(technologies)",
        r"\b(tech)",
        r"\b(solutions)",
        r"\b(services)",
        r"\b(india)",
    ]
    for suffix in suffixes:
        name = re.sub(suffix, "", name)
    return re.sub(r"\s+", " ", name).strip()


def normalize_title(title: str) -> str:
    """
    Normalize job titles for comparison.
    Strips seniority prefixes, standardizes common synonyms.
    """
    if not title:
        return ""
    title = normalize_text(title)

    # Remove seniority prefixes for matching
    prefixes = [
        r"^(sr\.?\s+|senior\s+)",
        r"^(jr\.?\s+|junior\s+)",
        r"^(lead\s+)",
        r"^(principal\s+)",
        r"^(staff\s+)",
        r"^(associate\s+)",
    ]
    for prefix in prefixes:
        title = re.sub(prefix, "", title)

    # Standardize common synonyms
    replacements = {
        r"\bswe\b": "software engineer",
        r"\bsde\b": "software development engineer",
        r"\bde\b": "data engineer",
        r"\bml\b": "machine learning",
        r"\bai\b": "artificial intelligence",
        r"\betl\b": "etl",
        r"\bdev\b": "developer",
    }
    for pattern, replacement in replacements.items():
        title = re.sub(pattern, replacement, title)

    return title.strip()


def normalize_location(location: str) -> str:
    """Normalize location strings for comparison."""
    if not location:
        return ""
    location = normalize_text(location)
    # Common location normalizations
    replacements = {
        r"\bbangalore\b": "bengaluru",
        r"\bbombay\b": "mumbai",
        r"\bmadras\b": "chennai",
        r"\bcalcutta\b": "kolkata",
        r"\bwfh\b": "remote",
        r"\bwork from home\b": "remote",
    }
    for pattern, replacement in replacements.items():
        location = re.sub(pattern, replacement, location)
    return location.strip()


def extract_years(experience_str: str) -> Optional[int]:
    """
    Extract the minimum years from an experience string.

    Examples:
        "0-1 years" → 0
        "2+ years" → 2
        "Fresher" → 0
        "3 to 5 years" → 3
    """
    if not experience_str:
        return None

    exp = experience_str.lower().strip()

    if any(word in exp for word in ["fresher", "entry level", "entry-level", "0 year", "intern"]):
        return 0

    # Match patterns like "0-1", "2+", "3 to 5", "1-3 years"
    match = re.search(r"(\d+)\s*[-–to]+\s*(\d+)", exp)
    if match:
        return int(match.group(1))

    match = re.search(r"(\d+)\+?", exp)
    if match:
        return int(match.group(1))

    return None


def compute_fingerprint(company: str, title: str, location: str) -> str:
    """
    Compute a deduplication fingerprint from normalized fields.
    Used for Level 3 duplicate detection.
    """
    normalized = f"{normalize_company(company)}|{normalize_title(title)}|{normalize_location(location)}"
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


def compute_description_hash(description: str) -> str:
    """Hash a description for quick equality checks."""
    if not description:
        return ""
    return hashlib.sha256(normalize_text(description).encode()).hexdigest()[:32]


def clean_url(url: str) -> str:
    """Normalize URLs for comparison — remove trailing slashes, tracking params."""
    if not url:
        return ""
    url = url.strip().rstrip("/")
    # Remove common tracking parameters
    url = re.sub(r"[?&](utm_\w+|ref|source|fbclid|gclid)=[^&]*", "", url)
    # Clean up leftover ? or &
    url = re.sub(r"\?$", "", url)
    url = re.sub(r"\?&", "?", url)
    return url
