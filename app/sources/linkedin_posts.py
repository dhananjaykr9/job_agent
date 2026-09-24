"""
LinkedIn Posts source adapter.

Discovers hiring-related LinkedIn posts by searching Google for
`site:linkedin.com/posts` or `site:linkedin.com/feed` with
hiring keywords. This catches informal hiring posts that never
appear on formal job boards.
"""
from __future__ import annotations

import httpx
from bs4 import BeautifulSoup
from duckduckgo_search import DDGS

from .base import BaseSource
from ..schemas import RawJobResult, SourceType


class LinkedInPostsSource(BaseSource):
    """Discover jobs from LinkedIn hiring posts via DuckDuckGo search (free, no API key)."""

    def __init__(self):
        super().__init__("linkedin_posts")

    def search(self, queries: list[str], **kwargs) -> list[RawJobResult]:
        results: list[RawJobResult] = []
        seen_urls: set[str] = set()

        for keyword in queries:
            try:
                # Search for LinkedIn posts containing hiring keywords
                query = f"site:linkedin.com/posts OR site:linkedin.com/feed {keyword}"
                self.logger.info(f"LinkedIn Posts: [bold]{keyword}[/]")

                with DDGS() as ddgs:
                    organic_results = list(
                        ddgs.text(
                            query,
                            region="in-en",
                            max_results=15,
                        )
                    )

                for item in organic_results:
                    url = item.get("href", "")
                    if not url or url in seen_urls:
                        continue
                    if "linkedin.com" not in url.lower():
                        continue

                    seen_urls.add(url)

                    raw_content = (
                        f"{item.get('title', '')}\n"
                        f"{item.get('body', '')}"
                    )

                    # Try to fetch fuller content
                    page_content = self._fetch_linkedin_post(url)
                    if page_content:
                        raw_content = page_content

                    results.append(
                        RawJobResult(
                            source="linkedin",
                            source_type=SourceType.LINKEDIN_POST,
                            url=url,
                            title=item.get("title", ""),
                            snippet=item.get("body", ""),
                            raw_content=raw_content,
                        )
                    )

            except Exception as e:
                self.logger.warning(f"LinkedIn keyword failed: {keyword} — {e}")
                continue

        return results

    def _fetch_linkedin_post(self, url: str) -> str:
        """
        Attempt to fetch LinkedIn post content.

        LinkedIn is heavily JS-rendered, so we get limited content.
        The Google snippet + title is often sufficient for LLM extraction.
        """
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

                # LinkedIn public post content is often in meta tags
                content_parts = []

                # og:description often has the post text
                og_desc = soup.find("meta", property="og:description")
                if og_desc and og_desc.get("content"):
                    content_parts.append(og_desc["content"])

                # og:title has the poster's name
                og_title = soup.find("meta", property="og:title")
                if og_title and og_title.get("content"):
                    content_parts.insert(0, f"Posted by: {og_title['content']}")

                # Try main content area
                for selector in [
                    ".feed-shared-update-v2__description",
                    ".update-components-text",
                    "article",
                    ".core-rail",
                ]:
                    el = soup.select_one(selector)
                    if el:
                        content_parts.append(el.get_text(strip=True))
                        break

                return "\n".join(content_parts)[:6000] if content_parts else ""

        except Exception:
            return ""
