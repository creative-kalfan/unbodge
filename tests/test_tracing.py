"""Tracing: local-first, LangSmith optional and never on the hot path."""

import io

import pytest

from tracing import LangSmithTracer, LocalTracer, TraceEvent, Tracer


def test_local_tracer_records_and_spans():
    tracer = LocalTracer()
    assert isinstance(tracer, Tracer)
    tracer.record(TraceEvent(trace_id="t1", name="workflow.start"))
    with tracer.span("t1", "policy.decision", outcome="ABSTAIN") as attrs:
        attrs["extra"] = "x"
    events = tracer.events()
    assert [e.name for e in events] == ["workflow.start", "policy.decision"]
    assert events[1].attributes["outcome"] == "ABSTAIN"
    tracer.clear()
    assert tracer.events() == []


def test_span_records_on_exception():
    tracer = LocalTracer()
    with pytest.raises(RuntimeError):
        with tracer.span("t9", "sandbox.run"):
            raise RuntimeError("boom")
    assert [e.name for e in tracer.events()] == ["sandbox.run"]


def test_langsmith_disabled_without_credentials():
    tracer = LangSmithTracer(api_key="")
    assert isinstance(tracer, Tracer)
    assert not tracer.enabled
    assert tracer.project == "unbodge-history-v1"
    tracer.record(TraceEvent(trace_id="t", name="reasoning.call"))
    assert len(tracer.events()) == 1  # buffered locally, nothing sent
    report = tracer.flush()
    assert report.sent == 0 and report.error


def test_langsmith_flush_reports_failure_without_raising():
    def opener(request, timeout):
        raise OSError("network down")

    tracer = LangSmithTracer(api_key="k", opener=opener)
    assert tracer.enabled
    tracer.record(TraceEvent(trace_id="t", name="sandbox.run"))
    report = tracer.flush()
    assert report.attempted == 1 and report.sent == 0 and report.error
    assert len(tracer.events()) == 1  # retained for retry


def test_langsmith_flush_clears_on_success():
    def opener(request, timeout):
        return io.BytesIO(b"{}")

    tracer = LangSmithTracer(api_key="k", opener=opener)
    tracer.record(TraceEvent(trace_id="t", name="evidence.synthesis"))
    report = tracer.flush()
    assert report.sent == 1 and not report.error
    assert tracer.events() == []
