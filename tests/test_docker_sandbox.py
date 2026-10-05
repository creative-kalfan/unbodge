"""Phase 2 real sandbox: Docker/OCI isolation, live but offline-safe.

All container tests use the pre-pulled ``python:3.11-slim`` image and
``--network none``; nothing leaves the machine. Skipped gracefully when
no daemon/image is available.
"""

import subprocess

import pytest

from sandbox.base import ResourceLimits, SandboxConstraints
from sandbox.docker import DockerSandbox, docker_available
from sandbox.errors import CommandRejectedError, LimitViolationError, SandboxError

needs_docker = pytest.mark.skipif(
    not docker_available(), reason="docker daemon or image unavailable"
)


def _sandbox(**kwargs) -> DockerSandbox:
    return DockerSandbox(**kwargs)


def test_handler_path_matches_phase1_lifecycle():
    sandbox = _sandbox(
        constraints=SandboxConstraints(allowed_commands=("echo",)),
    )
    handle = sandbox.create()
    assert sandbox.active_sessions() == 1
    sandbox.register_handler("echo", lambda command, env: (command, "", 0))
    result = sandbox.execute(handle, "echo hello", {"DEP_VERSION": "OLD"})
    assert result.exit_code == 0 and result.stdout == "echo hello"
    assert sandbox.collect(handle)
    sandbox.destroy(handle)
    assert sandbox.active_sessions() == 0


@needs_docker
def test_run_container_executes_real_code():
    sandbox = _sandbox()
    result = sandbox.run_container(
        {"hello.py": "print('hi from container')\n"},
        ["python", "hello.py"],
        {"DEP_VERSION": "OLD"},
    )
    assert result.exit_code == 0
    assert result.stdout.strip() == "hi from container"
    assert result.environment["DEP_VERSION"] == "OLD"
    assert result.environment["PYTHONDONTWRITEBYTECODE"] == "1"
    assert sandbox.active_sessions() == 0


@needs_docker
def test_run_container_separates_streams_and_exit_code():
    sandbox = _sandbox()
    result = sandbox.run_container(
        {},
        ["python", "-c", "import sys; sys.stderr.write('boom'); sys.exit(3)"],
        {},
    )
    assert result.exit_code == 3
    assert result.stdout == ""
    assert result.stderr == "boom"


@needs_docker
def test_run_container_rejects_unallowlisted_commands():
    sandbox = _sandbox()
    with pytest.raises(CommandRejectedError):
        sandbox.run_container({}, ["rm", "-rf", "/"], {})
    with pytest.raises(CommandRejectedError):
        sandbox.run_container({"../evil.py": "x"}, ["python", "x.py"], {})
    with pytest.raises(CommandRejectedError):
        sandbox.run_container({"/abs.py": "x"}, ["python", "x.py"], {})
    with pytest.raises(CommandRejectedError):
        sandbox.run_container({}, ["python", "x\x00.py"], {})


@needs_docker
def test_run_container_sanitizes_env():
    sandbox = _sandbox()
    code = (
        "import json, os; print(json.dumps({k: v for k, v in os.environ.items() "
        "if k in ('DEP_VERSION', 'SECRET_TOKEN', 'AWS_X')}))"
    )
    result = sandbox.run_container(
        {},
        ["python", "-c", code],
        {"DEP_VERSION": "OLD", "SECRET_TOKEN": "shh", "AWS_X": "shh"},
    )
    assert result.exit_code == 0
    assert '"DEP_VERSION": "OLD"' in result.stdout
    assert "SECRET_TOKEN" not in result.stdout
    assert "AWS_X" not in result.stdout


@needs_docker
def test_run_container_timeout_kills():
    sandbox = _sandbox()
    with pytest.raises(LimitViolationError):
        sandbox.run_container(
            {},
            ["python", "-c", "import time; time.sleep(30)"],
            {},
            timeout_s=6,
        )


@needs_docker
def test_run_container_has_no_network():
    sandbox = _sandbox()
    code = (
        "import socket; s = socket.create_connection(('8.8.8.8', 53), timeout=3); "
        "print('EGRESS')"
    )
    result = sandbox.run_container({}, ["python", "-c", code], {})
    assert result.exit_code != 0
    assert "EGRESS" not in result.stdout


@needs_docker
def test_run_container_output_cap():
    sandbox = _sandbox(
        constraints=SandboxConstraints(limits=ResourceLimits(max_output_bytes=1024))
    )
    with pytest.raises(LimitViolationError):
        sandbox.run_container(
            {}, ["python", "-c", "print('B' * 100000)"], {}
        )


@needs_docker
def test_run_container_collects_artifacts():
    sandbox = _sandbox()
    result = sandbox.run_container(
        {"make.py": "from pathlib import Path; Path('/work/out.txt').write_text('proof')\n"},
        ["python", "make.py"],
        {},
    )
    assert result.exit_code == 0
    assert result.artifacts.get("out.txt") == "proof"
    assert not [k for k in result.artifacts if "_unbodge_" in k]


@needs_docker
def test_run_container_cleans_up():
    sandbox = _sandbox()
    before = _labeled_containers()
    sandbox.run_container({"a.py": "print(1)\n"}, ["python", "a.py"], {})
    sandbox.run_container({"a.py": "print(1)\n"}, ["python", "a.py"], {})
    assert _labeled_containers() == before


def _labeled_containers() -> set[str]:
    completed = subprocess.run(
        ["docker", "ps", "-aq", "--filter", "label=unbodge-phase2=true"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    return {line for line in completed.stdout.splitlines() if line.strip()}


@needs_docker
def test_missing_image_fails_closed_without_pull():
    sandbox = _sandbox(image="unbodge-does-not-exist:xyz")
    with pytest.raises(SandboxError):
        sandbox.run_container({"a.py": "print(1)\n"}, ["python", "a.py"], {})


def test_missing_daemon_fails_closed(monkeypatch):
    import sandbox.docker as docker_module

    monkeypatch.setattr(docker_module.shutil, "which", lambda _: None)
    with pytest.raises(SandboxError):
        DockerSandbox()
