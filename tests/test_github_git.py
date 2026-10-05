"""GitHub adapter + local git history: reads, writes, and traversal guards."""

import pytest

from domain.models import FixCommit, Release, Repository, UpstreamIssue
from github.base import FixtureGitHubClient
from github.errors import GitError, GitHubNotFoundError
from github.git import GitRepo
from github.models import IssueComment, PullRequest, PullRequestFile, Tag
from phase2_support import (
    UPSTREAM_FIX_SHA,
    commit_all,
    init_repo,
    tag,
    write,
)

REPO_ID = "repo:downstream"


def _client() -> FixtureGitHubClient:
    repo = Repository(id=REPO_ID, full_name="acme/downstream")
    issue = UpstreamIssue(
        id="issue:7", repository_id=REPO_ID, number=7,
        title="nickname lookup crashes on anonymous profiles",
    )
    comment = IssueComment(
        id="comment:1", issue_id="issue:7", repository_id=REPO_ID,
        author="maintainer", body="reproduced on fake-dep 1.0",
    )
    pr = PullRequest(
        id="pr:9", repository_id=REPO_ID, number=9, title="Fix nickname default",
        head_branch="fix-nickname", base_branch="main",
    )
    commit = FixCommit(
        id="fix:1", repository_id=REPO_ID, sha=UPSTREAM_FIX_SHA,
        message="default missing nicknames to anonymous",
    )
    release = Release(
        id="rel:1", repository_id=REPO_ID, tag="v1.1", version="1.1",
        contains_fix_sha=UPSTREAM_FIX_SHA,
    )
    return FixtureGitHubClient(
        repositories={"acme/downstream": repo},
        issues={(REPO_ID, 7): issue},
        comments={(REPO_ID, 7): [comment]},
        pull_requests={(REPO_ID, 9): pr},
        pr_files={(REPO_ID, 9): [PullRequestFile(path="dep.py", status="modified")]},
        commits={(REPO_ID, UPSTREAM_FIX_SHA): commit},
        releases={REPO_ID: [release]},
        tags={REPO_ID: [Tag(name="v1.1", repository_id=REPO_ID, commit_sha=UPSTREAM_FIX_SHA)]},
    )


def test_fixture_reads_cover_phase2_surface():
    client = _client()
    assert client.get_repository("acme/downstream").full_name == "acme/downstream"
    assert client.get_issue(REPO_ID, 7).number == 7
    assert client.list_issue_comments(REPO_ID, 7)[0].author == "maintainer"
    assert client.get_pull_request(REPO_ID, 9).head_branch == "fix-nickname"
    assert client.list_pull_request_files(REPO_ID, 9)[0].path == "dep.py"
    assert client.get_commit(REPO_ID, UPSTREAM_FIX_SHA).message.startswith("default")
    assert client.list_releases(REPO_ID)[0].tag == "v1.1"
    assert client.list_tags(REPO_ID)[0].commit_sha == UPSTREAM_FIX_SHA
    assert client.list_issue_comments(REPO_ID, 999) == []
    assert client.list_releases("repo:missing") == []


def test_fixture_missing_entries_raise_not_found():
    client = _client()
    with pytest.raises(GitHubNotFoundError):
        client.get_repository("nobody/nowhere")
    with pytest.raises(GitHubNotFoundError):
        client.get_issue(REPO_ID, 404)
    with pytest.raises(GitHubNotFoundError):
        client.get_pull_request(REPO_ID, 404)
    with pytest.raises(GitHubNotFoundError):
        client.get_commit(REPO_ID, "0" * 40)


def test_fixture_write_ops_record_branches_commits_prs():
    client = _client()
    assert client.create_branch(REPO_ID, "unbodge/w7", UPSTREAM_FIX_SHA) == "unbodge/w7"
    commit = client.create_commit(REPO_ID, "unbodge/w7", "remove workaround", {"app.py": "x"})
    assert commit.repository_id == REPO_ID
    pr = client.create_pull_request(REPO_ID, "Remove workaround", "body", "unbodge/w7", "main")
    assert pr.number >= 1000 and pr.head_branch == "unbodge/w7"
    with pytest.raises(ValueError):
        client.create_branch(REPO_ID, "  ", UPSTREAM_FIX_SHA)
    with pytest.raises(ValueError):
        client.create_commit(REPO_ID, "b", "  ", {"app.py": "x"})
    with pytest.raises(ValueError):
        client.create_pull_request(REPO_ID, "  ", "b", "h", "main")


def _repo_with_history(tmp_path):
    root = init_repo(tmp_path / "downstream")
    write(root, "app.py", "v1\n")
    sha1 = commit_all(root, "first")
    write(root, "app.py", "v2\n")
    write(root, "new.py", "new\n")
    sha2 = commit_all(root, "second")
    tag(root, "v2.0")
    return root, sha1, sha2


def test_git_history_reads(tmp_path):
    root, sha1, sha2 = _repo_with_history(tmp_path)
    repo = GitRepo(root)
    assert repo.rev_parse("v2.0") == sha2
    assert repo.rev_parse("HEAD") == sha2
    subjects = repo.log_subjects(limit=5)
    assert [s for _, s in subjects] == ["second", "first"]
    assert repo.file_at("v2.0", "app.py") == "v2\n"
    assert repo.file_at("HEAD~1", "app.py") == "v1\n"
    assert sorted(repo.list_files_at("v2.0")) == ["app.py", "new.py"]
    assert repo.diff_names(sha1, sha2) == ["app.py", "new.py"]
    assert "v2" in repo.diff_text(sha1, sha2, "app.py")
    assert repo.list_tags() == ["v2.0"]
    with pytest.raises(GitHubNotFoundError):
        repo.file_at("v2.0", "ghost.py")


def test_git_rejects_traversal_and_bad_revs(tmp_path):
    root, _, _ = _repo_with_history(tmp_path)
    repo = GitRepo(root)
    for bad in ["../evil.py", "/abs.py", "..\\win.py", ""]:
        with pytest.raises(GitError):
            repo.file_at("HEAD", bad)
    for bad_rev in ["HEAD; rm -rf /", "$(whoami)", "`id`", "--upload-pack=x", "", ".."]:
        with pytest.raises(GitError):
            repo.rev_parse(bad_rev)
    with pytest.raises(GitError):
        GitRepo(tmp_path / "not-a-repo")


def test_git_branch_and_commit(tmp_path):
    root, _, _ = _repo_with_history(tmp_path)
    repo = GitRepo(root)
    assert repo.create_branch("unbodge/w7") == "unbodge/w7"
    sha = repo.commit_files("remove workaround", {"app.py": "v3\n"}, branch="unbodge/w7")
    assert len(sha) == 40 and repo.file_at("unbodge/w7", "app.py") == "v3\n"
    with pytest.raises(GitError):
        repo.create_branch("bad;name")
    with pytest.raises(GitError):
        repo.commit_files("   ", {"a.py": "x"})
    with pytest.raises(GitError):
        repo.commit_files("msg", {})
    with pytest.raises(GitError):
        repo.commit_files("msg", {"../escape.py": "x"})


def test_git_archive_materializes_rev(tmp_path):
    root, _, _ = _repo_with_history(tmp_path)
    repo = GitRepo(root)
    dest = repo.archive_to("HEAD~1", tmp_path / "work")
    assert (dest / "app.py").read_text() == "v1\n"
    assert not (dest / "new.py").exists()
