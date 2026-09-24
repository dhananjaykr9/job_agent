"""
Web Search source adapter using DuckDuckGo (FREE, no API key).

Sends configured search queries to DuckDuckGo and collects
results that look like job listings. Also uses the news
search for time-sensitive results like walk-in drives.
"""
from __future__ import annotations

import httpx
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

from .base import BaseSource
from ..schemas import RawJobResult, SourceType


class WebSearchSource(BaseSource):
    """Discover jobs through DuckDuckGo search (free, unlimited)."""

    def __init__(self):
        super().__init__("web_search")

    def search(self, queries: list[str], **kwargs) -> list[RawJobResult]:
        results: list[RawJobResult] = []
        seen_urls: set[str] = set()

        for query in queries:
            try:
                self.logger.info(f"Searching: [bold]{query}[/]")

                # ── Text search ─────────────────────────
                with DDGS() as ddgs:
                    text_results = list(
                        ddgs.text(
                            query,
                            region="in-en",  # India
                            max_results=15,
                        )
                    )

                for item in text_results:
                    url = item.get("href", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)

                    results.append(
                        RawJobResult(
                            source="duckduckgo",
                            source_type=self._classify_url(url),
                            url=url,
                            title=item.get("title", ""),
                            snippet=item.get("body", ""),
                            raw_content=f"{item.get('title', '')}\n{item.get('body', '')}",
                        )
                    )

                # ── News search (catches recent walk-ins & drives) ──
                if any(
                    kw in query.lower()
                    for kw in ["walk in", "walkin", "drive", "hiring", "fresher"]
                ):
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

                            results.append(
                                RawJobResult(
                                    source="duckduckgo_news",
                                    source_type=self._classify_url(url),
                                    url=url,
                                    title=item.get("title", ""),
                                    snippet=item.get("body", ""),
                                    raw_content=(
                                        f"[NEWS] {item.get('title', '')}\n"
                                        f"{item.get('body', '')}\n"
                                        f"Date: {item.get('date', '')}"
                                    ),
                                )
                            )
                    except Exception:
                        pass  # News search is optional

            except Exception as e:
                self.logger.warning(f"Query failed: {query} — {e}")
                continue

        return results

    def _classify_url(self, url: str) -> SourceType:
        """Classify the source type based on the URL domain."""
        url_lower = url.lower()
        if "linkedin.com/jobs" in url_lower:
            return SourceType.LINKEDIN_JOB
        if "linkedin.com" in url_lower:
            return SourceType.LINKEDIN_POST
        if "naukri.com" in url_lower:
            return SourceType.NAUKRI
        if "indeed.com" in url_lower:
            return SourceType.INDEED
        if "wellfound.com" in url_lower or "angel.co" in url_lower:
            return SourceType.WELLFOUND
        if any(kw in url_lower for kw in ["/careers", "/jobs", "/openings", "/hiring"]):
            return SourceType.COMPANY_CAREER
        return SourceType.WEB_SEARCH

    def fetch_page_content(self, url: str, timeout: float = 15.0) -> str:
        """
        Fetch the full text of a job page for LLM extraction.
        Falls back gracefully on timeouts / blocked pages.
        """
        try:
            with httpx.Client(
                timeout=timeout,
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
                resp.raise_for_status()

                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer", "header"]):
                    tag.decompose()

                text = soup.get_text(separator="\n", strip=True)
                return text[:8000]

        except Exception as e:
            self.logger.warning(f"Failed to fetch {url}: {e}")
            return ""
