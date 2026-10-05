"""Deterministic local sandbox (Phase 1).

Executes NOTHING on the host: commands are validated and then dispatched to
registered in-process handlers. Durations are measured with perf_counter;
output/artifact caps and timeouts are enforced structurally.
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Mapping

from sandbox.base import (
    RawResult,
    Sandbox,
    SandboxConstraints,
    sanitize_command,
    sanitize_env,
)
from sandbox.errors import (
    CommandRejectedError,
    LimitViolationError,
    SandboxError,
    SessionError,
)

#: Handler: (command, sanitized_env) -> (stdout, stderr, exit_code).
Handler = Callable[[str, Mapping[str, str]], tuple[str, str, int]]


@dataclass
class _Session:
    handle: str
    constraints: SandboxConstraints
    transcript: list[dict[str, object]] = field(default_factory=list)
    destroyed: bool = False


class LocalDeterministicSandbox(Sandbox):
    def __init__(
        self,
        constraints: SandboxConstraints | None = None,
        handlers: dict[str, Handler] | None = None,
    ) -> None:
        self._constraints = constraints or SandboxConstraints()
        self._handlers: dict[str, Handler] = dict(handlers or {})
        self._sessions: dict[str, _Session] = {}

    def register_handler(self, prefix: str, handler: Handler) -> None:
        self._handlers[prefix] = handler

    @property
    def constraints(self) -> SandboxConstraints:
        return self._constraints

    def active_sessions(self) -> int:
        return len(self._sessions)

    def create(self) -> str:
        handle = uuid.uuid4().hex
        self._sessions[handle] = _Session(
            handle=handle, constraints=self._constraints
        )
        return handle

    def _require(self, handle: str) -> _Session:
        session = self._sessions.get(handle)
        if session is None or session.destroyed:
            raise SessionError(f"unknown or destroyed session: {handle!r}")
        return session

    def execute(
        self, handle: str, command: str, env: Mapping[str, str] | None = None
    ) -> RawResult:
        session = self._require(handle)
        limits = session.constraints.limits
        clean_command = sanitize_command(command, session.constraints.allowed_commands)
        clean_env = sanitize_env(env or {}, session.constraints.allowed_env_keys)

        prefix = clean_command.strip().split()[0]
        handler = self._handlers.get(prefix)
        if handler is None:
            raise CommandRejectedError(f"no handler registered for {prefix!r}")

        started = time.perf_counter()
        produced = handler(clean_command, clean_env)
        if (
            not isinstance(produced, tuple)
            or len(produced) != 3
            or not isinstance(produced[0], str)
            or not isinstance(produced[1], str)
            or not isinstance(produced[2], int)
            or isinstance(produced[2], bool)
        ):
            raise SandboxError(f"handler {prefix!r} returned a malformed result")
        stdout, stderr, exit_code = produced
        duration = time.perf_counter() - started
        if duration > limits.timeout_s:
            raise LimitViolationError(
                f"execution exceeded timeout of {limits.timeout_s}s"
            )

        out_bytes = len(stdout.encode("utf-8")) + len(stderr.encode("utf-8"))
        if out_bytes > limits.max_output_bytes:
            raise LimitViolationError(
                f"output {out_bytes}B exceeds cap of {limits.max_output_bytes}B"
            )

        session.transcript.append(
            {
                "command": clean_command,
                "environment": dict(clean_env),
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": exit_code,
                "duration_s": duration,
            }
        )
        return RawResult(
            stdout=stdout,
            stderr=stderr,
            exit_code=int(exit_code),
            duration_s=duration,
            environment=dict(clean_env),
        )

    def collect(self, handle: str) -> dict[str, str]:
        session = self._require(handle)
        limits = session.constraints.limits
        artifacts = {
            f"exec-{index}.json": json.dumps(
                entry, sort_keys=True, separators=(",", ":"), default=str
            )
            for index, entry in enumerate(session.transcript)
        }
        if len(artifacts) > limits.max_artifacts:
            raise LimitViolationError(
                f"{len(artifacts)} artifacts exceed cap of {limits.max_artifacts}"
            )
        return artifacts

    def destroy(self, handle: str) -> None:
        session = self._sessions.get(handle)
        if session is None or session.destroyed:
            raise SessionError(f"unknown or destroyed session: {handle!r}")
        session.transcript.clear()
        session.destroyed = True
        del self._sessions[handle]