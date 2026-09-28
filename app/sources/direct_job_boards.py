"""
Direct Job Board Scraper — fetches directly from Indian job portals.

No DuckDuckGo needed. Hits Naukri, Shine, Freshersworld, and LinkedIn Jobs
directly for walk-in drives and fresher openings in Pune/Hyderabad/Bangalore.
"""
from __future__ import annotations

import json
import time
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from .base import BaseSource
from ..schemas import RawJobResult, SourceType
from ..utils.normalization import is_senior_title, has_invalid_content, extract_years


NAUKRI_WALKIN_URLS = [
    ("https://www.naukri.com/walkin-jobs-in-pune", "Pune"),
    ("https://www.naukri.com/walkin-jobs-in-hyderabad", "Hyderabad"),
    ("https://www.naukri.com/walkin-jobs-in-bangalore-bengaluru", "Bangalore"),
]

NAUKRI_FRESHER_URLS = [
    ("https://www.naukri.com/data-engineer-jobs-in-pune?experienceList=0,1&experience=0", "Data Engineer Pune"),
    ("https://www.naukri.com/python-developer-jobs-in-pune?experienceList=0,1&experience=0", "Python Developer Pune"),
    ("https://www.naukri.com/artificial-intelligence-jobs-in-pune?experienceList=0,1", "AI Engineer Pune"),
    ("https://www.naukri.com/data-engineer-jobs-in-hyderabad?experienceList=0,1", "Data Engineer Hyderabad"),
    ("https://www.naukri.com/software-engineer-jobs-in-pune?experienceList=0,1&experience=0", "Software Engineer Pune"),
    ("https://www.naukri.com/data-engineer-jobs-in-bangalore-bengaluru?experienceList=0,1", "Data Engineer Bangalore"),
]

SHINE_WALKIN_URLS = [
    ("https://www.shine.com/job-search/walk-in-interview-jobs-in-pune/", "Walk-in Pune"),
    ("https://www.shine.com/job-search/walk-in-interview-jobs-in-hyderabad/", "Walk-in Hyderabad"),
    ("https://www.shine.com/job-search/fresher-it-engineer-jobs-in-pune/", "IT Fresher Pune"),
]

FRESHERSWORLD_URLS = [
    ("https://www.freshersworld.com/jobs/freshers-jobs-in-pune", "Fresher Jobs Pune"),
    ("https://www.freshersworld.com/jobs/data-engineer-jobs/freshers", "Data Engineer Fresher"),
    ("https://www.freshersworld.com/jobs/python-developer-jobs/freshers", "Python Developer Fresher"),
    ("https://www.freshersworld.com/walkin-jobs/walkin-jobs-for-it-fresher", "Walk-in IT Fresher"),
]

LINKEDIN_JOBS_URLS = [
    ("https://www.linkedin.com/jobs/search/?keywords=data+engineer+fresher&location=Pune%2C+Maharashtra&f_E=1&f_TPR=r604800", "Data Engineer Fresher Pune"),
    ("https://www.linkedin.com/jobs/search/?keywords=python+developer+fresher&location=Pune%2C+Maharashtra&f_E=1&f_TPR=r604800", "Python Developer Fresher Pune"),
    ("https://www.linkedin.com/jobs/search/?keywords=walk+in+drive+engineer&location=Pune%2C+Maharashtra&f_TPR=r86400", "Walk-in Drive Pune"),
    ("https://www.linkedin.com/jobs/search/?keywords=data+engineer&location=Hyderabad%2C+Telangana&f_E=1&f_TPR=r604800", "Data Engineer Hyderabad"),
    ("https://www.linkedin.com/jobs/search/?keywords=software+engineer+intern&location=Bangalore%2C+Karnataka&f_E=1&f_TPR=r604800", "Software Engineer Intern Bangalore"),
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}


