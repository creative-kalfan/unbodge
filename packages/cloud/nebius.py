"""Nebius cloud sandbox adapter (Phase 4).

Same ``Sandbox`` ABC as ``LocalDockerSandbox``: identical client-side
validation (commands, env, paths), limits, and lifecycle semantics, so one
experiment specification runs through either backend unchanged.

No credentials/endpoint => every execution raises an explicit
``SandboxUnavailableError`` (local execution stays authoritative for
tests). With an injected ``transport`` the request/response mapping is
unit-tested WITHOUT claiming any real cloud execution: Phase 4 performs
zero live Nebius runs (reported as unavailable integration).
"""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import urlsplit

from sandbox.base import (
    RawResult,
    ResourceLimits,
    Sandbox,
    SandboxConstraints,
    sanitize_command,
    sanitize_env,
)
from sandbox.docker import ContainerResult, check_container_argv, check_container_files
from sandbox.errors import CommandRejectedError, LimitViolationError, SandboxError, SessionError

Opener = Callable[[urllib.request.Request, float], Any]


class SandboxUnavailableError(SandboxError):
    """Cloud backend not configured, unreachable, or failed (never faked)."""


@dataclass
class _CloudSession:
    handle: str
    destroyed: bool = False
    transcript: list[dict[str, object]] = field(default_factory=list)


