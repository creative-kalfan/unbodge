"""GitHub webhook ingestion (Phase 4).

HMAC-SHA256 validation (`X-Hub-Signature-256` vs `WEBHOOK_SECRET`),
idempotency by delivery ID, strict event allowlist. All content is
untrusted data: stored as records for reasoning/analysis, never
executed. Only `push`/`release`/`issues`/`issue_comment`/`pull_request`
map to upstream events; anything else is acknowledged and ignored.
A missing secret fails closed: nothing is ingested.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re

from domain.errors import UnbodgeError

SUPPORTED_EVENTS = frozenset(
    {"push", "release", "issues", "issue_comment", "pull_request"}
)
MAX_BODY_BYTES = 1_000_000

_DELIVERY_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


class WebhookError(UnbodgeError):
    """Webhook validation failure (auth, shape, size, event)."""


def verify_signature(body: bytes, signature: str, secret: str) -> bool:
    """Constant-time HMAC-SHA256 check (`sha256=<hex>`)."""
    if not signature.startswith("sha256=") or not secret:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature[len("sha256="):])


def webhook_secret() -> str:
    return os.environ.get("UNBODGE_WEBHOOK_SECRET", "")


def parse_webhook(
    *,
    event: str,
    delivery_id: str,
    signature: str,
    body: bytes,
    secret: str = "",
) -> dict:
    """Validate and normalize a webhook delivery into an ingest record."""
    if len(body) > MAX_BODY_BYTES:
        raise WebhookError("webhook payload exceeds size cap")
    if not _DELIVERY_RE.fullmatch(delivery_id or ""):
        raise WebhookError("invalid delivery id")
    active_secret = secret if secret else webhook_secret()
    if not active_secret:
        raise WebhookError("webhook secret not configured")
    if not verify_signature(body, signature, active_secret):
        raise WebhookError("webhook signature mismatch")
    if event not in SUPPORTED_EVENTS:
        raise WebhookError(f"unsupported event: {event!r}")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise WebhookError(f"webhook payload is not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise WebhookError("webhook payload must be a JSON object")
    repo = payload.get("repository", {})
    full_name = repo.get("full_name", "") if isinstance(repo, dict) else ""
    return {
        "delivery_id": delivery_id,
        "event": event,
        "repository": str(full_name)[:256],
        "action": str(payload.get("action", ""))[:64],
    }


__all__ = [
    "MAX_BODY_BYTES",
    "SUPPORTED_EVENTS",
    "WebhookError",
    "parse_webhook",
    "verify_signature",
    "webhook_secret",
]
