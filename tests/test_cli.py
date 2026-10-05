"""Worker CLI: argument handling, job validation, context building."""

import json

import pytest

from workflow.cli import load_context, main


def _job(tmp_path):
    return {
        "repository_id": "repo:x",
        "repo_path": str(tmp_path),
        "old_rev": "v1",
        "new_rev": "v2",
        "workaround_patch": "p",
        "probe_argv": ["python", "check.py"],
        "regression_argv": ["python", "reg.py"],
        "event": {"id": "evt:1", "repository_id": "repo:x", "title": "t"},
        "issue_id": "issue:1",
        "fix_id": "fix:1",
        "fix_sha": "c" * 40,
        "releases": [],
        "pypi": {"pkg": {"1.0": "2020-01-01T00:00:00+00:00"}},
        "plan_id": "job:1",
    }


def test_cli_rejects_bad_invocation_and_files(tmp_path, capsys):
    assert main([]) == 2
    assert main(["a", "b"]) == 2
    assert main([str(tmp_path / "missing.json")]) == 1
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")
    assert main([str(broken)]) == 1
    big = tmp_path / "big.json"
    big.write_text("x" * 10)
    assert main([str(big)]) == 1  # invalid JSON shape handled


def test_cli_validates_job_schema(tmp_path):
    job = _job(tmp_path)
    del job["probe_argv"]
    path = tmp_path / "job.json"
    path.write_text(json.dumps(job))
    assert main([str(path)]) == 1
    job = _job(tmp_path)
    job["timeout_s"] = float("nan")
    path.write_text(json.dumps(job))
    assert main([str(path)]) == 1
    job = _job(tmp_path)
    job["repo_path"] = str(tmp_path / "nope")
    path.write_text(json.dumps(job))
    assert main([str(path)]) == 1


def test_load_context_builds_typed_context(tmp_path):
    from workflow.stages import PipelineContext

    ctx = load_context(_job(tmp_path), sandbox=None)
    assert isinstance(ctx, PipelineContext)
    assert ctx.probe_argv == ["python", "check.py"]
    assert ctx.pypi.latest_version("pkg") == "1.0"
