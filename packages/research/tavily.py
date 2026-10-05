"""Tavily research provider (Phase 3).

Live search behind ``ResearchProvider``. Credentials strictly from the
environment (``TAVILY_API_KEY``); without them every call fails closed
with ``ResearchAuthError``. Transport errors map to typed failures --
an unavailable Tavily never yields fabricated research. An injectable
``opener`` keeps tests offline and credit-free.
"""

from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from evidence.hashing import sha256_hex
from pydantic import ValidationError
from research.base import ResearchProvider
from research.models import (
    ResearchAuthError,
    ResearchBundle,
    ResearchQuery,
    ResearchResult,
    ResearchUnavailableError,
)

TAVILY_ENDPOINT = "https://api.tavily.com/search"
MAX_BODY_BYTES = 1_048_576
MAX_FIELD_CHARS = 2000

Opener = Callable[[urllib.request.Request, float], Any]


def _check_https_endpoint(url: str) -> None:
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
    except ValueError:
        raise ValueError(f"tavily endpoint is not a valid URL: {url!r}")
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("tavily endpoint must be an https:// URL without credentials")


def _clean(text: object) -> str:
    cleaned = "".join(c if c >= " " or c in ("\n", "\t") else " " for c in str(text))
    if len(cleaned) > MAX_FIELD_CHARS:
        cleaned = cleaned[:MAX_FIELD_CHARS]
    return cleaned


class TavilyResearchProvider(ResearchProvider):
    def __init__(
        self,
        *,
        api_key: str | None = None,
        endpoint: str = TAVILY_ENDPOINT,
        timeout_s: float = 30,
        opener: Opener | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get("TAVILY_API_KEY", "")
        _check_https_endpoint(endpoint)
        self._endpoint = endpoint
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self._timeout_s = timeout_s
        self._opener = opener

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def search(self, query: ResearchQuery) -> ResearchBundle:
        if not self._api_key:
            raise ResearchAuthError("TAVILY_API_KEY is not set")
        payload = json.dumps(
            {
                "api_key": self._api_key,
                "query": query.query,
                "max_results": query.top_k,
                "topic": query.topic or "general",
                "include_answer": False,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self._endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            if self._opener is not None:
                response = self._opener(request, self._timeout_s)
                raw = response.read() if hasattr(response, "read") else response
            else:
                with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                    raw = response.read(MAX_BODY_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise ResearchAuthError(f"tavily authentication failed: {exc.code}") from exc
            raise ResearchUnavailableError(f"tavily HTTP error: {exc.code}") from exc
        except (urllib.error.URLError, ConnectionError, socket.timeout, TimeoutError) as exc:
            raise ResearchUnavailableError(f"tavily transport failed: {exc}") from exc
        if isinstance(raw, bytes) and len(raw) > MAX_BODY_BYTES:
            raise ResearchUnavailableError("tavily response exceeds size cap")
        try:
            envelope = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
            entries = envelope.get("results", [])
            if not isinstance(entries, list):
                raise ValueError("missing results list")
        except (ValueError, AttributeError) as exc:
            raise ResearchUnavailableError(f"tavily response unparseable: {exc}") from exc
        moment = datetime.now(timezone.utc)
        results: list[ResearchResult] = []
        for index, entry in enumerate(entries[: query.top_k]):
            if not isinstance(entry, dict):
                continue
            try:
                url = _clean(entry.get("url", ""))
                title = _clean(entry.get("title", ""))
                snippet = _clean(entry.get("content", ""))
                score = float(entry.get("score", 0.0) or 0.0)
                result = ResearchResult(
                    id=f"tavily:{sha256_hex(query.query)[:12]}:{index}",
                    query=query.query,
                    source=url or "tavily",
                    title=title,
                    snippet=snippet,
                    url=url,
                    score=score,
                    content_hash=sha256_hex(f"{url}\n{title}\n{snippet}"),
                    retrieved_at=moment,
                )
            except (ValueError, TypeError, ValidationError):
                continue
            results.append(result)
        return ResearchBundle(query=query.query, results=results, retrieved_at=moment)


__all__ = ["TAVILY_ENDPOINT", "TavilyResearchProvider"]
