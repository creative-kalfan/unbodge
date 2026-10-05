"""Proof worker CLI (Phase 4).

Runs one deterministic proof job from a JSON job file using local
backends (Docker sandbox when available, fixture package index).
Used by the ``worker`` deployment service and the demo script.
No Temporal server required; the Temporal mapping lives in
``workflow.temporal`` for later.

Job file schema (all fields required unless noted)::

    {
      "repository_id": "repo:x",
      "repo_path": "/path/to/repo",
      "old_rev": "v1", "new_rev": "v2",
      "workaround_patch": "<unified diff>",
      "probe_argv": ["python", "check.py"],
      "regression_argv": ["python", "regression.py"],
      "probe_env": {}, "regression_env": {},
      "event": {"id": "evt:1", "repository_id": "repo:x", "title": "t"},
      "issue_id": "issue:1", "fix_id": "fix:1",
      "fix_sha": "<40 hex>",
      "releases": [{"id": "rel:1", "repository_id": "repo:x",
                    "tag": "v1", "version": "1",
                    "contains_fix_sha": "<40 hex>"}],
      "pypi": {"pkg": {"1.0": "2020-01-01T00:00:00+00:00"}},
      "plan_id": "job:1", "decision_id": "decision:job:1",
      "workflow_id": "wf:job:1",
      "scan_exclude_prefixes": ["vendor/"],
      "timeout_s": 60
    }
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from domain.models import Release, UpstreamEvent, WorkflowRun
from pypi.base import FixturePyPIClient, ReleaseMetadata
from sandbox.docker import DockerSandbox
from workflow.pipeline import run_pipeline
from workflow.stages import PipelineContext, PipelineState


def load_context(job: dict, sandbox=None) -> PipelineContext:
    event = job["event"]
    releases = tuple(Release(**rel) for rel in job.get("releases", ()))
    index = {
        name: {
            version: ReleaseMetadata(
                name=name, version=version,
                upload_time=datetime.fromisoformat(stamp),
            )
            for version, stamp in versions.items()
        }
        for name, versions in job.get("pypi", {}).items()
    }
    return PipelineContext(
        repository_id=job["repository_id"],
        repo_path=job["repo_path"],
        old_rev=job["old_rev"],
        new_rev=job["new_rev"],
        workaround_patch=job["workaround_patch"],
        probe_argv=list(job["probe_argv"]),
        regression_argv=list(job["regression_argv"]),
        event=UpstreamEvent(
            id=event["id"], repository_id=event["repository_id"], title=event["title"],
            body=event.get("body", ""),
        ),
        issue_id=job["issue_id"],
        fix_id=job["fix_id"],
        fix_sha=job["fix_sha"],
        releases=releases,
        pypi=FixturePyPIClient(index),
        sandbox=sandbox or DockerSandbox(),
        plan_id=job.get("plan_id", "job:1"),
        decision_id=job.get("decision_id", "decision:job:1"),
        probe_env=dict(job.get("probe_env", {})),
        regression_env=dict(job.get("regression_env", {})),
        scan_exclude_prefixes=tuple(job.get("scan_exclude_prefixes", ())),
        timeout_s=float(job.get("timeout_s", 60)),
    )


def run_job(job: dict, sandbox=None) -> dict:
    ctx = load_context(job, sandbox=sandbox)
    workflow_id = job.get("workflow_id", "wf:job:1")
    initial = PipelineState(workflow=WorkflowRun(id=workflow_id, hypothesis_id=None))
    final = run_pipeline(initial, ctx)
    decision = final.decision
    return {
        "decision_id": job.get("decision_id", "decision:job:1"),
        "outcome": decision.outcome.value if decision else "NONE",
        "matrix": {cell.value: status.value for cell, status in final.matrix.items()},
        "evidence_ids": list(final.evidence_ids),
        "pr_id": final.pr_id,
        "pr_skipped": final.pr_skipped,
        "workflow_state": final.workflow.state.value if final.workflow else None,
    }


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("usage: python -m workflow.cli <job.json>", file=sys.stderr)
        return 2
    try:
        with open(args[0], encoding="utf-8") as handle:
            raw = handle.read(1_000_000 + 1)
        if len(raw) > 1_000_000:
            raise ValueError("job file exceeds size cap")
        job = json.loads(raw)
    except (OSError, ValueError) as exc:
        print(f"job file unreadable: {exc}", file=sys.stderr)
        return 1
    try:
        _validate_job(job)
        result = run_job(job)
    except Exception as exc:
        print(f"job failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _validate_job(job: dict) -> None:
    if not isinstance(job, dict):
        raise ValueError("job must be a JSON object")
    for key in (
        "repository_id", "repo_path", "old_rev", "new_rev", "workaround_patch",
        "probe_argv", "regression_argv", "event", "issue_id", "fix_id", "fix_sha",
    ):
        if key not in job:
            raise ValueError(f"job missing required key: {key!r}")
    if not isinstance(job["probe_argv"], list) or not job["probe_argv"]:
        raise ValueError("probe_argv must be a non-empty list")
    timeout = float(job.get("timeout_s", 60))
    if not (timeout > 0) or timeout != timeout or timeout > 3600:
        raise ValueError("timeout_s must be a finite positive number <= 3600")
    repo_path = job["repo_path"]
    if not isinstance(repo_path, str) or not Path(repo_path).is_dir():
        raise ValueError("repo_path must be an existing directory")


if __name__ == "__main__":
    raise SystemExit(main())
