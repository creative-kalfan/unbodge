"""Local reproducible PR generation (Phase 2).

No network: creates a real local branch + commit in the downstream
repository and renders the PR title/body purely from structured evidence
(matrix, regression counts, evidence ids, fix/release refs). The returned
``PullRequestResult`` is the submittable artifact; pushing/creating the
remote PR is a later-phase transport concern.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from domain.enums import TestStatus, UniverseCell
from domain.errors import UnbodgeError
from domain.models import PullRequestResult, RemovalDecision, utcnow
from github.errors import GitError
from github.git import GitRepo


class PrGeneratorError(UnbodgeError):
    """Local PR generation failed (bad inputs or git failure)."""


def render_pr_body(
    *,
    hypothesis_id: str,
    matrix: Mapping[UniverseCell, TestStatus],
    regression_suite: str,
    regression_passed: int,
    regression_failed: int,
    evidence_ids: Sequence[str],
    fix_sha: str,
    release_tag: str,
    removed_files: Sequence[str] = (),
) -> str:
    """Render a PR body deterministically from structured evidence only."""
    cells = " ".join(
        f"{cell.value}={matrix[cell].value}" for cell in UniverseCell if cell in matrix
    )
    removed = ", ".join(removed_files) if removed_files else "(workaround removal)"
    lines = [
        f"Remove obsolete workaround for hypothesis {hypothesis_id}.",
        "",
        "## Counterfactual proof",
        "",
        f"Matrix: {cells}",
        "",
        "## Regression",
        "",
        f"Suite `{regression_suite}`: passed={regression_passed} failed={regression_failed}",
        "",
        "## Evidence",
        "",
        *[f"- {evidence_id}" for evidence_id in evidence_ids],
        "",
        "## Upstream",
        "",
        f"Fix commit: {fix_sha}",
        f"Release: {release_tag}",
        f"Removed: {removed}",
    ]
    return "\n".join(lines)


def _slug(text: str) -> str:
    cleaned = "".join(c.lower() if c.isalnum() else "-" for c in text)
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned.strip("-")[:48] or "proposal"


class LocalPrGenerator:
    """Creates the local branch/commit and the PR artifact."""

    def __init__(self, repo: GitRepo) -> None:
        self._repo = repo

    def create_proposal(
        self,
        *,
        decision: RemovalDecision,
        title: str,
        body: str,
        files: Mapping[str, str],
        base_branch: str = "main",
    ) -> PullRequestResult:
        """Commit ``files`` on a new branch and return the PR artifact."""
        if not title.strip():
            raise PrGeneratorError("PR title must be non-empty")
        if not body.strip():
            raise PrGeneratorError("PR body must be non-empty")
        if not files:
            raise PrGeneratorError("PR proposal requires at least one file")
        base_sha = self._repo.rev_parse(base_branch)
        branch = f"unbodge/{_slug(decision.hypothesis_id or decision.id)}"
        try:
            self._repo.create_branch(branch, base_sha)
        except GitError:
            branch = f"unbodge/{_slug(decision.id)}-{base_sha[:8]}"
            self._repo.create_branch(branch, base_sha)
        commit_sha = self._repo.commit_files(
            f"{title}\n\nEvidence: {', '.join(decision.evidence_ids[:5])}",
            dict(files),
            branch=branch,
        )
        _ = commit_sha
        return PullRequestResult(
            id=f"pr:{decision.id}",
            decision_id=decision.id,
            title=title,
            body=body,
            branch=branch,
            base=base_branch,
            created_at=utcnow(),
        )


__all__ = ["LocalPrGenerator", "PrGeneratorError", "render_pr_body"]
