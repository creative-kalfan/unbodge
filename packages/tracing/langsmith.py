"""LangSmith tracing backend (Phase 3, strictly optional).

Without ``LANGSMITH_API_KEY`` the tracer reports ``enabled=False`` and
only fills the local buffer -- the proof loop is unaffected. With
credentials, ``flush()`` mirrors buffered events to the LangSmith runs
batch endpoint (best effort; failures are reported, never raised into
the proof path, and no test exercises the live path).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tracing.base import TraceEvent, Tracer

DEFAULT_ENDPOINT = "https://api.smith.langchain.com"
MAX_BUFFER_EVENTS = 1000
MAX_ATTRIBUTE_CHARS = 2000
MAX_BODY_BYTES = 1_048_576

Opener = Callable[[urllib.request.Request, float], Any]


def _check_https_endpoint(url: str) -> None:
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
    except ValueError:
        raise ValueError(f"langsmith endpoint is not a valid URL: {url!r}")
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("langsmith endpoint must be an https:// URL without credentials")


def _scrub(attributes: dict[str, str]) -> dict[str, str]:
    cleaned: dict[str, str] = {}
    for key, value in attributes.items():
        text = value if isinstance(value, str) else str(value)
        if len(text) > MAX_ATTRIBUTE_CHARS:
            text = text[:MAX_ATTRIBUTE_CHARS]
        cleaned[key] = text
    return cleaned


@dataclass
class FlushReport:
    attempted: int
    sent: int
    error: str = ""


class LangSmithTracer(Tracer):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        endpoint: str | None = None,
        project: str | None = None,
        timeout_s: float = 30,
        opener: Opener | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get("LANGSMITH_API_KEY", "")
        endpoint = (
            endpoint if endpoint is not None else os.environ.get("LANGSMITH_ENDPOINT", DEFAULT_ENDPOINT)
        ).rstrip("/")
        _check_https_endpoint(endpoint)
        self._endpoint = endpoint
        self._project = (
            project if project is not None else os.environ.get("LANGSMITH_PROJECT", "unbodge-history-v1")
        )
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self._timeout_s = timeout_s
        self._opener = opener
        self._buffer: list[TraceEvent] = []

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    @property
    def project(self) -> str:
        return self._project

    def record(self, event: TraceEvent) -> None:
        if len(self._buffer) >= MAX_BUFFER_EVENTS:
            del self._buffer[: len(self._buffer) - MAX_BUFFER_EVENTS + 1]
        self._buffer.append(
            event.model_copy(update={"attributes": _scrub(event.attributes)})
        )

    def events(self) -> list[TraceEvent]:
        return list(self._buffer)

    def flush(self) -> FlushReport:
        """Mirror buffered events remotely. Never used by the proof loop."""
        if not self.enabled:
            return FlushReport(attempted=0, sent=0, error="langsmith not configured")
        payload = json.dumps(
            {
                "project_name": self._project,
                "runs": [
                    {
                        "name": event.name,
                        "run_type": "chain",
                        "inputs": {"trace_id": event.trace_id, **event.attributes},
                        "start_time": event.at.isoformat(),
                    }
                    for event in self._buffer
                ],
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self._endpoint}/api/v1/runs/batch",
            data=payload,
            headers={"x-api-key": self._api_key, "Content-Type": "application/json"},
            method="POST",
        )
        try:
            if self._opener is not None:
                response = self._opener(request, self._timeout_s)
                if hasattr(response, "read"):
                    response.read()
            else:
                with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                    response.read(MAX_BODY_BYTES + 1)
        except Exception as exc:
            return FlushReport(attempted=len(self._buffer), sent=0, error=str(exc)[:200])
        sent, self._buffer = len(self._buffer), []
        return FlushReport(attempted=sent, sent=sent)


__all__ = ["DEFAULT_ENDPOINT", "FlushReport", "LangSmithTracer"]
