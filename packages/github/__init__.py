"""GitHub/Git adapters: metadata interface, fixture, and local git history."""

from github.base import FixtureGitHubClient, GitHubClient
from github.errors import GitError, GitHubError, GitHubNotFoundError
from github.git import GitRepo
from github.models import IssueComment, PullRequest, PullRequestFile, Tag

__all__ = [
    "FixtureGitHubClient",
    "GitError",
    "GitHubClient",
    "GitHubError",
    "GitHubNotFoundError",
    "GitRepo",
    "IssueComment",
    "PullRequest",
    "PullRequestFile",
    "Tag",
]
