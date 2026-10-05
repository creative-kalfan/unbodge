"""Real counterfactual execution over checked-out history (Phase 2).

Same A/B/C/D contract as the synthetic proof, but cells are materialized
from real repository states: the OLD/NEW revisions are archived to
workdirs, the workaround patch is applied for the PRESENT cells, and a
real probe command executes inside the Docker sandbox. Every run carries
full provenance (command, exit, streams, duration, dependency state,
Git SHA, environment, artifacts, hashes).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Mapping

from domain.enums import DependencyVersion, TestStatus, UniverseCell, WorkaroundState
from domain.errors import DomainError
from domain.models import ExperimentRun
from evidence.hashing import sha256_hex
from experiments.contracts import CounterfactualResult
from github.git import GitRepo
from sandbox.docker import DockerSandbox

_CELL_REV: dict[UniverseCell, str] = {
    UniverseCell.A: "old",
    UniverseCell.B: "old",
    UniverseCell.C: "new",
    UniverseCell.D: "new",
}

MAX_STAGED_FILES = 256
MAX_STAGED_BYTES = 1_000_000
MAX_PATCH_BYTES = 256 * 1024
SKIP_DIR_NAMES = frozenset({".git", "__pycache__"})


def _check_patch_paths(patch_text: str) -> None:
    """Reject patches touching absolute, escaping, or empty paths."""
    for line in patch_text.splitlines():
        if line.startswith(("--- ", "+++ ")):
            path = line[4:].strip()
            if path in ("/dev/null", "dev/null"):
                continue
            clean = path[2:] if path[:2] in ("a/", "b/") else path
            if (
                not clean
                or clean.startswith("/")
                or "\\" in clean
                or ".." in Path(clean).parts
            ):
                raise DomainError(f"unsafe patch path: {line!r}")


def apply_patch(workdir: str | Path, patch_text: str, *, reverse: bool = False) -> None:
    """Apply a unified diff inside ``workdir`` via ``git apply`` (no shell)."""
    if not patch_text.strip():
        raise DomainError("workaround patch must be non-empty")
    if len(patch_text.encode("utf-8")) > MAX_PATCH_BYTES:
        raise DomainError("workaround patch exceeds size cap")
    _check_patch_paths(patch_text)
    args = ["git", "apply", "--whitespace=nowarn"]
    if reverse:
        args.append("-R")
    args.append("-")
    completed = subprocess.run(
        args,
        cwd=workdir,
        input=patch_text.encode("utf-8"),
        capture_output=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()[:300]
        raise DomainError(f"workaround patch does not apply: {detail}")


def patch_marker_files(patch_text: str) -> list[str]:
    """Paths the patch creates (``+++ b/<path>`` without a real ``---`` side).

    Only clean relative paths are returned; anything else is rejected.
    """
    markers: list[str] = []
    old: str | None = None
    for line in patch_text.splitlines():
        if line.startswith("--- "):
            old = line[4:].strip()
        elif line.startswith("+++ "):
            new = line[4:].strip()
            for prefix in ("b/", "a/"):
                if new.startswith(prefix):
                    new = new[len(prefix):]
                    break
            if old in ("/dev/null", "dev/null") and new not in ("/dev/null", "dev/null"):
                if (
                    not new
                    or new.startswith("/")
                    or "\\" in new
                    or ".." in Path(new).parts
                ):
                    raise DomainError(f"unsafe patch marker path: {new!r}")
                markers.append(new)
            old = None
    return markers


def prepare_cell_workdir(
    git: GitRepo,
    rev: str,
    dest: str | Path,
    *,
    workaround_patch: str | None = None,
    reverse: bool = False,
) -> Path:
    """Archive ``rev`` to ``dest`` and optionally apply the workaround patch."""
    workdir = git.archive_to(rev, dest)
    if workaround_patch is not None:
        apply_patch(workdir, workaround_patch, reverse=reverse)
    return workdir


def ensure_workaround_state(
    workdir: str | Path, workaround_patch: str, present: bool
) -> None:
    """Make the workaround present/absent, whichever needs doing.

    Presence is determined by the patch's created files: a PRESENT cell
    applies the patch only when markers are missing; an ABSENT cell
    reverse-applies only when markers exist. Anything else is an error.
    """
    markers = patch_marker_files(workaround_patch)
    if not markers:
        raise DomainError("workaround patch creates no files")
    base = Path(workdir)
    have = [m for m in markers if (base / m).exists()]
    if present and len(have) < len(markers):
        apply_patch(workdir, workaround_patch)
    elif not present and have:
        apply_patch(workdir, workaround_patch, reverse=True)
    _reject_symlinks(base)


def _reject_symlinks(base: Path) -> None:
    """Refuse symlinks anywhere under a prepared workdir."""
    for path in base.rglob("*"):
        if path.is_symlink():
            raise DomainError(f"symlink refused in workdir: {path.name!r}")


def read_workdir_files(workdir: str | Path) -> dict[str, str]:
    """Read a workdir as ``{relpath: text}`` (text-only, capped)."""
    base = Path(workdir)
    staged: dict[str, str] = {}
    total = 0
    for path in sorted(base.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        rel_parts = path.relative_to(base).parts
        if any(part in SKIP_DIR_NAMES or part.startswith(".") for part in rel_parts):
            continue
        if len(staged) >= MAX_STAGED_FILES:
            raise DomainError("workdir exceeds staged file cap")
        try:
            if path.stat().st_size > MAX_STAGED_BYTES:
                raise DomainError(f"workdir file too large: {path.name!r}")
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        total += len(text.encode("utf-8"))
        if total > MAX_STAGED_BYTES:
            raise DomainError("workdir exceeds staged byte cap")
        staged[path.relative_to(base).as_posix()] = text
    return staged


def dependency_label_at(git: GitRepo, rev: str, package: str = "fake-dep") -> str:
    """Derive ``pkg==ver`` from requirements.txt at ``rev`` (best effort)."""
    try:
        text = git.file_at(rev, "requirements.txt")
    except Exception:
        return f"{package}==unknown"
    wanted = package.lower().replace("_", "-")
    for line in text.splitlines():
        name, sep, version = line.strip().partition("==")
        if sep and name.strip().lower().replace("_", "-") == wanted:
            parts = version.strip().split()
            ver = parts[0] if parts else "unknown"
            return f"{package}=={ver}"
    return f"{package}==unknown"


def run_real_suite(
    *,
    git: GitRepo,
    repository_id: str,
    old_rev: str,
    new_rev: str,
    workaround_patch: str | None,
    probe_argv: list[str],
    probe_env: Mapping[str, str] | None = None,
    sandbox: DockerSandbox,
    plan_id: str = "real:1",
    timeout_s: float = 60,
    package: str = "fake-dep",
) -> CounterfactualResult:
    """Execute the four real cells and return the counterfactual result."""
    revs = {"old": git.rev_parse(old_rev), "new": git.rev_parse(new_rev)}
    runs: dict[UniverseCell, ExperimentRun] = {}
    with TemporaryDirectory(prefix="unbodge-real-") as tmp:
        for cell in UniverseCell:
            which = _CELL_REV[cell]
            present = cell.workaround == WorkaroundState.PRESENT
            workdir = prepare_cell_workdir(git, revs[which], Path(tmp) / f"cell-{cell.value}")
            if workaround_patch is None:
                if present:
                    raise DomainError(f"cell {cell.value} needs a workaround patch")
            else:
                ensure_workaround_state(workdir, workaround_patch, present)
            files = read_workdir_files(workdir)
            dependency = cell.dependency
            container = sandbox.run_container(
                files, list(probe_argv), dict(probe_env or {}), timeout_s=timeout_s
            )
            status = TestStatus.PASS if container.exit_code == 0 else TestStatus.FAIL
            label = dependency_label_at(git, revs[which], package)
            environment = dict(container.environment)
            environment["DEP_VERSION"] = dependency.value
            environment["WORKAROUND"] = cell.workaround.value
            environment["UNIVERSE_CELL"] = cell.value
            spec_id = f"{plan_id}:cell:{cell.value}"
            transcript = "\n".join(
                [spec_id, " ".join(probe_argv), container.stdout, container.stderr,
                 str(container.exit_code)]
            )
            artifact_hashes = {"transcript": sha256_hex(transcript)}
            artifact_hashes.update(
                {
                    name: sha256_hex(content)
                    for name, content in sorted(container.artifacts.items())
                }
            )
            runs[cell] = ExperimentRun(
                id=f"{spec_id}:run",
                spec_id=spec_id,
                cell=cell,
                command=" ".join(probe_argv),
                stdout=container.stdout,
                stderr=container.stderr,
                exit_code=container.exit_code,
                duration_s=max(container.duration_s, 0.0),
                status=status,
                environment=environment,
                git_sha=revs[which],
                dependency_state={package: label},
                test_report={"status": status.value, "exit_code": container.exit_code},
                artifact_hashes=artifact_hashes,
            )
    return CounterfactualResult(runs=runs)


__all__ = [
    "apply_patch",
    "dependency_label_at",
    "ensure_workaround_state",
    "patch_marker_files",
    "prepare_cell_workdir",
    "read_workdir_files",
    "run_real_suite",
]
