"""Tracing: local sink always, LangSmith strictly optional (Phase 3)."""

from tracing.base import TraceEvent, Tracer
from tracing.langsmith import DEFAULT_ENDPOINT, FlushReport, LangSmithTracer
from tracing.local import LocalTracer
from tracing.otel import OtelTracer

__all__ = [
    "DEFAULT_ENDPOINT",
    "FlushReport",
    "LangSmithTracer",
    "LocalTracer",
    "OtelTracer",
    "TraceEvent",
    "Tracer",
]
