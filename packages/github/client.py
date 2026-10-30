"""Read-only GitHub REST API client (Phase 5).

Implements the read-only surface of GitHubClient using stdlib urllib.
Write operations (create_branch, create_commit, create_pull_request) raise
GitHubReadOnlyError to enforce the least-privilege, no-mutation invariant.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import quote

from domain.enums import IssueState
from domain.models import FixCommit, Release, Repository, UpstreamIssue
from github.base import GitHubClient
from github.errors import GitHubAuthError, GitHubError, GitHubNotFoundError
from github.models import IssueComment, PullRequest, PullRequestFile, Tag

GITHUB_API_BASE = "https://api.github.com"
MAX_BODY_BYTES = 2_097_152  # 2MB
DEFAULT_TIMEOUT_S = 30.0

Opener = Callable[[urllib.request.Request, float], Any]


class GitHubReadOnlyError(GitHubError):
    """Raised when a mutation is attempted on a read-only GitHub client."""


class ReadOnlyGitHubClient(GitHubClient):
    """Authenticated read-only GitHub client backed by the GitHub REST API."""

    def __init__(
        self,
        *,
        token: str | None = None,
        base_url: str = GITHUB_API_BASE,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        opener: Opener | None = None,
    ) -> None:
        self._token = token if token is not None else os.environ.get("GITHUB_TOKEN", "")
        self._base_url = base_url.rstrip("/")
        if timeout_s <= 0:
            raise ValueError("timeout_s must be positive")
        self._timeout_s = timeout_s
        self._opener = opener

    @property
    def configured(self) -> bool:
        return bool(self._token)

    def _request(self, path: str) -> Any:
        url = f"{self._base_url}{path}"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "UNBODGE-GitHubClient/1.0",
        }
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        request = urllib.request.Request(url, headers=headers, method="GET")
        try:
            if self._opener is not None:
                response = self._opener(request, self._timeout_s)
                raw = response.read() if hasattr(response, "read") else response
            else:
                with urllib.request.urlopen(request, timeout=self._timeout_s) as response:
                    raw = response.read(MAX_BODY_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise GitHubNotFoundError(f"Resource not found at {path}: {exc}") from exc
            if exc.code in (401, 403):
                raise GitHubAuthError(f"GitHub authentication/permission failed ({exc.code}): {exc}") from exc
            raise GitHubError(f"GitHub API HTTP error {exc.code} for {path}: {exc}") from exc
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
            raise GitHubError(f"GitHub connection failed for {path}: {exc}") from exc

        if isinstance(raw, bytes) and len(raw) > MAX_BODY_BYTES:
            raise GitHubError(f"GitHub response exceeded maximum size limit: {path}")

        try:
            text = raw.decode("utf-8") if isinstance(raw, bytes) else raw
            return json.loads(text)
        except Exception as exc:
            raise GitHubError(f"Invalid JSON response from GitHub for {path}: {exc}") from exc

    # -- reads -----------------------------------------------------------
    def get_repository(self, full_name: str) -> Repository:
        data = self._request(f"/repos/{full_name}")
        return Repository(
            id=str(data.get("id", full_name)),
            full_name=data.get("full_name", full_name),
            default_branch=data.get("default_branch", "main"),
        )

    def get_issue(self, repository_id: str, number: int) -> UpstreamIssue:
        data = self._request(f"/repos/{repository_id}/issues/{number}")
        raw_state = str(data.get("state", "open")).upper()
        state = IssueState.CLOSED if raw_state == "CLOSED" else IssueState.OPEN
        return UpstreamIssue(
            id=str(data.get("id", f"{repository_id}#{number}")),
            repository_id=repository_id,
            number=data.get("number", number),
            title=data.get("title", ""),
            body=data.get("body", "") or "",
            state=state,
            url=data.get("html_url"),
        )

    def list_issue_comments(self, repository_id: str, number: int) -> list[IssueComment]:
        data = self._request(f"/repos/{repository_id}/issues/{number}/comments")
        comments: list[IssueComment] = []
        if isinstance(data, list):
            for c in data:
                created_at_raw = c.get("created_at")
                created_at = (
                    datetime.fromisoformat(created_at_raw.replace("Z", "+00:00"))
                    if created_at_raw
                    else datetime.now()
                )
                comments.append(
                    IssueComment(
                        id=str(c.get("id")),
                        body=c.get("body", "") or "",
                        author=c.get("user", {}).get("login", ""),
                        created_at=created_at,
                    )
                )
        return comments

    def get_pull_request(self, repository_id: str, number: int) -> PullRequest:
        data = self._request(f"/repos/{repository_id}/pulls/{number}")
        return PullRequest(
            id=str(data.get("id", f"{repository_id}#PR{number}")),
            number=data.get("number", number),
            title=data.get("title", ""),
            body=data.get("body", "") or "",
            head_sha=data.get("head", {}).get("sha", ""),
            base_sha=data.get("base", {}).get("sha", ""),
            merged=bool(data.get("merged", False)),
        )

    def list_pull_request_files(self, repository_id: str, number: int) -> list[PullRequestFile]:
        data = self._request(f"/repos/{repository_id}/pulls/{number}/files")
        files: list[PullRequestFile] = []
        if isinstance(data, list):
            for f in data:
                files.append(
                    PullRequestFile(
                        filename=f.get("filename", ""),
                        status=f.get("status", "modified"),
                        additions=int(f.get("additions", 0)),
                        deletions=int(f.get("deletions", 0)),
                        patch=f.get("patch"),
                    )
                )
        return files

    def get_commit(self, repository_id: str, sha: str) -> FixCommit:
        data = self._request(f"/repos/{repository_id}/commits/{sha}")
        commit_obj = data.get("commit", {})
        committer = commit_obj.get("committer", {})
        committed_at_raw = committer.get("date")
        committed_at = (
            datetime.fromisoformat(committed_at_raw.replace("Z", "+00:00"))
            if committed_at_raw
            else datetime.now()
        )
        files_data = data.get("files", [])
        files_touched = tuple(f.get("filename", "") for f in files_data if isinstance(f, dict))
        parents_data = data.get("parents", [])
        parents = tuple(p.get("sha", "") for p in parents_data if isinstance(p, dict))

        return FixCommit(
            sha=data.get("sha", sha),
            message=commit_obj.get("message", ""),
            author=commit_obj.get("author", {}).get("name", ""),
            committed_at=committed_at,
            files_touched=files_touched,
            parents=parents,
        )

    def list_releases(self, repository_id: str) -> list[Release]:
        data = self._request(f"/repos/{repository_id}/releases")
        releases: list[Release] = []
        if isinstance(data, list):
            for r in data:
                published_raw = r.get("published_at")
                published_at = (
                    datetime.fromisoformat(published_raw.replace("Z", "+00:00"))
                    if published_raw
                    else datetime.now()
                )
                releases.append(
                    Release(
                        id=str(r.get("id")),
                        repository_id=repository_id,
                        tag=r.get("tag_name", ""),
                        version=r.get("name", "") or r.get("tag_name", ""),
                        published_at=published_at,
                        prerelease=bool(r.get("prerelease", False)),
                    )
                )
        return releases

    def list_tags(self, repository_id: str) -> list[Tag]:
        data = self._request(f"/repos/{repository_id}/tags")
        tags: list[Tag] = []
        if isinstance(data, list):
            for t in data:
                tags.append(
                    Tag(
                        name=t.get("name", ""),
                        sha=t.get("commit", {}).get("sha", ""),
                    )
                )
        return tags

    # -- writes: strictly forbidden on read-only client ------------------
    def create_branch(self, repository_id: str, branch: str, from_sha: str) -> str:
        raise GitHubReadOnlyError(
            f"Mutations are forbidden on ReadOnlyGitHubClient: create_branch {branch!r}"
        )

    def create_commit(
        self, repository_id: str, branch: str, message: str, files: dict[str, str]
    ) -> FixCommit:
        raise GitHubReadOnlyError(
            "Mutations are forbidden on ReadOnlyGitHubClient: create_commit"
        )

    def create_pull_request(
        self, repository_id: str, title: str, body: str, head_branch: str, base_branch: str
    ) -> PullRequest:
        raise GitHubReadOnlyError(
            f"Mutations are forbidden on ReadOnlyGitHubClient: create_pull_request {title!r}"
        )


__all__ = ["GITHUB_API_BASE", "GitHubReadOnlyError", "ReadOnlyGitHubClient"]