class DirectJobBoardSource(BaseSource):
    """
    Scrapes Indian job portals directly for walk-in drives and fresher openings.
    Much more reliable than DuckDuckGo for finding walk-in drives in Pune.
    """

    def __init__(self):
        super().__init__("direct_job_boards")

    def search(self, queries: list[str], **kwargs) -> list[RawJobResult]:
        results: list[RawJobResult] = []
        seen_urls: set[str] = set()

        self.logger.info("[bold]== Direct Job Board Scraping ===[/]")

        for url, label in NAUKRI_WALKIN_URLS:
            self.logger.info(f"  Naukri Walk-in: {label}")
            self._fetch_naukri(url, f"walkin_{label}", results, seen_urls)
            time.sleep(2)

        for url, label in NAUKRI_FRESHER_URLS:
            self.logger.info(f"  Naukri Fresher: {label}")
            self._fetch_naukri(url, f"fresher_{label}", results, seen_urls)
            time.sleep(2)

        for url, label in SHINE_WALKIN_URLS:
            self.logger.info(f"  Shine: {label}")
            self._fetch_generic(url, "shine", label, results, seen_urls)
            time.sleep(2)

        for url, label in FRESHERSWORLD_URLS:
            self.logger.info(f"  Freshersworld: {label}")
            self._fetch_generic(url, "freshersworld", label, results, seen_urls)
            time.sleep(2)

        for url, label in LINKEDIN_JOBS_URLS:
            self.logger.info(f"  LinkedIn Jobs: {label}")
            self._fetch_linkedin(url, label, results, seen_urls)
            time.sleep(3)

        self.logger.info(f"Direct boards found [bold]{len(results)}[/] raw results")
        return results

    def _fetch_naukri(self, url: str, label: str, results: list, seen_urls: set) -> None:
        try:
            with httpx.Client(timeout=20.0, follow_redirects=True, headers=HEADERS) as client:
                resp = client.get(url)
                if resp.status_code != 200:
                    return
            soup = BeautifulSoup(resp.text, "html.parser")

            # Try __NEXT_DATA__ JSON
            nd = soup.find("script", id="__NEXT_DATA__")
            if nd and nd.string:
                try:
                    jobs = self._parse_naukri_next(json.loads(nd.string))
                    for j in jobs:
                        if j["url"] not in seen_urls and not is_senior_title(j["title"]):
                            seen_urls.add(j["url"])
                            results.append(self._make_result(
                                source=f"naukri_{label}",
                                url=j["url"], title=j["title"],
                                company=j.get("company", ""),
                                location=j.get("location", ""),
                                experience=j.get("experience", "0-1 years"),
                                snippet=j.get("snippet", ""),
                            ))
                    if jobs:
                        return
                except Exception:
                    pass

            # HTML fallback
            for card in soup.select("article.jobTuple, div.srp-jobtuple-wrapper, div[class*='tuple']")[:20]:
                try:
                    a = card.select_one("a.title, a[class*='title'], h2 a")
                    if not a:
                        continue
                    title = a.get_text(strip=True)
                    href = a.get("href", "")
                    job_url = href if href.startswith("http") else f"https://www.naukri.com{href}"
                    if not title or job_url in seen_urls or is_senior_title(title):
                        continue
                    company = (card.select_one("a[class*='comp'], a.subTitle") or type("", (), {"get_text": lambda *a, **kw: ""})()).get_text(strip=True)
                    location = (card.select_one("span[class*='loc'], li[class*='location']") or type("", (), {"get_text": lambda *a, **kw: ""})()).get_text(strip=True)
                    seen_urls.add(job_url)
                    results.append(self._make_result(
                        source=f"naukri_{label}", url=job_url, title=title,
                        company=company, location=location, experience="0-1 years",
                    ))
                except Exception:
                    continue
        except Exception as e:
            self.logger.warning(f"Naukri fetch error ({label}): {e}")

    def _parse_naukri_next(self, data: dict) -> list[dict]:
        jobs = []
        try:
            pp = data.get("props", {}).get("pageProps", {})
            job_list = (pp.get("jobs") or pp.get("jobData", {}).get("jobDetails") or [])
            if isinstance(job_list, dict):
                job_list = list(job_list.values())
            for item in (job_list or []):
                if not isinstance(item, dict):
                    continue
                title = (item.get("title") or item.get("jobTitle") or "").strip()
                company = (item.get("companyName") or item.get("company") or "").strip()
                placeholders = item.get("placeholders") or []
                location = placeholders[0].get("label", "") if len(placeholders) > 0 else ""
                exp = placeholders[1].get("label", "0-1 years") if len(placeholders) > 1 else "0-1 years"
                if extract_years(exp) and extract_years(exp) > 1:
                    continue  # Skip experienced jobs!
                job_url = item.get("jdURL") or item.get("url") or ""
                if job_url and not job_url.startswith("http"):
                    job_url = f"https://www.naukri.com{job_url}"
                if title and job_url:
                    jobs.append({"title": title, "company": company, "location": location, "experience": exp, "url": job_url, "snippet": (item.get("jobDescription") or "")[:300]})
        except Exception:
            pass
        return jobs

    def _fetch_linkedin(self, url: str, label: str, results: list, seen_urls: set) -> None:
        try:
            with httpx.Client(timeout=20.0, follow_redirects=True, headers={**HEADERS, "Accept-Language": "en-US,en;q=0.9"}) as client:
                resp = client.get(url)
                if resp.status_code not in (200,):
                    return
            soup = BeautifulSoup(resp.text, "html.parser")

            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    d = json.loads(script.string or "")
                    items = d.get("itemListElement", [d]) if d.get("@type") == "ItemList" else [d]
                    for it in items:
                        j = it.get("item", it)
                        title = j.get("title", "")
                        company = (j.get("hiringOrganization") or {}).get("name", "")
                        job_url = j.get("url", "")
                        location = ((j.get("jobLocation") or {}).get("address") or {}).get("addressLocality", "")
                        if title and job_url and job_url not in seen_urls and not is_senior_title(title):
                            seen_urls.add(job_url)
                            results.append(self._make_result(source=f"linkedin_jobs_{label}", url=job_url, title=title, company=company, location=location))
                except Exception:
                    continue

            import re as _re
            for card in soup.select("ul.jobs-search__results-list li, div.base-card, div[class*='job-search-card']")[:25]:
                try:
                    a = card.select_one("a.base-card__full-link, a[class*='job-card'], h3 a, h4 a")
                    if not a:
                        continue
                    title = a.get_text(strip=True)
                    href = a.get("href", "").split("?")[0]
                    if not href or href in seen_urls or is_senior_title(title):
                        continue

                    # Check title slug for senior indicators
                    slug = href.split('/jobs/view/')[-1].split('?')[0]
                    title_slug = slug.split('-at-')[0].replace('-', ' ')
                    if is_senior_title(title_slug):
                        continue

                    company_el = card.select_one("h4.base-search-card__subtitle, h4, a[data-tracking-control-name*='company']")
                    company = company_el.get_text(strip=True) if company_el else ""
                    if not company and "-at-" in href:
                        m_slug = _re.search(r"-at-([a-zA-Z0-9\-]+)-\d+", href)
                        if m_slug:
                            company = m_slug.group(1).replace("-", " ").title()

                    loc_el = card.select_one("span.job-search-card__location, span[class*='location']")
                    location = loc_el.get_text(strip=True) if loc_el else ""

                    # Inspect job detail page to verify experience and seniority
                    exp_str = "0-1 years"
                    try:
                        job_resp = client.get(href, timeout=8.0)
                        if job_resp.status_code == 200:
                            job_html = job_resp.text

                            # 1. Seniority level check (Mid-Senior, Director, Executive -> REJECT)
                            m_sen = _re.search(r'Seniority\s*level\s*</h3>\s*<span[^>]*>\s*([^<]+)\s*</span>', job_html, _re.IGNORECASE)
                            seniority = m_sen.group(1).strip() if m_sen else ""
                            if seniority.lower() in ["mid-senior level", "director", "executive"]:
                                continue

                            # 2. Description text experience check
                            clean_desc = _re.sub(r'<[^>]+>', ' ', job_html)
                            exp_match = _re.search(r'(?:exp(?:erience)?|exp)\s*[-:]?\s*([2-9]|\d{2,})\s*\+?\s*years?', clean_desc, _re.IGNORECASE)
                            if not exp_match:
                                exp_match = _re.search(r'([2-9]|\d{2,})\s*[-–to]+\s*\d*\s*years?(?:\s*of)?\s*(?:relevant\s*)?experience', clean_desc, _re.IGNORECASE)
                            if not exp_match:
                                exp_match = _re.search(r'minimum\s*([2-9]|\d{2,})\s*years?', clean_desc, _re.IGNORECASE)
                            if not exp_match:
                                exp_match = _re.search(r'([2-9]|\d{2,})\s*years?\s*of\s*experience', clean_desc, _re.IGNORECASE)

                            if exp_match:
                                continue  # Reject! Explicitly requires 2+, 3+, 5+ years!

                            # 3. Company fallback
                            if not company or len(company) <= 2:
                                m_top = _re.search(r'class="topcard__org-name-link[^"]*"[^>]*>\s*([^<]+)\s*<', job_html)
                                if not m_top:
                                    m_top = _re.search(r'"hiringOrganization":\s*\{[^}]*"name":\s*"([^"]+)"', job_html)
                                if m_top:
                                    company = m_top.group(1).strip()

                            # 4. Set accurate experience
                            if seniority.lower() == "internship":
                                exp_str = "Internship (0 years)"
                            elif seniority.lower() == "entry level":
                                exp_str = "0-1 years"
                            elif any(kw in clean_desc.lower() for kw in ["fresher", "intern", "trainee", "campus", "entry level", "entry-level"]):
                                exp_str = "0-1 years"
                            elif seniority.lower() == "associate":
                                exp_str = "0-1 years"
                            else:
                                continue
                    except Exception:
                        if not any(k in title.lower() for k in ["intern", "fresher", "trainee", "entry level"]):
                            continue

                    seen_urls.add(href)
                    results.append(self._make_result(
                        source="linkedin_jobs", url=href, title=title,
                        company=company, location=location, experience=exp_str,
                    ))
                except Exception:
                    continue
        except Exception as e:
            self.logger.warning(f"LinkedIn Jobs fetch error ({label}): {e}")

    def _fetch_generic(self, url: str, source_name: str, label: str, results: list, seen_urls: set) -> None:
        try:
            with httpx.Client(timeout=20.0, follow_redirects=True, headers=HEADERS) as client:
                resp = client.get(url)
                if resp.status_code != 200:
                    return
            soup = BeautifulSoup(resp.text, "html.parser")

            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    d = json.loads(script.string or "")
                    if d.get("@type") == "JobPosting":
                        title = d.get("title", "")
                        company = (d.get("hiringOrganization") or {}).get("name", "")
                        job_url = d.get("url", url)
                        location = ((d.get("jobLocation") or {}).get("address") or {}).get("addressLocality", "")
                        if title and job_url not in seen_urls and not is_senior_title(title):
                            seen_urls.add(job_url)
                            results.append(self._make_result(source=source_name, url=job_url, title=title, company=company, location=location))
                except Exception:
                    continue

            job_kw = ["engineer", "developer", "intern", "analyst", "walk in", "walkin", "python", "data", "ai", "ml", "fresher", "associate"]
            for a in soup.find_all("a", href=True):
                text = a.get_text(strip=True)
                if len(text) < 5 or len(text) > 120:
                    continue
                if not any(kw in text.lower() for kw in job_kw):
                    continue
                href = a["href"]
                job_url = href if href.startswith("http") else urljoin(url, href)
                if job_url in seen_urls or job_url == url or is_senior_title(text):
                    continue
                seen_urls.add(job_url)
                results.append(self._make_result(source=source_name, url=job_url, title=text, company="", location="", snippet=label))
        except Exception as e:
            self.logger.warning(f"{source_name} fetch error ({label}): {e}")

    def _make_result(self, source: str, url: str, title: str, company: str = "", location: str = "", experience: str = "0-1 years", snippet: str = "") -> RawJobResult:
        return RawJobResult(
            source=source,
            source_type=SourceType.WEB_SEARCH,
            url=url,
            title=title,
            company=company,
            location=location,
            experience=experience,
            snippet=snippet or f"{company} | {location}",
            raw_content=(
                f"[{source.upper()}]\n"
                f"Company: {company}\n"
                f"Title: {title}\n"
                f"Location: {location}\n"
                f"Experience: {experience}\n"
                f"URL: {url}"
            ),
        )