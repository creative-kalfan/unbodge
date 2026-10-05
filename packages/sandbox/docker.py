"""Real local sandbox on Docker/OCI (Phase 2).

Two execution paths behind one lifecycle:
- ``execute()``: Phase 1-compatible handler dispatch (in-process, for the
  synthetic proof and unit-speed tests).
- ``run_container()``: REAL isolated execution. CWD files plus a generated
  entry shim are copied into a fresh container (``--network none``,
  memory/CPU caps); the target argv travels embedded in the shim file, so
  no shell ever interprets anything. Stdout/stderr/exit code are copied
  back out as files, giving exact stream separation.

Fail-closed offline behavior: the image must already be present
(``docker image inspect``); UNBODGE never pulls implicitly.
"""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from sandbox.base import (
    ResourceLimits,
    Sandbox,
    SandboxConstraints,
    sanitize_command,
    sanitize_env,
)
from sandbox.errors import CommandRejectedError, LimitViolationError, SandboxError, SessionError

_DOCKER_TIMEOUT_S = 120
_MAX_ARGV_ELEMENT_CHARS = 4096
_MAX_CONTAINER_FILE_BYTES = 256 * 1024
_MAX_ARTIFACT_SCAN = 10000
_MAX_STAGED_FILE_BYTES = 256 * 1024
_MAX_STAGED_TOTAL_BYTES = 1_000_000
_IMAGE_RE = re.compile(r"^[A-Za-z0-9_./:@-]+$")


def check_container_argv(argv: list[str], real_commands: tuple[str, ...]) -> list[str]:
    """Validate a real-execution argv vector (no shell involved)."""
    if not argv or not isinstance(argv, list):
        raise CommandRejectedError("container argv must be a non-empty list")
    if argv[0] not in real_commands:
        raise CommandRejectedError(f"container command {argv[0]!r} is not allowlisted")
    for element in argv:
        if not isinstance(element, str):
            raise CommandRejectedError("container argv elements must be strings")
        if "\x00" in element or "\n" in element or "\r" in element:
            raise CommandRejectedError("container argv contains control characters")
        if len(element) > _MAX_ARGV_ELEMENT_CHARS:
            raise CommandRejectedError("container argv element too long")
    return argv


def check_container_files(files: Mapping[str, str]) -> dict[str, str]:
    """Validate staged container files (paths, names, sizes)."""
    staged: dict[str, str] = {}
    total = 0
    for rel, content in files.items():
        if not isinstance(rel, str) or not rel or rel.startswith("/") or "\\" in rel:
            raise CommandRejectedError(f"unsafe container path: {rel!r}")
        if ".." in Path(rel).parts or not isinstance(content, str):
            raise CommandRejectedError(f"unsafe container path: {rel!r}")
        if Path(rel).parts[0].startswith("_unbodge_"):
            raise CommandRejectedError(f"reserved container path: {rel!r}")
        size = len(content.encode("utf-8"))
        if size > _MAX_STAGED_FILE_BYTES:
            raise LimitViolationError(f"staged file too large: {rel!r}")
        total += size
        if total > _MAX_STAGED_TOTAL_BYTES:
            raise LimitViolationError("staged files exceed total cap")
        staged[rel] = content
    return staged

_ENTRY_SHIM_TEMPLATE = """\
import json
import subprocess
import sys
from pathlib import Path

def main() -> int:
    spec = json.loads(Path("/work/_unbodge_argv.json").read_text(encoding="utf-8"))
    try:
        proc = subprocess.run(
            spec["argv"], capture_output=True, cwd="/work", check=False,
        )
    except Exception as exc:  # e.g. missing executable: fail closed
        Path("/work/_unbodge_err.bin").write_bytes(f"entry error: {exc}".encode())
        Path("/work/_unbodge_out.bin").write_bytes(b"")
        Path("/work/_unbodge_exit").write_text("127", encoding="utf-8")
        return 0
    Path("/work/_unbodge_out.bin").write_bytes(proc.stdout)
    Path("/work/_unbodge_err.bin").write_bytes(proc.stderr)
    Path("/work/_unbodge_exit").write_text(str(proc.returncode), encoding="utf-8")
    return 0

if __name__ == "__main__":
    sys.exit(main())
"""


@dataclass
class ContainerResult:
    stdout: str
    stderr: str
    exit_code: int
    duration_s: float
    environment: dict[str, str]
    artifacts: dict[str, str] = field(default_factory=dict)


@dataclass
class _HandlerSession:
    handle: str
    transcript: list[dict[str, object]] = field(default_factory=list)
    destroyed: bool = False


def _docker(*args: str, timeout_s: int = _DOCKER_TIMEOUT_S) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            ["docker", *args],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SandboxError("docker CLI not found") from exc
    except subprocess.TimeoutExpired as exc:
        raise LimitViolationError(f"docker CLI timed out: docker {' '.join(args)}") from exc


