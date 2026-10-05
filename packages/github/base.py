"""GitHub metadata adapter (Phase 2).

``GitHubClient`` is an abstract interface: metadata reads plus branch /
commit / PR creation. The network transport is deliberately absent in
Phase 2 (offline-first); ``FixtureGitHubClient`` serves controlled cases
from in-memory data. A REST transport can implement the same ABC later
without touching callers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from domain.models import FixCommit, Release, Repository, UpstreamIssue
from github.errors import GitHubNotFoundError
from github.models import IssueComment, PullRequest, PullRequestFile, Tag


class GitHubClient(ABC):
    """Stable GitHub interface. Git history itself lives in ``github.git``."""

    # -- reads -----------------------------------------------------------
    @abstractmethod
    def get_repository(self, full_name: str) -> Repository: ...
    @abstractmethod
    def get_issue(self, repository_id: str, number: int) -> UpstreamIssue: ...
    @abstractmethod
    def list_issue_comments(self, repository_id: str, number: int) -> list[IssueComment]: ...
    @abstractmethod
    def get_pull_request(self, repository_id: str, number: int) -> PullRequest: ...
    @abstractmethod
    def list_pull_request_files(self, repository_id: str, number: int) -> list[PullRequestFile]: ...
    @abstractmethod
    def get_commit(self, repository_id: str, sha: str) -> FixCommit: ...
    @abstractmethod
    def list_releases(self, repository_id: str) -> list[Release]: ...
    @abstractmethod
    def list_tags(self, repository_id: str) -> list[Tag]: ...

    # -- writes (local-evaluable; network transport later) ---------------
    @abstractmethod
    def create_branch(self, repository_id: str, branch: str, from_sha: str) -> str: ...
    @abstractmethod
    def create_commit(
        self, repository_id: str, branch: str, message: str, files: dict[str, str]
    ) -> FixCommit: ...
    @abstractmethod
    def create_pull_request(
        self, repository_id: str, title: str, body: str, head_branch: str, base_branch: str
    ) -> PullRequest: ...


class FixtureGitHubClient(GitHubClient):
    """In-memory client for controlled (offline, deterministic) cases."""

    def __init__(
        self,
        *,
        repositories: dict[str, Repository] | None = None,
        issues: dict[tuple[str, int], UpstreamIssue] | None = None,
        comments: dict[tuple[str, int], list[IssueComment]] | None = None,
        pull_requests: dict[tuple[str, int], PullRequest] | None = None,
        pr_files: dict[tuple[str, int], list[PullRequestFile]] | None = None,
        commits: dict[tuple[str, str], FixCommit] | None = None,
        releases: dict[str, list[Release]] | None = None,
        tags: dict[str, list[Tag]] | None = None,
    ) -> None:
        self._repositories = dict(repositories or {})
        self._issues = dict(issues or {})
        self._comments = dict(comments or {})
        self._pull_requests = dict(pull_requests or {})
        self._pr_files = dict(pr_files or {})
        self._commits = dict(commits or {})
        self._releases = dict(releases or {})
        self._tags = dict(tags or {})
        self._created_branches: dict[str, list[str]] = {}
        self._created_commits: list[FixCommit] = []
        self._created_prs: list[PullRequest] = []

    def get_repository(self, full_name: str) -> Repository:
        try:
            return self._repositories[full_name]
        except KeyError:
            raise GitHubNotFoundError(f"repository not found: {full_name!r}") from None

    def get_issue(self, repository_id: str, number: int) -> UpstreamIssue:
        try:
            return self._issues[(repository_id, number)]
        except KeyError:
            raise GitHubNotFoundError(f"issue not found: {repository_id}#{number}") from None

    def list_issue_comments(self, repository_id: str, number: int) -> list[IssueComment]:
        return list(self._comments.get((repository_id, number), []))

    def get_pull_request(self, repository_id: str, number: int) -> PullRequest:
        try:
            return self._pull_requests[(repository_id, number)]
        except KeyError:
            raise GitHubNotFoundError(f"PR not found: {repository_id}#{number}") from None

    def list_pull_request_files(self, repository_id: str, number: int) -> list[PullRequestFile]:
        return list(self._pr_files.get((repository_id, number), []))

    def get_commit(self, repository_id: str, sha: str) -> FixCommit:
        try:
            return self._commits[(repository_id, sha)]
        except KeyError:
            raise GitHubNotFoundError(f"commit not found: {sha!r}") from None

    def list_releases(self, repository_id: str) -> list[Release]:
        return list(self._releases.get(repository_id, []))

    def list_tags(self, repository_id: str) -> list[Tag]:
        return list(self._tags.get(repository_id, []))

    def create_branch(self, repository_id: str, branch: str, from_sha: str) -> str:
        if not branch.strip() or not from_sha.strip():
            raise ValueError("branch and from_sha must be non-empty")
        self._created_branches.setdefault(repository_id, []).append(branch)
        return branch

    def create_commit(
        self, repository_id: str, branch: str, message: str, files: dict[str, str]
    ) -> FixCommit:
        if not message.strip():
            raise ValueError("commit message must be non-empty")
        if not files:
            raise ValueError("commit requires at least one file")
        sha = f"{len(self._created_commits):040x}"
        commit = FixCommit(
            id=f"commit:{repository_id}:{branch}:{len(self._created_commits)}",
            repository_id=repository_id,
            sha=sha,
            message=message,
        )
        self._created_commits.append(commit)
        return commit

    def create_pull_request(
        self, repository_id: str, title: str, body: str, head_branch: str, base_branch: str
    ) -> PullRequest:
        if not title.strip():
            raise ValueError("PR title must be non-empty")
        pr = PullRequest(
            id=f"pr:{repository_id}:{len(self._created_prs)}",
            repository_id=repository_id,
            number=1000 + len(self._created_prs),
            title=title,
            body=body,
            head_branch=head_branch,
            base_branch=base_branch,
        )
        self._created_prs.append(pr)
        return pr


__all__ = ["FixtureGitHubClient", "GitHubClient"]