class NebiusSandbox(Sandbox):
    """Nebius-backed sandbox behind the standard lifecycle.

    ``transport`` injection (``opener(request, timeout) -> response``)
    keeps unit tests offline. Live use requires ``NEBIUS_API_KEY`` and
    ``NEBIUS_SANDBOX_URL``.
    """

    def __init__(
        self,
        constraints: SandboxConstraints | None = None,
        handlers: dict | None = None,
        *,
        api_key: str | None = None,
        endpoint: str | None = None,
        image: str = "python:3.11-slim",
        real_commands: tuple[str, ...] = ("python",),
        timeout_s: float = 120,
        opener: Opener | None = None,
    ) -> None:
        self._constraints = constraints or SandboxConstraints()
        self._handlers: dict = dict(handlers or {})
        self._api_key = api_key if api_key is not None else os.environ.get("NEBIUS_API_KEY", "")
        self._endpoint = (
            endpoint if endpoint is not None else os.environ.get("NEBIUS_SANDBOX_URL", "")
        ).rstrip("/")
        if self._endpoint:
            parts = urlsplit(self._endpoint)
            if (
                parts.scheme != "https"
                or not parts.hostname
                or parts.username
                or parts.password
            ):
                raise ValueError("nebius endpoint must be an https:// URL without credentials")
        self._image = image
        self._real_commands = real_commands
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self._timeout_s = timeout_s
        self._opener = opener
        self._sessions: dict[str, _CloudSession] = {}

    @property
    def configured(self) -> bool:
        return bool(self._api_key and self._endpoint)

    def _require_configured(self) -> None:
        if not self.configured:
            raise SandboxUnavailableError(
                "nebius sandbox not configured (NEBIUS_API_KEY/NEBIUS_SANDBOX_URL); "
                "local execution remains authoritative"
            )

    # -- Phase 1 handler path (identical validation semantics) -----------
    def register_handler(self, prefix: str, handler) -> None:
        self._handlers[prefix] = handler

    def active_sessions(self) -> int:
        return len(self._sessions)

    def create(self) -> str:
        handle = uuid.uuid4().hex
        self._sessions[handle] = _CloudSession(handle=handle)
        return handle

    def _require(self, handle: str) -> _CloudSession:
        session = self._sessions.get(handle)
        if session is None or session.destroyed:
            raise SessionError(f"unknown or destroyed session: {handle!r}")
        return session

    def execute(
        self, handle: str, command: str, env: Mapping[str, str] | None = None
    ) -> RawResult:
        session = self._require(handle)
        limits = self._constraints.limits
        clean_command = sanitize_command(command, self._constraints.allowed_commands)
        clean_env = sanitize_env(env or {}, self._constraints.allowed_env_keys)
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
            raise LimitViolationError(f"execution exceeded timeout of {limits.timeout_s}s")
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
            stdout=stdout, stderr=stderr, exit_code=int(exit_code),
            duration_s=duration, environment=dict(clean_env),
        )

    def collect(self, handle: str) -> dict[str, str]:
        import json as _json

        session = self._require(handle)
        if len(session.transcript) > self._constraints.limits.max_artifacts:
            raise LimitViolationError("artifact cap exceeded")
        return {
            f"exec-{index}.json": _json.dumps(entry, sort_keys=True, default=str)
            for index, entry in enumerate(session.transcript)
        }

    def destroy(self, handle: str) -> None:
        session = self._sessions.get(handle)
        if session is None or session.destroyed:
            raise SessionError(f"unknown or destroyed session: {handle!r}")
        session.transcript.clear()
        session.destroyed = True
        del self._sessions[handle]

    # -- real container path (remote execution, fail-closed) -------------
    def run_container(
        self,
        files: Mapping[str, str],
        argv: list[str],
        env: Mapping[str, str] | None = None,
        *,
        timeout_s: float | None = None,
    ) -> ContainerResult:
        """Execute ``argv`` remotely. Unconfigured => UnavailableError."""
        self._require_configured()
        clean_argv = check_container_argv(list(argv), self._real_commands)
        staged = check_container_files(dict(files))
        clean_env = sanitize_env(dict(env or {}), self._constraints.allowed_env_keys)
        deadline = timeout_s if timeout_s is not None else float(
            self._constraints.limits.timeout_s
        )
        if deadline <= 0:
            raise ValueError("nebius run deadline must be positive")
        return self._remote_run(staged, clean_argv, clean_env, deadline)

    def _remote_run(
        self, files: dict[str, str], argv: list[str], env: dict[str, str], deadline: float
    ) -> ContainerResult:
        payload = json.dumps(
            {
                "image": self._image,
                "argv": argv,
                "files": files,
                "env": env,
                "limits": {
                    "timeout_s": deadline,
                    "memory_mb": self._constraints.limits.max_memory_mb,
                    "network": self._constraints.network,
                },
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self._endpoint}/v1/sandbox/run",
            data=payload,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            if self._opener is not None:
                response = self._opener(request, self._timeout_s)
                raw = response.read() if hasattr(response, "read") else response
            else:
                with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                    raw = response.read(1_048_577)
        except urllib.error.HTTPError as exc:
            raise SandboxUnavailableError(f"nebius sandbox HTTP error: {exc.code}") from exc
        except (urllib.error.URLError, ConnectionError, socket.timeout, TimeoutError) as exc:
            raise SandboxUnavailableError(f"nebius sandbox unreachable: {exc}") from exc
        except SandboxUnavailableError:
            raise
        except Exception as exc:
            raise SandboxUnavailableError(f"nebius transport failed: {type(exc).__name__}") from exc
        if isinstance(raw, bytes) and len(raw) > 1_048_576:
            raise SandboxUnavailableError("nebius response exceeds size cap")
        try:
            body = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
            artifacts = _coerce_artifacts(body.get("artifacts", {}))
            return ContainerResult(
                stdout=str(body["stdout"])[:1_048_576],
                stderr=str(body.get("stderr", ""))[:1_048_576],
                exit_code=int(body["exit_code"]),
                duration_s=float(body.get("duration_s", 0.0)),
                environment=dict(env),
                artifacts=artifacts,
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise SandboxUnavailableError(f"nebius response unparseable: {exc}") from exc


def _coerce_artifacts(value: object) -> dict[str, str]:
    """Bound and stringify an untrusted artifact mapping."""
    if not isinstance(value, dict):
        raise ValueError("artifacts must be a mapping")
    artifacts: dict[str, str] = {}
    for key, item in value.items():
        if len(artifacts) >= 256:
            break
        name = str(key)[:256]
        text = item if isinstance(item, str) else str(item)
        artifacts[name] = text[:262_144]
    return artifacts


__all__ = ["NebiusSandbox", "SandboxUnavailableError"]
