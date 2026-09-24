"""
Company Career Page source adapter — EXPANDED.

Three discovery strategies:
1. Scrape pre-configured company career pages (90+ companies)
2. Dynamically discover NEW companies via Google search
   ("top startups Pune hiring", "funded startups Hyderabad", etc.)
3. Walk-in drive discovery across all IT hubs

This ensures we're not limited to a fixed list — the agent
finds companies it has never seen before.
"""
from __future__ import annotations

import re
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from duckduckgo_search import DDGS

from .base import BaseSource
from ..schemas import RawJobResult, SourceType


class CompanyCareersSource(BaseSource):
    """
    Discover jobs directly from company career pages.

    Combines static targets + dynamic internet-wide discovery
    to find startups, midcaps, and walk-in drives across
    Pune, Hyderabad, and Bangalore.
    """

    def __init__(self):
        super().__init__("company_careers")

    def search(
        self,
        queries: list[str],
        *,
        target_companies: list[dict] | None = None,
        discovery_queries: list[str] | None = None,
        walkin_queries: list[str] | None = None,
        **kwargs,
    ) -> list[RawJobResult]:
        """
        Three-pronged company discovery:
        1. Configured career page scraping
        2. Dynamic company/career page discovery via Google
        3. Walk-in drive specific search
        """
        results: list[RawJobResult] = []
        seen_urls: set[str] = set()

        # ── Strategy 1: Direct career page scraping ─────
        if target_companies:
            self.logger.info(
                f"Scraping [bold]{len(target_companies)}[/] configured career pages..."
            )
            for company in target_companies:
                name = company.get("name", "")
                career_url = company.get("career_url", "")
                if not career_url:
                    continue

                self.logger.info(f"  → {name}")
                page_results = self._scrape_career_page(name, career_url)
                for r in page_results:
                    if r.url not in seen_urls:
                        seen_urls.add(r.url)
                        results.append(r)

        # ── Strategy 2: Dynamic company discovery ───────
        all_discovery_queries = list(queries or [])
        if discovery_queries:
            all_discovery_queries.extend(discovery_queries)

        if all_discovery_queries:
            self.logger.info(
                f"Dynamic discovery with [bold]{len(all_discovery_queries)}[/] queries..."
            )
            for query in all_discovery_queries:
                discovered = self._discover_companies_from_search(query, seen_urls)
                for r in discovered:
                    if r.url not in seen_urls:
                        seen_urls.add(r.url)
                        results.append(r)

        # ── Strategy 3: Walk-in drive discovery ─────────
        if walkin_queries:
            self.logger.info(
                f"Walk-in drive search with [bold]{len(walkin_queries)}[/] queries..."
            )
            for query in walkin_queries:
                walkin_results = self._search_walkin_drives(query, seen_urls)
                for r in walkin_results:
                    if r.url not in seen_urls:
                        seen_urls.add(r.url)
                        results.append(r)

        return results

    # ═══════════════════════════════════════════════════
    # Strategy 2: Dynamic company discovery
    # ═══════════════════════════════════════════════════
    def _discover_companies_from_search(
        self, query: str, seen_urls: set[str]
    ) -> list[RawJobResult]:
        """
        Search broadly for companies/career pages via DuckDuckGo.
        NOT restricted to specific sites — targets the whole internet (100% free).
        """
        results: list[RawJobResult] = []

        try:
            self.logger.info(f"Discovery: [bold]{query}[/]")

            with DDGS() as ddgs:
                search_results = list(
                    ddgs.text(
                        query,
                        region="in-en",
                        max_results=20,
                    )
                )

            for item in search_results:
                url = item.get("href", "")
                if not url or url in seen_urls:
                    continue

                # Skip aggregators — we want direct company pages
                if self._is_aggregator(url):
                    continue

                seen_urls.add(url)

                search_meta = {"title": item.get("title", ""), "snippet": item.get("body", "")}
                is_career_page = self._looks_like_career_page(url, search_meta)

                if is_career_page:
                    # Try to scrape it for individual job listings
                    company_name = self._extract_company_from_url(url)
                    page_results = self._scrape_career_page(
                        company_name, url, max_jobs=10
                    )
                    results.extend(page_results)
                else:
                    # Treat as a potential job result
                    results.append(
                        RawJobResult(
                            source="career_discovery",
                            source_type=SourceType.COMPANY_CAREER,
                            url=url,
                            title=item.get("title", ""),
                            snippet=item.get("body", ""),
                            raw_content=f"{item.get('title', '')}\n{item.get('body', '')}",
                        )
                    )

        except Exception as e:
            self.logger.warning(f"Discovery query failed: {query} — {e}")

        return results

    # ═══════════════════════════════════════════════════
    # Strategy 3: Walk-in drive search
    # ═══════════════════════════════════════════════════
    def _search_walkin_drives(
        self, query: str, seen_urls: set[str]
    ) -> list[RawJobResult]:
        """
        Search for walk-in drives and hiring events via DuckDuckGo.
        Searches the entire internet, not restricted to any specific site.
        """
        results: list[RawJobResult] = []

        try:
            self.logger.info(f"Walk-in search: [bold]{query}[/]")

            with DDGS() as ddgs:
                text_results = list(
                    ddgs.text(
                        query,
                        region="in-en",
                        max_results=15,
                    )
                )

            for item in text_results:
                url = item.get("href", "")
                if not url or url in seen_urls:
                    continue

                seen_urls.add(url)
                title = item.get("title", "")
                snippet = item.get("body", "")

                # Fetch more content for walk-in pages
                page_content = self._fetch_page_text(url)
                raw_content = (
                    f"[WALK-IN DRIVE]\n"
                    f"Title: {title}\n"
                    f"Snippet: {snippet}\n"
                )
                if page_content:
                    raw_content += f"\nPage Content:\n{page_content}"

                results.append(
                    RawJobResult(
                        source="walkin_drive",
                        source_type=SourceType.WEB_SEARCH,
                        url=url,
                        title=title,
                        snippet=snippet,
                        raw_content=raw_content,
                    )
                )

            # Also check news for recent walk-ins
            try:
                with DDGS() as ddgs:
                    news_results = list(
                        ddgs.news(
                            query,
                            region="in-en",
                            max_results=10,
                        )
                    )
                for item in news_results:
                    url = item.get("url", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)
                    title = item.get("title", "")
                    snippet = item.get("body", "")
                    results.append(
                        RawJobResult(
                            source="walkin_drive_news",
                            source_type=SourceType.WEB_SEARCH,
                            url=url,
                            title=title,
                            snippet=snippet,
                            raw_content=(
                                f"[WALK-IN DRIVE NEWS]\n"
                                f"Title: {title}\n"
                                f"Date: {item.get('date', '')}\n"
                                f"Snippet: {snippet}\n"
                            ),
                        )
                    )
            except Exception:
                pass

        except Exception as e:
            self.logger.warning(f"Walk-in search failed: {query} — {e}")

        return results

    # ═══════════════════════════════════════════════════
    # Career page scraping
    # ═══════════════════════════════════════════════════
    def _scrape_career_page(
        self, company_name: str, career_url: str, max_jobs: int = 20
    ) -> list[RawJobResult]:
        """Scrape a company's career page for individual job listings."""
        results: list[RawJobResult] = []

        try:
            with httpx.Client(
                timeout=15.0,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                },
            ) as client:
                resp = client.get(career_url)
                resp.raise_for_status()

                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer"]):
                    tag.decompose()

                # ── Find job listing links ──────────────
                job_links = self._extract_job_links(soup, career_url)

                for link_url, link_text in job_links[:max_jobs]:
                    raw_content = (
                        f"Company: {company_name}\n"
                        f"Title: {link_text}\n"
                        f"Source: {career_url}\n"
                    )

                    # Try to fetch individual job page
                    try:
                        job_resp = client.get(link_url)
                        if job_resp.status_code == 200:
                            job_soup = BeautifulSoup(job_resp.text, "html.parser")
                            for t in job_soup(["script", "style", "nav", "footer"]):
                                t.decompose()
                            page_text = job_soup.get_text(separator="\n", strip=True)
                            raw_content += f"\n{page_text[:6000]}"
                    except Exception:
                        pass

                    results.append(
                        RawJobResult(
                            source=company_name,
                            source_type=SourceType.COMPANY_CAREER,
                            url=link_url,
                            title=link_text,
                            raw_content=raw_content,
                        )
                    )

                # If no links found, treat the whole page as one result
                if not job_links:
                    page_text = soup.get_text(separator="\n", strip=True)
                    if len(page_text) > 100:  # Skip empty pages
                        results.append(
                            RawJobResult(
                                source=company_name,
                                source_type=SourceType.COMPANY_CAREER,
                                url=career_url,
                                title=f"{company_name} Careers",
                                raw_content=f"Company: {company_name}\n{page_text[:6000]}",
                            )
                        )

        except Exception as e:
            self.logger.warning(f"Failed to scrape {career_url}: {e}")

        return results

    # ═══════════════════════════════════════════════════
    # Helper methods
    # ═══════════════════════════════════════════════════
    def _extract_job_links(
        self, soup: BeautifulSoup, base_url: str
    ) -> list[tuple[str, str]]:
        """Extract links that look like individual job postings."""
        job_links = []
        job_keywords = [
            "engineer",
            "developer",
            "analyst",
            "intern",
            "associate",
            "junior",
            "data",
            "python",
            "sql",
            "ml",
            "ai",
            "software",
            "backend",
            "etl",
            "devops",
            "cloud",
            "platform",
            "fresher",
            "sde",
            "swe",
            "full stack",
            "frontend",
        ]

        for link in soup.find_all("a", href=True):
            href = link["href"]
            text = link.get_text(strip=True).lower()

            is_job_link = any(kw in text for kw in job_keywords) or any(
                kw in href.lower()
                for kw in [
                    "/job/",
                    "/position/",
                    "/opening/",
                    "/apply/",
                    "/role/",
                    "/vacancy/",
                    "/requisition/",
                    "jobid=",
                    "job_id=",
                ]
            )

            if is_job_link and len(text) > 3:
                absolute_url = urljoin(base_url, href)
                job_links.append((absolute_url, link.get_text(strip=True)))

        return job_links[:30]

    def _is_aggregator(self, url: str) -> bool:
        """Check if URL belongs to a job aggregator (skip these)."""
        aggregators = [
            "linkedin.com",
            "naukri.com",
            "indeed.com",
            "glassdoor.com",
            "ambitionbox.com",
            "shine.com",
            "timesjobs.com",
            "monster.com",
            "foundit.in",
            "instahyre.com",
            "hirist.com",
            "cutshort.io",
            "angellist.com",
            "wellfound.com",
            "wikipedia.org",
            "youtube.com",
            "facebook.com",
            "twitter.com",
            "quora.com",
            "reddit.com",
        ]
        url_lower = url.lower()
        return any(agg in url_lower for agg in aggregators)

    def _looks_like_career_page(self, url: str, search_result: dict) -> bool:
        """Heuristic: does this URL look like a company career page?"""
        url_lower = url.lower()
        title = search_result.get("title", "").lower()
        snippet = search_result.get("snippet", "").lower()

        career_signals = [
            "/careers",
            "/jobs",
            "/openings",
            "/hiring",
            "/join-us",
            "/work-with-us",
            "/opportunities",
            "/vacancies",
            "career",
        ]

        url_match = any(sig in url_lower for sig in career_signals)
        text_match = any(
            kw in title or kw in snippet
            for kw in ["careers", "we're hiring", "join our team", "open positions"]
        )

        return url_match or text_match

    def _extract_company_from_url(self, url: str) -> str:
        """Try to extract a company name from the URL domain."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.replace("www.", "")
            # Take the main part before .com/.in etc.
            parts = domain.split(".")
            if parts:
                name = parts[0].replace("-", " ").replace("_", " ").title()
                return name
        except Exception:
            pass
        return "Unknown"

    def _fetch_page_text(self, url: str) -> str:
        """Fetch and extract text from a URL."""
        try:
            with httpx.Client(
                timeout=10.0,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                },
            ) as client:
                resp = client.get(url)
                if resp.status_code != 200:
                    return ""
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()
                return soup.get_text(separator="\n", strip=True)[:6000]
        except Exception:
            return ""
