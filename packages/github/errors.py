"""Typed GitHub errors (Phase 2)."""

from __future__ import annotations

from domain.errors import UnbodgeError


class GitHubError(UnbodgeError):
    """Base class for GitHub adapter failures."""


class GitHubNotFoundError(GitHubError):
    """A repository, issue, PR, commit, release, or tag was not found."""


class GitError(GitHubError):
    """A local git operation failed (or refused an unsafe input)."""


__all__ = ["GitError", "GitHubError", "GitHubNotFoundError"]
