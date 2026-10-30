"""Controlled metadata/Git trust roots for proof tests, never live GitHub proof.

Real-dependency tests replay actual vendored bytes in this controlled mirror;
the generated fix SHA is deliberately distinct from the historical GitHub SHA.
"""
from dataclasses import replace
from pathlib import Path
from tempfile import mkdtemp

from domain.models import FixCommit, Repository, UpstreamIssue
from github.base import FixtureGitHubClient
from github.git import GitRepo
from history.provenance import GitProvenance
from phase2_support import git_cmd, init_repo, tag, write


def with_provenance(ctx, *, package="fake-dep", sources=(("dep.py", "dep.py"),),
                    upstream_name="unbodge-fixtures/upstream",
                    downstream_name="unbodge-fixtures/downstream", issue_number=7, symptom_number=1):
    downstream = GitRepo(ctx.repo_path)
    path = mkdtemp(prefix="upstream-", dir=Path(ctx.repo_path).parent)
    root = init_repo(path)
    for rev, label in ((ctx.old_rev, "old"), (ctx.new_rev, "new")):
        paths = set(downstream.list_files_at(rev))
        for down_path, up_path in sources:
            target = root / up_path
            if down_path in paths:
                write(root, up_path, downstream.file_at(rev, down_path))
            elif target.exists():
                target.unlink()
        url = f"https://github.com/{upstream_name}/issues/{issue_number}"
        git_cmd(root, "add", "-A")
        git_cmd(root, "commit", "--allow-empty", "-m", "old dependency snapshot" if label == "old" else "Fix " + url)
        sha = git_cmd(root, "rev-parse", "HEAD").strip()
        tag(root, "old" if label == "old" else ctx.releases[-1].tag)
    release = ctx.releases[-1].model_copy(update={"contains_fix_sha": sha, "repository_id": "repo:verified-upstream"})
    upstream_repo = Repository(id="repo:verified-upstream", full_name=upstream_name)
    downstream_repo = Repository(id=ctx.repository_id, full_name=downstream_name)
    issue = UpstreamIssue(id=ctx.issue_id, repository_id=upstream_repo.id,
                          number=issue_number, title="controlled issue", url=url)
    symptom = UpstreamIssue(id="symptom:controlled", repository_id=ctx.repository_id,
                            number=symptom_number, title="controlled symptom", body=url,
                            url=f"https://github.com/{downstream_name}/issues/{symptom_number}")
    fix = FixCommit(id=ctx.fix_id, repository_id=upstream_repo.id, sha=sha, message="Fix " + url)
    client = FixtureGitHubClient(
        repositories={upstream_name: upstream_repo, downstream_name: downstream_repo},
        issues={(upstream_repo.id, issue_number): issue, (ctx.repository_id, symptom_number): symptom},
        commits={(upstream_repo.id, sha): fix}, releases={upstream_repo.id: [release]},
    )
    provenance = GitProvenance(client, GitRepo(root), upstream_name, downstream_name,
                               package, issue_number, symptom_number, "old", release.tag,
                               downstream.rev_parse(ctx.old_rev), tuple(sources))
    return replace(ctx, fix_sha=sha, releases=(release,), provenance=provenance)
