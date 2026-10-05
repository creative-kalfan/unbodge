"""Local git history adapter (Phase 2).

Real ``git`` history reads (and local branch/commit creation) through
fixed argv vectors -- never a shell. Untrusted inputs (revs, paths,
branch names, messages) are validated before they reach the CLI.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

from github.errors import GitError, GitHubNotFoundError

_REV_BASE_RE = re.compile(r"^[A-Za-z0-9_./-]+$")
_REV_SUFFIX_RE = re.compile(r"^([~^][0-9]*)*$")
_BRANCH_RE = re.compile(r"^[A-Za-z0-9_./-]+$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_GIT_TIMEOUT_S = 60
_MAX_ARCHIVE_BYTES = 100 * 1024 * 1024
_MAX_ARCHIVE_MEMBERS = 10000


def _check_rev(rev: str) -> str:
    """Allow a plain ref plus ``~n``/``^n`` ancestry suffixes (no ranges)."""
    if not rev or rev.startswith(("-", ".", "/")):
        raise GitError(f"unsafe git revision: {rev!r}")
    base, suffix = rev, ""
    for sep in ("~", "^"):
        if sep in rev:
            head, _, tail = rev.partition(sep)
            base, suffix = head, sep + tail
            break
    if not _REV_BASE_RE.fullmatch(base) or not _REV_SUFFIX_RE.fullmatch(suffix):
        raise GitError(f"unsafe git revision: {rev!r}")
    if ".." in base:
        raise GitError(f"unsafe git revision: {rev!r}")
    return rev


def _check_branch(branch: str) -> str:
    if not branch or not _BRANCH_RE.fullmatch(branch):
        raise GitError(f"unsafe branch name: {branch!r}")
    if ".." in branch or branch.startswith(("-", ".", "/")) or branch.endswith((".lock", "/")):
        raise GitError(f"unsafe branch name: {branch!r}")
    return branch


def _check_rel_path(path: str) -> str:
    if not path or path.startswith("/") or "\\" in path:
        raise GitError(f"unsafe repository path: {path!r}")
    if ".." in path.split("/"):
        raise GitError(f"unsafe repository path: {path!r}")
    return path


class GitRepo:
    """A local git repository checkout."""

    def __init__(self, path: str | Path) -> None:
        self._root = Path(path)
        if not (self._root / ".git").is_dir():
            raise GitError(f"not a git repository: {self._root}")

    @property
    def root(self) -> Path:
        return self._root

    def _run(self, *args: str, env: dict[str, str] | None = None) -> str:
        try:
            completed = subprocess.run(
                ["git", *args],
                cwd=self._root,
                env=env,
                capture_output=True,
                text=True,
                timeout=_GIT_TIMEOUT_S,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GitError(f"git {' '.join(args)} failed: {exc}") from exc
        if completed.returncode != 0:
            raise GitError(
                f"git {' '.join(args)} exited {completed.returncode}: "
                f"{completed.stderr.strip()[:500]}"
            )
        return completed.stdout

    def rev_parse(self, rev: str) -> str:
        """Resolve any rev (tag, branch, prefix) to a full 40-char SHA."""
        out = self._run("rev-parse", "--verify", f"{_check_rev(rev)}^{{commit}}")
        sha = out.strip()
        if not _SHA_RE.fullmatch(sha):
            raise GitError(f"could not resolve revision: {rev!r}")
        return sha

    def log_subjects(self, rev: str = "HEAD", limit: int = 50) -> list[tuple[str, str]]:
        """List ``(sha, subject)`` newest-first for a single rev (no ranges)."""
        if limit < 1 or limit > 500:
            raise GitError(f"unsafe log limit: {limit!r}")
        out = self._run("log", "--format=%H %s", f"-{limit}", _check_rev(rev))
        entries: list[tuple[str, str]] = []
        for line in out.splitlines():
            sha, _, subject = line.partition(" ")
            if _SHA_RE.fullmatch(sha):
                entries.append((sha, subject))
        return entries

    def file_at(self, rev: str, path: str) -> str:
        """Read a file as it existed at ``rev`` (traversal-safe)."""
        sha = self.rev_parse(rev)
        rel = _check_rel_path(path)
        try:
            return self._run("show", f"{sha}:{rel}")
        except GitError as exc:
            raise GitHubNotFoundError(f"file {rel!r} not present at {rev!r}") from exc

    def list_files_at(self, rev: str) -> list[str]:
        sha = self.rev_parse(rev)
        out = self._run("ls-tree", "-r", "--name-only", sha)
        return [line for line in out.splitlines() if line]

    def diff_names(self, old_rev: str, new_rev: str) -> list[str]:
        old = self.rev_parse(old_rev)
        new = self.rev_parse(new_rev)
        out = self._run("diff", "--name-only", old, new)
        return [line for line in out.splitlines() if line]

    def diff_text(self, old_rev: str, new_rev: str, path: str | None = None) -> str:
        old = self.rev_parse(old_rev)
        new = self.rev_parse(new_rev)
        args = ["diff", old, new]
        if path is not None:
            args += ["--", _check_rel_path(path)]
        return self._run(*args)

    def list_tags(self) -> list[str]:
        out = self._run("tag", "--list")
        return [line for line in out.splitlines() if line]

    def blob_size(self, rev: str, path: str) -> int:
        """Byte size of a blob at ``rev`` without fetching its content."""
        sha = self.rev_parse(rev)
        out = self._run("cat-file", "-s", f"{sha}:{_check_rel_path(path)}")
        try:
            return int(out.strip())
        except ValueError:
            raise GitError(f"cannot size blob {path!r} at {rev!r}") from None

    def archive_to(self, rev: str, dest: str | Path) -> Path:
        """Materialize the tree at ``rev`` into an empty ``dest`` (deterministic)."""
        import sys

        sha = self.rev_parse(rev)
        target = Path(dest)
        target.mkdir(parents=True, exist_ok=True)
        if any(target.iterdir()):
            raise GitError(f"archive destination must be empty: {target}")
        archive = subprocess.run(
            ["git", "archive", sha],
            cwd=self._root,
            capture_output=True,
            timeout=_GIT_TIMEOUT_S,
            check=False,
        )
        if archive.returncode != 0:
            raise GitError(f"git archive failed for {rev!r}")
        if len(archive.stdout) > _MAX_ARCHIVE_BYTES:
            raise GitError("archive exceeds size cap")
        import tarfile
        from io import BytesIO

        try:
            with tarfile.open(fileobj=BytesIO(archive.stdout), mode="r") as tar:
                members = tar.getmembers()
                if len(members) > _MAX_ARCHIVE_MEMBERS:
                    raise GitError("archive exceeds member cap")
                for member in members:
                    name = member.name
                    if name.startswith("/") or ".." in Path(name).parts:
                        raise GitError(f"unsafe archive member: {name!r}")
                    if member.issym() or member.islnk():
                        raise GitError(f"archive symlinks refused: {name!r}")
                extract_kwargs = {"filter": "data"} if sys.version_info >= (3, 12) else {}
                tar.extractall(path=target, **extract_kwargs)
        except (tarfile.TarError, OSError) as exc:
            raise GitError(f"archive extraction failed: {exc}") from exc
        return target

    def create_branch(self, branch: str, from_rev: str = "HEAD") -> str:
        sha = self.rev_parse(from_rev)
        self._run("branch", "--no-track", _check_branch(branch), sha)
        return branch

    def commit_files(
        self,
        message: str,
        files: dict[str, str],
        *,
        branch: str | None = None,
        author_name: str = "unbodge",
        author_email: str = "unbodge@local",
    ) -> str:
        """Write files, stage them, and commit on ``branch`` (or current HEAD)."""
        if not message.strip():
            raise GitError("commit message must be non-empty")
        if not files:
            raise GitError("commit requires at least one file")
        for rel in files:
            _check_rel_path(rel)
        if branch is not None:
            _check_branch(branch)
        current = self._current_branch()
        try:
            if branch is not None:
                self._run("checkout", "-B", branch)
            for rel, content in files.items():
                target = self._root / rel
                if self._root.resolve() not in target.resolve().parents:
                    raise GitError(f"file escapes repository: {rel!r}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="\n")
            self._run("add", "--", *[_check_rel_path(r) for r in files])
            env = dict(os.environ)
            env.update(
                {
                    "GIT_AUTHOR_NAME": author_name,
                    "GIT_AUTHOR_EMAIL": author_email,
                    "GIT_COMMITTER_NAME": author_name,
                    "GIT_COMMITTER_EMAIL": author_email,
                }
            )
            self._run(
                "-c", "user.name=unbodge", "-c", "user.email=unbodge@local",
                "commit", "-m", message, env=env,
            )
            return self.rev_parse("HEAD")
        finally:
            if branch is not None and current is not None and current != branch:
                self._run("checkout", current)

    def _current_branch(self) -> str | None:
        try:
            out = self._run("symbolic-ref", "--short", "HEAD")
        except GitError:
            return None
        return out.strip() or None


__all__ = ["GitRepo"]
