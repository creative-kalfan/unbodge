"""Verify the causal chain against configured metadata and Git objects.

The metadata client and upstream checkout are operator-configured trust roots,
not fields accepted from an investigation/job or reasoning output. Fixture
clients are useful for controlled cases; they do not authenticate live GitHub.
No caller-supplied `contains_fix_sha` or `verified` flag establishes ancestry.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from tempfile import TemporaryDirectory

from evidence.hashing import sha256_hex
from experiments.real import ensure_workaround_state, prepare_cell_workdir, read_workdir_files
from github.base import GitHubClient
from github.git import GitRepo
from history.reconstruction import Reconstructor
from history.states import HistoryError


def _require(condition, message):
    if not condition:
        raise HistoryError(message)


def _references(text, url):
    return re.search(re.escape(url) + r"(?![0-9])", text) is not None


@dataclass(frozen=True)
class GitProvenance:
    metadata: GitHubClient
    upstream: GitRepo
    upstream_full_name: str
    downstream_full_name: str
    package: str
    issue_number: int
    symptom_number: int
    old_tag: str
    release_tag: str
    introduction: str
    sources: tuple[tuple[str, str], ...]

    def verify(self, ctx) -> dict:
        upstream = self.metadata.get_repository(self.upstream_full_name)
        downstream = self.metadata.get_repository(self.downstream_full_name)
        _require(upstream.full_name == self.upstream_full_name
                 and downstream.full_name == self.downstream_full_name, "metadata repository identity mismatch")
        _require(downstream.id == ctx.repository_id, "wrong downstream repository")
        issue = self.metadata.get_issue(upstream.id, self.issue_number)
        symptom = self.metadata.get_issue(downstream.id, self.symptom_number)
        issue_url = f"https://github.com/{upstream.full_name}/issues/{self.issue_number}"
        symptom_url = f"https://github.com/{downstream.full_name}/issues/{self.symptom_number}"
        _require(issue.id == ctx.issue_id and issue.repository_id == upstream.id
                 and issue.url == issue_url, "unrelated upstream issue")
        _require(symptom.repository_id == downstream.id and symptom.url == symptom_url
                 and _references(symptom.body, issue_url), "unsupported downstream symptom")
        fix = self.metadata.get_commit(upstream.id, ctx.fix_sha)
        sha = self.upstream.rev_parse(ctx.fix_sha)
        message = self.upstream._run("show", "-s", "--format=%B", sha).strip()
        _require(fix.id == ctx.fix_id and fix.repository_id == upstream.id
                 and fix.sha == sha and fix.message == message and _references(message, issue_url),
                 "fix is unrelated to issue or differs from Git object")
        old = self.upstream.rev_parse(self.old_tag)
        new = self.upstream.rev_parse(self.release_tag)
        containing = self.upstream._run("rev-list", new).splitlines()
        _require(sha in containing and old in self.upstream._run("rev-list", sha).splitlines()
                 and sha not in self.upstream._run("rev-list", old).splitlines(),
                 "fix not introduced between old and release states")
        release = next((r for r in self.metadata.list_releases(upstream.id)
                        if r.tag == self.release_tag), None)
        if release is None:
            raise HistoryError("release lacks verified metadata")
        _require(release.repository_id == upstream.id
                 and release.contains_fix_sha == sha, "release lacks verified metadata")
        _require(any(r.model_dump() == release.model_dump() for r in ctx.releases),
                 "caller release differs from configured metadata")
        repo = GitRepo(ctx.repo_path)
        intro = repo.rev_parse(self.introduction)
        old_down, new_down = repo.rev_parse(ctx.old_rev), repo.rev_parse(ctx.new_rev)
        _require(intro in repo._run("rev-list", old_down).splitlines()
                 and old_down in repo._run("rev-list", new_down).splitlines(),
                 "workaround introduction is outside downstream history")
        intro_message = repo._run("show", "-s", "--format=%B", intro)
        _require(_references(intro_message, issue_url) and _references(intro_message, symptom_url),
                 "workaround introduction does not link issue and symptom")
        with TemporaryDirectory(prefix="unbodge-intro-") as tmp:
            tree = prepare_cell_workdir(repo, intro, tmp)
            ensure_workaround_state(tree, ctx.workaround_patch, present=False)
            parent = repo.rev_parse(intro + "^")
            expected = {p: repo.file_at(parent, p) for p in repo.list_files_at(parent)}
            _require(read_workdir_files(tree) == expected,
                     "removal patch differs from recorded workaround introduction")
        recon = Reconstructor(repo, ctx.repository_id)
        old_lock, new_lock = recon.state_at(old_down).lock, recon.state_at(new_down).lock
        _require(new_lock.version_of(self.package) == release.version
                 and bool(old_lock.version_of(self.package))
                 and old_lock.version_of(self.package) != release.version,
                 "dependency versions do not match fix release")
        _require(bool(self.sources) and len(set(self.sources)) == len(self.sources),
                 "missing or duplicate dependency source mapping")
        _require(set(repo.diff_names(old_down, new_down)) <=
                 {p for p, _ in self.sources} | {"requirements.txt"},
                 "unrelated downstream changes confound the upstream fix")
        old_requirements = repo.file_at(old_down, "requirements.txt").splitlines()
        new_requirements = repo.file_at(new_down, "requirements.txt").splitlines()
        old_pin = f"{self.package}=={old_lock.version_of(self.package)}"
        _require(old_requirements.count(old_pin) == 1, "unsupported dependency pin declaration")
        expected_requirements = [f"{self.package}=={release.version}" if line == old_pin else line
                                 for line in old_requirements]
        _require(new_requirements == expected_requirements,
                 "dependency change includes unrelated requirements")
        fixed_paths = {p for p in self.upstream.diff_names(sha + "^", sha) if p.endswith(".py")}
        _require(bool(fixed_paths) and fixed_paths <= {p for _, p in self.sources},
                 "fix code is not bound to executed dependency sources")
        source_hashes = {}
        for label, up_rev, down_rev in (("old", old, old_down), ("new", new, new_down)):
            up_paths, down_paths = set(self.upstream.list_files_at(up_rev)), set(repo.list_files_at(down_rev))
            for down_path, up_path in self.sources:
                _require((up_path in up_paths) == (down_path in down_paths), "dependency source missing")
                if up_path in up_paths:
                    content = self.upstream.file_at(up_rev, up_path)
                    _require(content == repo.file_at(down_rev, down_path), "executed dependency source differs")
                    source_hashes[label + ":" + down_path] = sha256_hex(content)
        return {"issue": issue.model_dump(mode="json"), "symptom": symptom.model_dump(mode="json"),
                "fix": fix.model_dump(mode="json"), "release": release.model_dump(mode="json"),
                "upstream_old": old, "upstream_release": new, "introduction": intro,
                "downstream_old": old_down, "downstream_new": new_down,
                "patch_hash": sha256_hex(ctx.workaround_patch), "sources": source_hashes}