def docker_available(image: str = "python:3.11-slim") -> bool:
    """True iff the docker CLI, daemon, and ``image`` are all present."""
    if shutil.which("docker") is None:
        return False
    try:
        info = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, timeout=30, check=False,
        )
        if info.returncode != 0:
            return False
        inspect = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True, timeout=30, check=False,
        )
        return inspect.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


class DockerSandbox(Sandbox):
    """Docker-backed sandbox. Handler path mirrors Phase 1; ``run_container``
    executes real argv vectors in throwaway containers."""

    def __init__(
        self,
        constraints: SandboxConstraints | None = None,
        handlers: dict | None = None,
        *,
        image: str = "python:3.11-slim",
        real_commands: tuple[str, ...] = ("python",),
    ) -> None:
        if shutil.which("docker") is None:
            raise SandboxError("docker CLI not found on PATH")
        if (
            not isinstance(image, str)
            or not _IMAGE_RE.fullmatch(image)
            or image.startswith("-")
        ):
            raise SandboxError(f"unsafe docker image reference: {image!r}")
        self._constraints = constraints or SandboxConstraints()
        self._handlers: dict = dict(handlers or {})
        self._image = image
        self._real_commands = real_commands
        self._sessions: dict[str, _HandlerSession] = {}
        self._daemon_ok: bool | None = None
        self._image_ok: bool | None = None

    # -- environment ----------------------------------------------------
    def ensure_daemon(self) -> None:
        if self._daemon_ok is None:
            probe = _docker("info", "--format", "{{.ServerVersion}}")
            self._daemon_ok = probe.returncode == 0
        if not self._daemon_ok:
            raise SandboxError("docker daemon unreachable")

    def ensure_image(self) -> None:
        self.ensure_daemon()
        if self._image_ok is None:
            probe = _docker("image", "inspect", self._image)
            self._image_ok = probe.returncode == 0
        if not self._image_ok:
            raise SandboxError(
                f"image {self._image!r} not present locally; "
                "UNBODGE never pulls implicitly (offline fail-closed)"
            )

    @property
    def image(self) -> str:
        return self._image

    # -- Phase 1 handler path (ABC conformance) --------------------------
    def register_handler(self, prefix: str, handler) -> None:
        self._handlers[prefix] = handler

    def active_sessions(self) -> int:
        return len(self._sessions)

    def create(self) -> str:
        handle = uuid.uuid4().hex
        self._sessions[handle] = _HandlerSession(handle=handle)
        return handle

    def _require(self, handle: str) -> _HandlerSession:
        session = self._sessions.get(handle)
        if session is None or session.destroyed:
            raise SessionError(f"unknown or destroyed session: {handle!r}")
        return session

    def execute(
        self, handle: str, command: str, env: Mapping[str, str] | None = None
    ):
        from sandbox.base import RawResult

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
        if len(stdout.encode()) + len(stderr.encode()) > limits.max_output_bytes:
            raise LimitViolationError("output exceeds cap")
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
        limits = self._constraints.limits
        artifacts = {
            f"exec-{index}.json": _json.dumps(entry, sort_keys=True, default=str)
            for index, entry in enumerate(session.transcript)
        }
        if len(artifacts) > limits.max_artifacts:
            raise LimitViolationError("artifact cap exceeded")
        return artifacts

    def destroy(self, handle: str) -> None:
        session = self._sessions.get(handle)
        if session is None or session.destroyed:
            raise SessionError(f"unknown or destroyed session: {handle!r}")
        session.transcript.clear()
        session.destroyed = True
        del self._sessions[handle]

    # -- real container path ---------------------------------------------
    def _check_argv(self, argv: list[str]) -> list[str]:
        return check_container_argv(argv, self._real_commands)

    def _create_container(
        self, docker_env: list[str]
    ) -> subprocess.CompletedProcess[str]:
        limits = self._constraints.limits
        base = [
            "create",
            "--pull", "never",
            "--network", "none",
            "--memory", f"{limits.max_memory_mb}m",
            "--memory-swap", f"{limits.max_memory_mb}m",
            "--cpus", "1",
            "--pids-limit", "256",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--label", "unbodge-phase2=true",
            "--entrypoint", "python",
            *docker_env,
            self._image,
            "/work/_unbodge_entry.py",
        ]
        created = _docker(*base)
        if created.returncode != 0 and "unknown flag" in created.stderr:
            fallback = [arg for arg in base if arg not in ("--pull", "never")]
            created = _docker(*fallback)
        return created

    @staticmethod
    def _check_files(files: Mapping[str, str]) -> dict[str, str]:
        return check_container_files(files)

    def run_container(
        self,
        files: Mapping[str, str],
        argv: list[str],
        env: Mapping[str, str] | None = None,
        *,
        timeout_s: float | None = None,
    ) -> ContainerResult:
        """Execute ``argv`` in a throwaway container with ``files`` staged."""
        limits = self._constraints.limits
        clean_argv = self._check_argv(list(argv))
        staged = self._check_files(files)
        clean_env = sanitize_env(dict(env or {}), self._constraints.allowed_env_keys)
        for key, value in clean_env.items():
            if any(c in value for c in ("\x00", "\n", "\r")):
                raise CommandRejectedError(f"env value for {key!r} contains control chars")
        deadline = timeout_s if timeout_s is not None else float(limits.timeout_s)
        if deadline <= 0:
            raise LimitViolationError(f"non-positive timeout: {deadline!r}")
        self.ensure_image()

        staged["_unbodge_entry.py"] = _ENTRY_SHIM_TEMPLATE
        staged["_unbodge_argv.json"] = json.dumps({"argv": clean_argv})

        stage = Path(tempfile.mkdtemp(prefix="unbodge-docker-"))
        container_id: str | None = None
        try:
            for rel, content in staged.items():
                target = stage / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="\n")
            docker_env = ["-e", "PYTHONDONTWRITEBYTECODE=1"]
            for key in sorted(clean_env):
                docker_env += ["-e", f"{key}={clean_env[key]}"]
            created = self._create_container(docker_env)
            if created.returncode != 0:
                raise SandboxError(f"docker create failed: {created.stderr.strip()[:300]}")
            container_id = created.stdout.strip()
            if not re.fullmatch(r"[0-9a-f]{64}", container_id):
                raise SandboxError("docker returned a malformed container id")
            started = time.perf_counter()
            copied = _docker("cp", f"{stage}{os.sep}.", f"{container_id}:/work/")
            if copied.returncode != 0:
                raise SandboxError(f"docker cp in failed: {copied.stderr.strip()[:300]}")
            started_run = _docker("start", container_id)
            if started_run.returncode != 0:
                raise SandboxError(f"docker start failed: {started_run.stderr.strip()[:300]}")
            try:
                _docker("wait", container_id, timeout_s=max(1, math.ceil(deadline)))
            except LimitViolationError:
                _docker("kill", container_id)
                raise LimitViolationError(f"container exceeded {deadline}s timeout")
            duration = time.perf_counter() - started
            cap = limits.max_output_bytes
            stdout = self._cp_text(container_id, "/work/_unbodge_out.bin", cap)
            stderr = self._cp_text(container_id, "/work/_unbodge_err.bin", cap)
            try:
                exit_code = int(self._cp_text(container_id, "/work/_unbodge_exit", 64).strip())
            except ValueError:
                logs = _docker("logs", container_id)
                raise SandboxError(
                    "container entry failed: "
                    f"{logs.stdout.strip()[-500:]} {logs.stderr.strip()[-500:]}"
                )
            if len(stdout.encode()) + len(stderr.encode()) > cap:
                raise LimitViolationError("container output exceeds cap")
            artifacts = self._cp_artifacts(
                container_id, limits.max_artifacts, cap, set(staged)
            )
            environment = dict(clean_env)
            environment["PYTHONDONTWRITEBYTECODE"] = "1"
            return ContainerResult(
                stdout=stdout, stderr=stderr, exit_code=exit_code,
                duration_s=duration, environment=environment, artifacts=artifacts,
            )
        finally:
            if container_id:
                _docker("rm", "-f", container_id)
            shutil.rmtree(stage, ignore_errors=True)

    def _cp_text(self, container_id: str, remote: str, byte_cap: int) -> str:
        with tempfile.TemporaryDirectory(prefix="unbodge-cp-") as tmp:
            result = _docker("cp", f"{container_id}:{remote}", tmp)
            if result.returncode != 0:
                raise SandboxError(f"docker cp out failed for {remote}: {result.stderr[:200]}")
            target = Path(tmp) / Path(remote).name
            if target.is_symlink():
                raise SandboxError(f"container returned a symlink: {remote}")
            if target.stat().st_size > byte_cap:
                raise LimitViolationError(f"container output {remote} exceeds cap")
            data = target.read_bytes()
        return data.decode("utf-8", errors="replace")

    def _cp_artifacts(
        self, container_id: str, max_artifacts: int, byte_cap: int, staged: set[str]
    ) -> dict[str, str]:
        """Collect files the container created (staged inputs are skipped)."""
        with tempfile.TemporaryDirectory(prefix="unbodge-art-") as tmp:
            result = _docker("cp", f"{container_id}:/work/.", tmp)
            if result.returncode != 0:
                return {}
            artifacts: dict[str, str] = {}
            total = 0
            scanned = 0
            for path in sorted(Path(tmp).rglob("*")):
                scanned += 1
                if scanned > _MAX_ARTIFACT_SCAN:
                    raise LimitViolationError("container artifact scan exceeds cap")
                if not path.is_file() or path.is_symlink():
                    continue
                if path.name.startswith("_unbodge_"):
                    continue
                rel = path.relative_to(tmp).as_posix()
                if rel in staged:
                    continue
                if "__pycache__" in Path(rel).parts or Path(rel).parts[0].startswith("."):
                    continue
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                if size > _MAX_CONTAINER_FILE_BYTES:
                    continue
                total += size
                if total > byte_cap:
                    raise LimitViolationError("container artifacts exceed cap")
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                artifacts[rel] = text
                if len(artifacts) >= max_artifacts:
                    break
            return artifacts


__all__ = ["ContainerResult", "DockerSandbox", "docker_available"]
