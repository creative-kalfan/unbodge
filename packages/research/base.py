"""Research provider interface + implementations (Phase 3)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from research.models import ResearchBundle, ResearchQuery


class ResearchProvider(ABC):
    """Stable research interface (issue/release/docs discovery)."""

    @abstractmethod
    def search(self, query: ResearchQuery) -> ResearchBundle:
        """Run one research query; never fabricate results."""
        ...


__all__ = ["ResearchProvider"]
