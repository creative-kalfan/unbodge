"""Tracing contracts (Phase 3).

Every event is recorded locally first. A LangSmith backend may mirror
events remotely, but the core proof loop never requires it: without
credentials the tracer degrades to the local sink with ``enabled=False``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import datetime
from typing import Iterator
from domain.models import UnbodgeModel, utcnow
from pydantic import Field


class TraceEvent(UnbodgeModel):
    trace_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    attributes: dict[str, str] = Field(default_factory=dict)
    at: datetime = Field(default_factory=utcnow)


class Tracer(ABC):
    """Trace sink interface (workflow, reasoning, research, tools, runs)."""

    @abstractmethod
    def record(self, event: TraceEvent) -> None:
        ...

    @abstractmethod
    def events(self) -> list[TraceEvent]:
        ...

    @contextmanager
    def span(self, trace_id: str, name: str, **attributes: str) -> Iterator[dict[str, str]]:
        collected: dict[str, str] = dict(attributes)
        try:
            yield collected
        finally:
            self.record(TraceEvent(trace_id=trace_id, name=name, attributes=collected))


__all__ = ["TraceEvent", "Tracer"]
