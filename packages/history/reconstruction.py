"""Historical reconstruction over a local git repository (Phase 2).

Answers, deterministically and offline:
1. What repository state existed at commit/tag X? (resolved SHA + tree)
2. What dependency version was active? (parsed lock at that rev)
3. Can it be installed/reproduced? (pins known to the package index)
4. What was the workaround code at that point? (scan of archived tree)
5. What changed between old and new states? (dependency diff)
"""

from __future__ import annotations

from pathlib import Path

from analysis.scanner import scan_tree
from domain.models import WorkaroundCandidate
from github.errors import GitError, GitHubNotFoundError
from github.git import GitRepo
from history.pins import (
    parse_pyproject_dependencies,
    parse_requirements_text,
    parse_setup_cfg,
)
from history.states import (
    DependencyDiff,
    DependencyLock,
    HistoricalState,
    HistoryError,
    InstallabilityReport,
)
from pypi.base import PackageNotFoundError, PyPIClient, normalize_name

LOCK_FILES = ("requirements.txt", "requirements/base.txt", "pyproject.toml", "setup.cfg")

_MAX_LOCK_BYTES = 1_000_000


def _is_lock_file(rel: str) -> bool:
    base = rel.rsplit("/", 1)[-1]
    return (base.startswith("requirements") and base.endswith(".txt")) or rel in (
        "pyproject.toml",
        "setup.cfg",
    )


def _lock_from_tree(files: dict[str, bytes]) -> tuple[DependencyLock, list[str]]:
    """Merge pins from lock files (sorted for determinism; later wins)."""
    packages: dict[str, str] = {}
    sources: list[str] = []
    constraints: list[str] = []
    for name in sorted(files):
        data = files[name]
        if name.endswith(".txt"):
            parsed = parse_requirements_text(data.decode("utf-8", errors="replace"), name)
        elif name.endswith(".toml"):
            parsed = parse_pyproject_dependencies(data, name)
        else:
            parsed = parse_setup_cfg(data, name)
        sources.append(name)
        for pin in parsed.pins:
            packages[normalize_name(pin.package)] = pin.version
        constraints.extend(parsed.constraints)
    return DependencyLock(packages=packages, source_files=sources), constraints


class Reconstructor:
    """Reconstructs explicit historical states from a ``GitRepo``."""

    def __init__(self, repo: GitRepo, repository_id: str) -> None:
        self._repo = repo
        self._repository_id = repository_id

    def _tree_files(self, sha: str) -> dict[str, bytes]:
        files: dict[str, bytes] = {}
        for rel in self._repo.list_files_at(sha):
            if not _is_lock_file(rel):
                continue
            try:
                if self._repo.blob_size(sha, rel) > _MAX_LOCK_BYTES:
                    continue
                files[rel] = self._repo.file_at(sha, rel).encode("utf-8")
            except GitHubNotFoundError:
                continue
        return files

    def state_at(self, rev: str, *, tag: str | None = None) -> HistoricalState:
        try:
            sha = self._repo.rev_parse(rev)
        except GitError as exc:
            raise HistoryError(f"cannot resolve revision {rev!r}: {exc}") from exc
        lock, constraints = _lock_from_tree(self._tree_files(sha))
        return HistoricalState(
            id=f"state:{self._repository_id}:{sha[:12]}",
            repository_id=self._repository_id,
            git_sha=sha,
            tag=tag,
            lock=lock,
            constraints=constraints,
        )

    def diff_states(self, old: HistoricalState, new: HistoricalState) -> DependencyDiff:
        added = {k: v for k, v in new.lock.packages.items() if k not in old.lock.packages}
        removed = {k: v for k, v in old.lock.packages.items() if k not in new.lock.packages}
        changed = {
            k: (old.lock.packages[k], new.lock.packages[k])
            for k in old.lock.packages
            if k in new.lock.packages and old.lock.packages[k] != new.lock.packages[k]
        }
        return DependencyDiff(
            old_sha=old.git_sha, new_sha=new.git_sha,
            added=added, removed=removed, changed=changed,
        )

    def check_installable(
        self, state: HistoricalState, index: PyPIClient
    ) -> InstallabilityReport:
        """Conservative rule: every pinned version must exist in the index."""
        missing: list[str] = []
        notes: list[str] = []
        for name, version in sorted(state.lock.packages.items()):
            try:
                index.get_release(name, version)
            except PackageNotFoundError:
                missing.append(f"{name}=={version}")
        if state.constraints:
            notes.append(f"{len(state.constraints)} unbounded constraints (not pinned)")
        if not state.lock.packages:
            notes.append("no dependency pins found at this state")
        return InstallabilityReport(
            state_id=state.id,
            installable=not missing and bool(state.lock.packages),
            missing=missing,
            notes=notes,
        )

    def workaround_at(
        self, rev: str, dest: str | Path, *, max_files: int = 1000
    ) -> list[WorkaroundCandidate]:
        """Scan the archived tree at ``rev`` for workaround candidates."""
        sha = self._repo.rev_parse(rev)
        tree = self._repo.archive_to(sha, dest)
        return scan_tree(tree, self._repository_id, max_files=max_files)


__all__ = ["LOCK_FILES", "Reconstructor"]
