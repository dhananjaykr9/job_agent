"""
Base class for all source adapters.

Every source (web search, LinkedIn posts, company careers, etc.)
inherits from BaseSource and implements the `search()` method,
returning a list of RawJobResult objects.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..schemas import RawJobResult
from ..utils.logger import get_logger


class BaseSource(ABC):
    """Abstract base for source adapters."""

    def __init__(self, name: str):
        self.name = name
        self.logger = get_logger(f"job_agent.source.{name}")

    @abstractmethod
    def search(self, queries: list[str], **kwargs) -> list[RawJobResult]:
        """
        Run discovery for the given queries.

        Args:
            queries: Search strings to use.

        Returns:
            List of raw results to be processed by the extraction agent.
        """
        ...

    def _safe_search(self, queries: list[str], **kwargs) -> list[RawJobResult]:
        """
        Wrapper that isolates source failures.
        If this source crashes, the pipeline continues with other sources.
        """
        try:
            results = self.search(queries, **kwargs)
            self.logger.info(
                f"[source]{self.name}[/] returned [bold]{len(results)}[/] results"
            )
            return results
        except Exception as e:
            self.logger.error(f"[error]{self.name} failed:[/] {e}")
            return []
