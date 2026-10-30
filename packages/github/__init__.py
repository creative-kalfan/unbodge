"""GitHub/Git adapters: metadata interface, fixture, and local git history."""

from github.base import FixtureGitHubClient, GitHubClient
from github.client import GITHUB_API_BASE, GitHubReadOnlyError, ReadOnlyGitHubClient
from github.errors import GitError, GitHubError, GitHubNotFoundError
from github.git import GitRepo
from github.models import IssueComment, PullRequest, PullRequestFile, Tag

__all__ = [
    "FixtureGitHubClient",
    "GITHUB_API_BASE",
    "GitError",
    "GitHubClient",
    "GitHubError",
    "GitHubNotFoundError",
    "GitHubReadOnlyError",
    "GitRepo",
    "IssueComment",
    "PullRequest",
    "PullRequestFile",
    "ReadOnlyGitHubClient",
    "Tag",
]
