"""Local (offline) trace sink (Phase 3). Always available, deterministic."""

from __future__ import annotations

from tracing.base import TraceEvent, Tracer


class LocalTracer(Tracer):
    def __init__(self) -> None:
        self._events: list[TraceEvent] = []

    def record(self, event: TraceEvent) -> None:
        self._events.append(event)

    def events(self) -> list[TraceEvent]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()


__all__ = ["LocalTracer"]
