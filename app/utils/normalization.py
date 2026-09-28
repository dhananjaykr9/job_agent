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


# Domains that NEVER represent a single direct job posting
BLOCKED_DOMAINS = [
    # Encyclopedias & knowledge bases
    "wikipedia.org",
    "wikimedia.org",
    "wiktionary.org",
    "britannica.com",
    "investopedia.com",
    "dictionary.com",
    # Video & entertainment
    "youtube.com",
    "youtu.be",
    # Social feeds (not hiring posts — covered by linkedin_posts source)
    "facebook.com",
    "instagram.com",
    "twitter.com",
    "x.com",
    "reddit.com",
    "quora.com",
    "medium.com",
    "pinterest.com",
    # Developer knowledge / tutorials (never job postings)
    "github.com",
    "gitlab.com",
    "stackoverflow.com",
    "stackexchange.com",
    "geeksforgeeks.org",
    "w3schools.com",
    "tutorialspoint.com",
    "javatpoint.com",
    "roadmap.sh",
    "dev.to",
    "hashnode.com",
    # Learning platforms
    "coursera.org",
    "udemy.com",
    "edx.org",
    "skillshare.com",
    "pluralsight.com",
    # E-commerce (not jobs)
    "amazon.in",
    "amazon.com",
    "flipkart.com",
    # Financial / news (not jobs)
    "marketwatch.com",
    "moneycontrol.com",
    "economictimes.com",
    # Generic job aggregators that give listing PAGES not specific jobs
    # (individual job URLs from them are still fine — filtered by is_aggregator_page)
    "ycombinator.com",
    "topstartups.io",
    "techstartupslist.com",
]

# Domains that ARE job boards but whose specific URL patterns indicate
# a search/listing page (not a specific job posting)
AGGREGATOR_SEARCH_PATTERNS = [
    "/search/",               # generic search pages (foundit.in/search/..., simplyhired.co.in/search/...)
    "/search?",               # generic search query URLs
    "?q=",                    # search query param
    "&l=",                    # location filter param
    "-jobs-in-",              # aggregator search listing pages like '...-jobs-in-hyderabad'
    "/jobs-in-",              # generic city job listing
    "/jobs/search",           # search endpoints
    "/job-search?",           # search endpoints with params
    "/careers?departments=",  # generic career category pages
    "/jobs/role/",            # YC generic role pages (not specific jobs)
    "/area-of-interest/",     # Accenture career category pages
    "/explore-careers/",      # generic explore pages
    # Content pages that are NEVER job postings
    "/blog/",
    "/blogs/",
    "/article/",
    "/articles/",
    "/course/",
    "/courses/",
    "/course-category/",
    "/training/",
    "/learn/",
    "/tutorial/",
    "/guide/",
]

# Job board aggregator domains — only pass if URL points to a specific job (has numeric/hash ID)
AGGREGATOR_DOMAINS = [
    "foundit.in",
    "foundit.com",
    "bayt.com",
    "builtin.com",
    "builtinbengaluru.in",
    "builtinpune.com",
    "placementindia.com",
    "simplyhired.co.in",
    "simplyhired.com",
    "freshersworld.com",
    "timesjobs.com",
    "shine.com",
    "monsterindia.com",
    "hirist.tech",
    "hirist.com",
    "instahyre.com",
    "cutshort.io",
    "careesma.in",
    "indeed.com",
    "indeed.co.in",
    "glassdoor.com",
    "glassdoor.co.in",
    "accenture.com",          # their generic career category pages (specific job URLs still valid)
]

# Phrases that strongly indicate the content is NOT a valid job posting
INVALID_CONTENT_PHRASES = [
    "currently not hiring",
    "not accepting applications",
    "position is closed",
    "no longer accepting",
    "this role has been filled",
]

# Robust regex patterns for detecting senior/experienced roles anywhere in title
SENIOR_TITLE_REGEXES = [
    # Senior keywords anywhere in the title
    re.compile(r'\b(sr\.?|senior|lead|principal|staff|manager|mgr|director|vp|vice\s+president|head\s+of|chief|distinguished|architect|specialist|expert|experienced|lateral)\b', re.IGNORECASE),
    # Roman numeral levels: II, III, IV, V (e.g. "Data Engineer II", "SDE III")
    re.compile(r'\b(ii|iii|iv|v)\b', re.IGNORECASE),
    # Numeric levels: Engineer 2, Associate 2, Developer 3, Level 2, L2, SDE-2, etc.
    re.compile(r'\b(?:engineer|developer|associate|analyst|consultant|sde|de|swe)\s*[-_ ]*([2-9])\b', re.IGNORECASE),
    re.compile(r'\b(level\s*[2-6]|l[2-6]|sde\s*[-_ ]?[2-4]|de\s*[-_ ]?[2-4]|band\s*[6-9])\b', re.IGNORECASE),
    # Experience years explicitly in title: e.g. "3+ years", "2-5 yrs"
    re.compile(r'\b([2-9]|\d{2,})\+?\s*(?:to\s*\d+\s*)?(?:years?|yrs?|yr)\b', re.IGNORECASE),
]


def is_blocked_url(url: str) -> bool:
    """Return True if URL belongs to an encyclopedia, tutorial/social site, etc."""
    if not url:
        return True
    url_lower = url.lower()
    return any(domain in url_lower for domain in BLOCKED_DOMAINS)


def is_aggregator_page(url: str) -> bool:
    """Return True if URL is a generic search/listing page (not a specific job posting)."""
    if not url:
        return False
    url_lower = url.lower()
    # Check generic URL patterns that indicate a search/listing page
    if any(pat in url_lower for pat in AGGREGATOR_SEARCH_PATTERNS):
        return True
    # For known aggregator sites, reject if URL doesn't contain a numeric or hash job ID
    for agg in AGGREGATOR_DOMAINS:
        if agg in url_lower:
            # A specific job page must have a numeric ID (5+ digits) or 8+ char hex/alphanumeric hash
            if not re.search(r'/(\d{5,}|[a-f0-9]{8,})', url_lower):
                return True
    return False


def has_invalid_content(text: str) -> bool:
    """Return True if the text strongly signals a non-active, closed, or invalid posting."""
    text_lower = (text or "").lower()
    return any(phrase in text_lower for phrase in INVALID_CONTENT_PHRASES)


def is_senior_title(title: str) -> bool:
    """Return True if job title indicates a senior/experienced role (not suitable for freshers)."""
    if not title:
        return False
    t = title.strip()
    return any(rx.search(t) for rx in SENIOR_TITLE_REGEXES)
