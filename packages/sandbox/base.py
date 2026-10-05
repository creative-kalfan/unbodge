"""Sandbox contract (Phase 1).

Lifecycle is explicit: ``create -> execute* -> collect -> destroy``.
Security posture is structural, not advisory:

- commands must match the allowlist AND the safe-command grammar
- the environment is sanitized before anything executes
- network policy is deny-all
- resource limits are enforced structurally (timeout, output, artifact caps).
  ``max_memory_mb`` is validated at construction but advisory for the local
  in-process implementation: real RSS enforcement requires the process
  isolation of later phases. Timeouts are cooperative (measured around the
  handler call), so registered handlers must be bounded, fast, and pure.
- every session is cleaned up via ``destroy`` (or the session context manager)

Phase 1 never executes model-generated commands on the host: the local
implementation only dispatches registered in-process handlers.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator, Mapping

from sandbox.errors import CommandRejectedError, LimitViolationError

#: Safe-command grammar: word chars, dashes, dots, slashes, colons, equals,
#: whitespace. Anything else (shell metacharacters, quotes, backslashes,
#: newlines) is rejected before the allowlist is even consulted.
ALLOWED_COMMAND_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_./=:\s-]*$")

#: Defence in depth: explicit denylist checked before the grammar.
DENIED_COMMAND_TOKENS = (
    ";", "|", "&", "$", "`", "(", ")", "<", ">", "\\", "\n", "\r", "..",
    '"', "'", "{", "}", "!", "~", "*", "?", "#",
)

#: Environment variable names matching these patterns are never propagated,
#: even if explicitly provided (secret-leakage guard).
SENSITIVE_ENV_PATTERNS = (
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASSWD",
    "PRIVATE",
    "AWS_",
    "GITHUB_",
    "NEBIUS_",
    "OPENAI_",
    "ANTHROPIC_",
    "KEY",
    "AUTH",
    "CREDS",
    "CREDENTIAL",
    "COOKIE",
    "SESSION",
    "BEARER",
    "PASSPHRASE",
    "SIGNING",
    "ENCRYPT",
)

#: Hard caps that apply regardless of configured limits.
MAX_COMMAND_CHARS = 4096
MAX_ENV_VALUE_CHARS = 4096


@dataclass(frozen=True)
class ResourceLimits:
    timeout_s: int = 30
    max_memory_mb: int = 512
    max_output_bytes: int = 65536
    max_artifacts: int = 16

    def __post_init__(self) -> None:
        if self.timeout_s <= 0:
            raise LimitViolationError(f"timeout_s must be > 0, got {self.timeout_s}")
        if self.max_memory_mb <= 0:
            raise LimitViolationError(f"max_memory_mb must be > 0, got {self.max_memory_mb}")
        if self.max_output_bytes <= 0:
            raise LimitViolationError(
                f"max_output_bytes must be > 0, got {self.max_output_bytes}"
            )
        if self.max_artifacts <= 0:
            raise LimitViolationError(
                f"max_artifacts must be > 0, got {self.max_artifacts}"
            )


@dataclass(frozen=True)
class SandboxConstraints:
    limits: ResourceLimits = field(default_factory=ResourceLimits)
    allowed_commands: tuple[str, ...] = ("synthetic-check", "regression-suite")
    allowed_env_keys: frozenset[str] = frozenset({"DEP_VERSION", "WORKAROUND", "SUITE"})
    filesystem_root: str = "sandbox://local"
    network: str = "deny_all"


@dataclass(frozen=True)
class RawResult:
    """Outcome of one sandboxed command execution."""

    stdout: str
    stderr: str
    exit_code: int
    duration_s: float
    environment: dict[str, str]


def sanitize_env(
    env: Mapping[str, str], allowed_keys: frozenset[str] | set[str]
) -> dict[str, str]:
    """Return only explicitly allowed, non-sensitive environment entries."""
    clean: dict[str, str] = {}
    for key, value in env.items():
        if key not in allowed_keys:
            continue
        upper = key.upper()
        if any(pattern in upper for pattern in SENSITIVE_ENV_PATTERNS):
            continue
        if len(value) > MAX_ENV_VALUE_CHARS:
            raise LimitViolationError(
                f"env value for {key!r} exceeds {MAX_ENV_VALUE_CHARS} chars"
            )
        clean[str(key)] = str(value)
    return clean


def sanitize_command(command: str, allowed_commands: tuple[str, ...]) -> str:
    """Validate a command; return it unchanged or raise CommandRejectedError."""
    if not command or not command.strip():
        raise CommandRejectedError("empty command")
    if len(command) > MAX_COMMAND_CHARS:
        raise CommandRejectedError(f"command exceeds {MAX_COMMAND_CHARS} chars")
    for token in DENIED_COMMAND_TOKENS:
        if token in command:
            raise CommandRejectedError(f"denied token {token!r} in command")
    if not ALLOWED_COMMAND_RE.match(command):
        raise CommandRejectedError(f"command violates safe-command grammar: {command!r}")
    first = command.strip().split()[0]
    if first not in allowed_commands:
        raise CommandRejectedError(f"command {first!r} is not in the allowlist")
    return command


class Sandbox(ABC):
    """Execution-lifecycle interface. Later phases plug Docker/Nebius behind this."""

    @abstractmethod
    def create(self) -> str:
        """Create an isolated session; return its handle."""
        raise NotImplementedError

    @abstractmethod
    def execute(
        self, handle: str, command: str, env: Mapping[str, str] | None = None
    ) -> RawResult:
        """Execute one validated command inside ``handle``."""
        raise NotImplementedError

    @abstractmethod
    def collect(self, handle: str) -> dict[str, str]:
        """Collect capped artifacts (transcripts) for ``handle``."""
        raise NotImplementedError

    @abstractmethod
    def destroy(self, handle: str) -> None:
        """Tear down ``handle`` and release its resources."""
        raise NotImplementedError

    @contextmanager
    def session(self) -> Iterator[str]:
        """Convenience lifecycle wrapper: create, yield, always destroy."""
        handle = self.create()
        try:
            yield handle
        finally:
            self.destroy(handle)