"""Durable workflow mapping (Phase 4).

The 13 logical pipeline stages are declared as versioned, idempotent
activities with explicit retry policies. ``LocalWorkflowRunner`` executes
them through the existing local pipeline (authoritative). A Temporal
server integration is NOT available in this environment (no SDK, no
server): ``TemporalWorkflowRunner`` exists solely to document the mapping
and fails closed. No swarm, no autonomous agents: one durable workflow.
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.errors import UnbodgeError
from workflow.stages import STAGE_NAMES


class TemporalUnavailableError(UnbodgeError):
    """Temporal server/SDK unavailable (explicit, never faked)."""


@dataclass(frozen=True)
class ActivityDefinition:
    name: str
    version: str = "v1"
    idempotency_key: str = "stage-name"
    max_retries: int = 3
    timeout_s: int = 600


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_s: int = 5
    retry_on: tuple[str, ...] = ("TimeoutError", "ConnectionError")


ACTIVITIES: tuple[ActivityDefinition, ...] = tuple(
    ActivityDefinition(name=name) for name in STAGE_NAMES
)

WORKFLOW_NAME = "unbodge-proof-loop"
WORKFLOW_VERSION = "v1"


class LocalWorkflowRunner:
    """Executes the durable activity list locally via ``run_pipeline``."""

    def __init__(self, activities: tuple[ActivityDefinition, ...] = ACTIVITIES) -> None:
        names = [activity.name for activity in activities]
        if names != list(STAGE_NAMES):
            raise ValueError("activity list must match the pipeline stages in order")
        self._activities = activities

    @property
    def activities(self) -> tuple[ActivityDefinition, ...]:
        return self._activities

    def run(self, state, ctx, *, retry_policy: RetryPolicy | None = None):
        """Run pending activities with bounded retries (stages are idempotent)."""
        from workflow.pipeline import run_pipeline

        attempts = retry_policy.max_attempts if retry_policy else 1
        if attempts < 1:
            raise ValueError("max_attempts must be positive")
        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                return run_pipeline(state, ctx)
            except Exception as exc:
                last_error = exc
        assert last_error is not None
        raise last_error


class TemporalWorkflowRunner:
    """Placeholder mapping to a Temporal server (unavailable here)."""

    def __init__(self, *, address: str = "", namespace: str = "default") -> None:
        self._address = address
        self._namespace = namespace

    @property
    def configured(self) -> bool:
        try:
            import temporalio  # noqa: F401
        except ImportError:
            return False
        return bool(self._address)

    def run(self, state, ctx, **kwargs):
        raise TemporalUnavailableError(
            "temporal server/SDK unavailable; use LocalWorkflowRunner"
        )


__all__ = [
    "ACTIVITIES",
    "ActivityDefinition",
    "LocalWorkflowRunner",
    "RetryPolicy",
    "TemporalUnavailableError",
    "TemporalWorkflowRunner",
    "WORKFLOW_NAME",
    "WORKFLOW_VERSION",
]
