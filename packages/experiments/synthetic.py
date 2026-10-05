"""Deterministic synthetic dependency scenario (Phase 1).

Fake history, fully offline:

- OLD ``profile_nickname`` reads ``profile["nickname"]`` directly and raises
  ``KeyError`` for profiles without a nickname (the simulated upstream bug).
- The downstream workaround wraps the call and falls back to ``"anonymous"``.
- NEW ``profile_nickname`` already defaults to ``"anonymous"`` (upstream fix).

Resulting proof matrix:

- OLD + workaround        -> PASS
- OLD + no workaround     -> FAIL
- NEW + workaround        -> PASS
- NEW + no workaround     -> PASS
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from domain.enums import DependencyVersion, TestStatus, WorkaroundState
from sandbox.errors import CommandRejectedError

FALLBACK_NICKNAME = "anonymous"

#: Profiles exercised by the checks. The empty profile triggers the OLD bug.
PROBE_PROFILE: dict[str, str] = {}

REGRESSION_PROFILES: tuple[dict[str, str], ...] = (
    {},
    {"nickname": "ada"},
    {"nickname": ""},
    {"nickname": "grace"},
    {},
)

OLD_DEPENDENCY_LABEL = "fake-dep==1.0-buggy"
NEW_DEPENDENCY_LABEL = "fake-dep==1.1-fixed"

SYNTHETIC_COMMANDS = ("synthetic-check", "regression-suite")

_COMMAND_RE = re.compile(
    r"^(?P<tool>[a-z][a-z-]*)\s+--dep\s+(?P<dep>OLD|NEW)"
    r"\s+--workaround\s+(?P<ws>PRESENT|ABSENT)\s*$"
)


def old_profile_nickname(profile: Mapping[str, str]) -> str:
    """OLD dependency behaviour: raises KeyError when nickname is absent."""
    return profile["nickname"]


def new_profile_nickname(profile: Mapping[str, str]) -> str:
    """NEW dependency behaviour: upstream fix, safe default."""
    return profile.get("nickname", FALLBACK_NICKNAME)


def workaround_profile_nickname(profile: Mapping[str, str]) -> str:
    """Downstream workaround around the OLD bug."""
    try:
        return old_profile_nickname(profile)
    except KeyError:
        return FALLBACK_NICKNAME


def resolve_nickname(
    dependency: DependencyVersion, workaround: WorkaroundState, profile: Mapping[str, str]
) -> str:
    if dependency == DependencyVersion.NEW:
        return new_profile_nickname(profile)
    if workaround == WorkaroundState.PRESENT:
        return workaround_profile_nickname(profile)
    return old_profile_nickname(profile)


@dataclass(frozen=True)
class SyntheticOutcome:
    stdout: str
    stderr: str
    exit_code: int
    status: TestStatus
    duration_s: float = 0.0


@dataclass(frozen=True)
class RegressionOutcome:
    suite: str
    passed: int
    failed: int
    status: TestStatus
    stdout: str
    stderr: str
    exit_code: int
    duration_s: float = 0.0


def run_synthetic(
    dependency: DependencyVersion,
    workaround: WorkaroundState,
    profile: Mapping[str, str] | None = None,
) -> SyntheticOutcome:
    target = dict(PROBE_PROFILE if profile is None else profile)
    try:
        nickname = resolve_nickname(dependency, workaround, target)
    except KeyError as exc:
        return SyntheticOutcome(
            stdout="",
            stderr=f"KeyError: {exc} (simulated upstream bug in {OLD_DEPENDENCY_LABEL})",
            exit_code=1,
            status=TestStatus.FAIL,
        )
    return SyntheticOutcome(
        stdout=f"ok nickname={nickname}",
        stderr="",
        exit_code=0,
        status=TestStatus.PASS,
    )


def run_regression_checks(
    dependency: DependencyVersion,
    workaround: WorkaroundState,
    suite: str = "fake-dep-probes",
) -> RegressionOutcome:
    passed = 0
    failed = 0
    for profile in REGRESSION_PROFILES:
        try:
            resolve_nickname(dependency, workaround, profile)
            passed += 1
        except KeyError:
            failed += 1
    status = TestStatus.PASS if (failed == 0 and passed > 0) else TestStatus.FAIL
    code = 0 if status == TestStatus.PASS else 1
    return RegressionOutcome(
        suite=suite,
        passed=passed,
        failed=failed,
        status=status,
        stdout=f"suite {suite}: passed={passed} failed={failed}",
        stderr="" if code == 0 else "regression failures detected",
        exit_code=code,
    )


def parse_synthetic_command(command: str) -> tuple[str, DependencyVersion, WorkaroundState]:
    """Parse ``<tool> --dep OLD|NEW --workaround PRESENT|ABSENT``."""
    match = _COMMAND_RE.match(command.strip())
    if match is None:
        raise CommandRejectedError(f"malformed synthetic command: {command!r}")
    tool = match.group("tool")
    if tool not in SYNTHETIC_COMMANDS:
        raise CommandRejectedError(f"unknown synthetic tool: {tool!r}")
    return (
        tool,
        DependencyVersion(match.group("dep")),
        WorkaroundState(match.group("ws")),
    )


def synthetic_handler(
    command: str, env: Mapping[str, str]
) -> tuple[str, str, int]:
    tool, dependency, workaround = parse_synthetic_command(command)
    if tool != "synthetic-check":
        raise CommandRejectedError(f"synthetic handler cannot run {tool!r}")
    outcome = run_synthetic(dependency, workaround)
    return outcome.stdout, outcome.stderr, outcome.exit_code


def regression_handler(
    command: str, env: Mapping[str, str]
) -> tuple[str, str, int]:
    tool, dependency, workaround = parse_synthetic_command(command)
    if tool != "regression-suite":
        raise CommandRejectedError(f"regression handler cannot run {tool!r}")
    outcome = run_regression_checks(dependency, workaround)
    return outcome.stdout, outcome.stderr, outcome.exit_code