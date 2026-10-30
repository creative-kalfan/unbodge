"""Tracing: local sink always, LangSmith strictly optional (Phase 3)."""

import os

from tracing.base import TraceEvent, Tracer
from tracing.langsmith import DEFAULT_ENDPOINT, FlushReport, LangSmithTracer
from tracing.local import LocalTracer
from tracing.otel import OtelTracer


def get_default_tracer() -> Tracer:
    """Return a configured tracer based on environment.

    Defaults to LocalTracer unless LANGSMITH_API_KEY is explicitly set.
    """
    if os.environ.get("LANGSMITH_API_KEY"):
        return LangSmithTracer()
    return LocalTracer()


__all__ = [
    "DEFAULT_ENDPOINT",
    "FlushReport",
    "LangSmithTracer",
    "LocalTracer",
    "OtelTracer",
    "TraceEvent",
    "Tracer",
    "get_default_tracer",
]
