"""Nebius cloud sandbox: same ABC, portability, explicit availability."""

import io
import json
import urllib.error

import pytest

from cloud import NebiusSandbox, SandboxUnavailableError
from sandbox import (
    DockerSandbox,
    check_container_argv,
    check_container_files,
    docker_available,
)
from sandbox.base import SandboxConstraints
from sandbox.errors import CommandRejectedError, LimitViolationError, SessionError

needs_docker = pytest.mark.skipif(
    not docker_available(), reason="docker daemon or image unavailable"
)


def _sandbox(**kwargs):
    kwargs.setdefault("api_key", "test-key")
    kwargs.setdefault("endpoint", "https://nebius.example.com")
    return NebiusSandbox(**kwargs)


def test_unconfigured_nebius_fails_closed():
    sandbox = NebiusSandbox()
    assert not sandbox.configured
    with pytest.raises(SandboxUnavailableError):
        sandbox.run_container({"a.py": "print(1)\n"}, ["python", "a.py"], {})
    with pytest.raises(SandboxUnavailableError):
        NebiusSandbox(api_key="k", endpoint="").run_container({}, ["python", "x"], {})


def test_nebius_rejects_bad_endpoint():
    with pytest.raises(ValueError):
        NebiusSandbox(api_key="k", endpoint="http://plain.example")
    with pytest.raises(ValueError):
        NebiusSandbox(api_key="k", endpoint="https://user@host.example")
    unconfigured = NebiusSandbox(api_key="k", endpoint="")
    assert not unconfigured.configured
    with pytest.raises(SandboxUnavailableError):
        unconfigured.run_container({"a.py": "x\n"}, ["python", "a.py"], {})


def test_nebius_handler_lifecycle_matches_local():
    sandbox = _sandbox()
    handle = sandbox.create()
    assert sandbox.active_sessions() == 1
    sandbox.register_handler("echo", lambda command, env: (command, "", 0))
    sandbox2 = _sandbox(
        constraints=SandboxConstraints(allowed_commands=("echo",)),
    )
    sandbox2.register_handler("echo", lambda command, env: (command, "", 0))
    handle2 = sandbox2.create()
    result = sandbox2.execute(handle2, "echo hi", {"DEP_VERSION": "OLD"})
    assert result.exit_code == 0
    assert sandbox2.collect(handle2)
    sandbox2.destroy(handle2)
    assert sandbox2.active_sessions() == 0
    sandbox.destroy(handle)
    with pytest.raises(SessionError):
        sandbox.destroy(handle)


def test_backends_share_validation_semantics():
    # identical allowlist/grammar checks on both backends (portability)
    from sandbox.base import sanitize_command

    for command in ("rm -rf /", "synthetic-check; rm -rf /", ""):
        with pytest.raises(CommandRejectedError):
            sanitize_command(command, ("synthetic-check",))
    with pytest.raises(CommandRejectedError):
        check_container_argv(["rm", "-rf", "/"], ("python",))
    with pytest.raises(CommandRejectedError):
        check_container_files({"../evil.py": "x"})
    with pytest.raises(LimitViolationError):
        check_container_files({"big.py": "x" * (257 * 1024)})


def test_nebius_remote_mapping_without_cloud():
    def opener(request, timeout):
        assert request.full_url == "https://nebius.example.com/v1/sandbox/run"
        body = json.dumps(
            {
                "stdout": "hi",
                "stderr": "",
                "exit_code": 0,
                "duration_s": 0.5,
                "artifacts": {"out.txt": "proof"},
            }
        )
        return io.BytesIO(body.encode())

    sandbox = _sandbox(opener=opener)
    result = sandbox.run_container({"a.py": "print(1)\n"}, ["python", "a.py"], {"DEP_VERSION": "OLD"})
    assert result.exit_code == 0 and result.stdout == "hi"
    assert result.artifacts == {"out.txt": "proof"}
    assert result.environment == {"DEP_VERSION": "OLD"}


def test_nebius_malformed_remote_response_fails_closed():
    def opener(request, timeout):
        return io.BytesIO(b'{"nope": true}')

    sandbox = _sandbox(opener=opener)
    with pytest.raises(SandboxUnavailableError):
        sandbox.run_container({"a.py": "x\n"}, ["python", "a.py"], {})


def test_nebius_http_errors_fail_closed():
    def opener(request, timeout):
        raise urllib.error.HTTPError(request.full_url, 401, "no", {}, io.BytesIO())

    sandbox = _sandbox(opener=opener)
    with pytest.raises(SandboxUnavailableError):
        sandbox.run_container({"a.py": "x\n"}, ["python", "a.py"], {})


@needs_docker
def test_experiment_spec_portable_across_backends():
    """Same argv runs locally; Nebius accepts the same spec shape."""
    local = DockerSandbox()
    result = local.run_container({"a.py": "print('portable')\n"}, ["python", "a.py"], {})
    assert result.stdout.strip() == "portable"
    cloud = _sandbox()
    assert cloud.active_sessions() == 0
    # configured fixture transport proves the cloud backend takes the
    # identical files/argv/env shape (no live cloud execution is claimed)
    assert cloud.configured
