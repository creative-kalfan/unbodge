"""Production API: HTTP layer over frozen domain contracts (Phase 4)."""

from api.app import VERSION, create_app
from api.models import DecisionOut, ErrorOut, EventIn, RepositoryIn, RepositoryOut
from api.webhooks import (
    MAX_BODY_BYTES,
    SUPPORTED_EVENTS,
    WebhookError,
    parse_webhook,
    verify_signature,
    webhook_secret,
)

__all__ = [
    "DecisionOut",
    "ErrorOut",
    "EventIn",
    "MAX_BODY_BYTES",
    "SUPPORTED_EVENTS",
    "VERSION",
    "RepositoryIn",
    "RepositoryOut",
    "WebhookError",
    "create_app",
    "parse_webhook",
    "verify_signature",
    "webhook_secret",
]
