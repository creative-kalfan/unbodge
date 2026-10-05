"""OpenTelemetry-compatible instrumentation (Phase 4).

System-level spans in OTel shape (trace/span ids, attributes, timing).
Without the OTel SDK installed this is a pure-local implementation over
the existing tracer -- observability is never a hard dependency for
correctness. LangSmith remains the model-trace backend (Phase 3).
"""

from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from typing import Iterator

from tracing.base import Tracer


class OtelTracer:
    """OTel-shaped spans recorded into any ``Tracer`` sink."""

    def __init__(self, sink: Tracer, *, service: str = "unbodge") -> None:
        self._sink = sink
        self._service = service

    @property
    def service(self) -> str:
        return self._service

    @contextmanager
    def span(
        self, name: str, trace_id: str | None = None, **attributes: str
    ) -> Iterator[dict[str, str]]:
        from tracing.base import TraceEvent

        trace = trace_id or uuid.uuid4().hex
        span_id = uuid.uuid4().hex[:16]
        started = time.perf_counter()
        collected: dict[str, str] = dict(attributes)
        try:
            yield collected
        finally:
            duration_ms = (time.perf_counter() - started) * 1000.0
            self._sink.record(
                TraceEvent(
                    trace_id=trace,
                    name=f"otel.{name}",
                    attributes={
                        "span_id": span_id,
                        "service": self._service,
                        "duration_ms": f"{duration_ms:.3f}",
                        **collected,
                    },
                )
            )

    @staticmethod
    def sdk_available() -> bool:
        try:
            import opentelemetry.trace  # noqa: F401
        except ImportError:
            return False
        return True


__all__ = ["OtelTracer"]
