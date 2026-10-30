"""Permanent reproductions of the proof-authorization audit bypasses.

The recording sandbox is injected test infrastructure, not a claim of real
container execution. Git mutations are confined to pytest temporary repos.
"""
from dataclasses import replace

import pytest

from domain.enums import DecisionOutcome, PolicyMode, TestStatus
from domain.models import RemovalDecision
from github.git import GitRepo
from history.states import HistoryError
from phase2_support import build_downstream_fixture
from pr.generator import LocalPrGenerator, PrGeneratorError
from sandbox.docker import ContainerResult
from test_phase2_proof import _context, _releases
from workflow.pipeline import run_pipeline
from workflow.stages import PipelineState, STAGE_NAMES, stage_run_regression_tests, stage_validate_policy


class RecordingSandbox:
    def __init__(self):
        self.inputs = []

    def run_container(self, files, argv, env, **kwargs):
        self.inputs.append((dict(files), list(argv)))
        if argv[1] == "probe.py":
            failed = "workaround.py" not in files and "fake-dep==1.0" in files["requirements.txt"]
            return ContainerResult("probe", "", int(failed), 0.01, dict(env))
        failed = argv[1] == "sentinel.py" and "workaround.py" not in files
        return ContainerResult(
            "passed=0 failed=1" if failed else "passed=3 failed=0",
            "", int(failed), 0.01, dict(env),
        )


def context(tmp_path):
    refs = build_downstream_fixture(tmp_path / "downstream")
    return replace(_context(refs, _releases()), sandbox=RecordingSandbox())


def snapshot(repo):
    return (repo._run("show-ref"), repo._run("status", "--porcelain"),
            repo._run("rev-parse", "HEAD"), repo._run("ls-files", "-s"),
            repo._run("count-objects", "-v"))


def assert_safe(call):
    try:
        state = call()
    except (HistoryError, PrGeneratorError):
        return
    assert state.decision is not None
    assert state.decision.outcome == DecisionOutcome.ABSTAIN
    assert state.pr_id is None


@pytest.mark.parametrize("case", ["abstain", "invalid_evidence", "failed_regression", "unauthorized_mode"])
def test_direct_generator_rejects_unauthorized_before_mutation(tmp_path, case):
    ctx = context(tmp_path)
    repo = GitRepo(ctx.repo_path)
    before = snapshot(repo)
    decision = RemovalDecision(
        id="audit:" + case, hypothesis_id="audit:h",
        outcome=DecisionOutcome.ABSTAIN if case in ("abstain", "failed_regression") else DecisionOutcome.PROPOSE_REMOVAL,
        policy_mode=PolicyMode.STRICT_AUTO_MERGE if case == "unauthorized_mode" else PolicyMode.PROPOSE_ONLY,
        rationale="audit: no validated proof", evidence_ids=["ev:unvalidated"],
    )
    with pytest.raises(PrGeneratorError):
        LocalPrGenerator(repo).create_proposal(
            decision=decision, title="audit", body="audit", files={"app.py": "audit\n"},
        )
    assert snapshot(repo) == before


@pytest.mark.parametrize("case", ["unrelated_issue_nonexistent_fix", "caller_release_only"])
def test_caller_claims_cannot_authorize_removal(tmp_path, case):
    ctx = context(tmp_path)
    if case == "caller_release_only":
        ctx = replace(ctx, provenance=None)
    if case == "unrelated_issue_nonexistent_fix":
        bogus = "f" * 40
        ctx = replace(ctx, issue_id="issue:unrelated", fix_sha=bogus,
                      releases=tuple(r.model_copy(update={"contains_fix_sha": bogus}) for r in ctx.releases))
    repo = GitRepo(ctx.repo_path)
    before = snapshot(repo)
    assert_safe(lambda: run_pipeline(PipelineState(), ctx))
    assert snapshot(repo) == before


def test_regression_executes_removal_not_retained_workaround(tmp_path):
    ctx = replace(context(tmp_path), regression_argv=["python", "sentinel.py"])
    state = stage_run_regression_tests(PipelineState(), ctx)
    files, _ = ctx.sandbox.inputs[-1]
    assert "workaround.py" not in files
    assert "from workaround import" not in files["app.py"]
    assert state.regression.status == TestStatus.FAIL


@pytest.mark.parametrize("case", ["wrong_regression_revision", "mismatched_experiment"])
def test_mismatched_execution_cannot_authorize(tmp_path, case):
    ctx = context(tmp_path)
    state = run_pipeline(PipelineState(), ctx, stages=STAGE_NAMES[:-2])
    if case == "wrong_regression_revision":
        state = state.model_copy(update={"regression": state.regression.model_copy(update={"git_sha": "a" * 40})})
    else:
        run = state.runs[0].model_copy(update={"id": "run:another-investigation"})
        state = state.model_copy(update={"runs": [run, *state.runs[1:]]})
    assert_safe(lambda: stage_validate_policy(state, ctx))


def authorized(tmp_path):
    from experiments.real import prepared_files
    from policy.authorization import RemovalProof

    ctx = context(tmp_path)
    state = run_pipeline(PipelineState(), ctx, stages=STAGE_NAMES[:-1])
    assert state.decision.outcome == DecisionOutcome.PROPOSE_REMOVAL, state.failure
    files = prepared_files(GitRepo(ctx.repo_path), ctx.new_rev, ctx.workaround_patch, present=False)
    return ctx, state, files, RemovalProof(ctx, state)


@pytest.fixture(scope="module")
def complete_proof(tmp_path_factory):
    ctx, state, files, proof = authorized(tmp_path_factory.mktemp("complete-proof"))
    return ctx, state, files, snapshot(GitRepo(ctx.repo_path))


def test_authorized_proposal_commits_exact_removal_and_rejects_replay(tmp_path):
    ctx, state, files, proof = authorized(tmp_path)
    repo = GitRepo(ctx.repo_path)
    generator = LocalPrGenerator(repo)
    original_head = repo.rev_parse("HEAD")
    pr = generator.create_proposal(decision=state.decision, title="Remove workaround",
                                   body="proof", files=files, proof=proof)
    assert {p: repo.file_at(pr.branch, p) for p in repo.list_files_at(pr.branch)} == files
    assert "workaround.py" not in repo.list_files_at(pr.branch)
    assert repo.rev_parse("HEAD") == original_head
    assert repo._run("status", "--porcelain") == ""
    before = snapshot(repo)
    with pytest.raises(PrGeneratorError):
        generator.create_proposal(decision=state.decision, title="Remove workaround",
                                  body="proof", files=files, proof=proof)
    assert snapshot(repo) == before


@pytest.mark.parametrize("case", ["tampered_evidence", "missing_regression", "failed_regression",
                                  "wrong_artifact", "wrong_receipt", "wrong_experiment", "mode",
                                  "rehash_artifacts", "rehash_regression", "incomplete_evidence"])
def test_direct_boundary_revalidates_complete_proof(complete_proof, case):
    from policy.authorization import RemovalProof

    ctx, seed, files, pristine = complete_proof
    state, files = seed.model_copy(deep=True), dict(files)
    assert snapshot(GitRepo(ctx.repo_path)) == pristine
    if case == "tampered_evidence":
        item = state.evidence[0].model_copy(update={"claim": "tampered"})
        state = state.model_copy(update={"evidence": [item, *state.evidence[1:]]})
    elif case == "missing_regression":
        state = state.model_copy(update={"regression": None})
    elif case == "failed_regression":
        reg = state.regression.model_copy(update={"status": TestStatus.FAIL, "passed": 0, "failed": 1, "exit_code": 1})
        state = state.model_copy(update={"regression": reg})
    elif case == "wrong_artifact":
        files = {**files, "app.py": "unexecuted change\n"}
    elif case == "wrong_receipt":
        reg = state.regression.model_copy(update={"execution_receipt": "caller-supplied-pass"})
        state = state.model_copy(update={"regression": reg})
    elif case == "wrong_experiment":
        run = state.runs[0].model_copy(update={"spec_id": "foreign:cell:A"})
        state = state.model_copy(update={"runs": [run, *state.runs[1:]]})
    elif case == "mode":
        state = state.model_copy(update={"decision": state.decision.model_copy(update={"policy_mode": PolicyMode.HUMAN_APPROVAL_REQUIRED})})
    elif case == "incomplete_evidence":
        state = state.model_copy(update={"evidence": state.evidence[:-1]})
    else:
        from evidence.chain import run_payload
        from evidence.items import make_evidence

        if case == "rehash_artifacts":
            run = state.runs[0].model_copy(update={"artifact_hashes": {"transcript": "f" * 64}})
            state = state.model_copy(update={"runs": [run, *state.runs[1:]]})
            target_id, payload = f"ev:{ctx.plan_id}:exp:A:0", run_payload(run)
        else:
            reg = state.regression.model_copy(update={"artifact_hash": "f" * 64})
            state = state.model_copy(update={"regression": reg})
            target_id, payload = f"ev:{ctx.plan_id}:reg:0", reg.model_dump(mode="json")
        items = []
        for item in state.evidence:
            if item.id == target_id:
                data = item.model_dump(exclude={"hash"})
                data["payload"] = payload
                item = make_evidence(**data)
            items.append(item)
        state = state.model_copy(update={"evidence": items})
    repo = GitRepo(ctx.repo_path)
    before = snapshot(repo)
    with pytest.raises(PrGeneratorError):
        LocalPrGenerator(repo).create_proposal(decision=state.decision, title="audit", body="audit",
                                              files=files, proof=RemovalProof(ctx, state))
    assert snapshot(repo) == before


def test_missing_provenance_returns_explicit_safe_failure(tmp_path):
    ctx = replace(context(tmp_path), provenance=None)
    repo = GitRepo(ctx.repo_path)
    before = snapshot(repo)
    state = run_pipeline(PipelineState(), ctx)
    assert state.decision.outcome == DecisionOutcome.ABSTAIN
    assert state.failure and state.pr_skipped and state.pr_id is None
    assert run_pipeline(state, ctx) == state
    assert snapshot(repo) == before


@pytest.mark.parametrize("case", ["wrong_issue", "nonexistent_fix", "unverified_release", "unlinked_symptom"])
def test_independent_provenance_relationships_fail_closed(tmp_path, case):
    ctx = context(tmp_path)
    if case == "wrong_issue":
        ctx = replace(ctx, issue_id="issue:unrelated")
    elif case == "nonexistent_fix":
        ctx = replace(ctx, fix_sha="f" * 40)
    elif case == "unverified_release":
        ctx = replace(ctx, releases=tuple(r.model_copy(update={"contains_fix_sha": "f" * 40}) for r in ctx.releases))
    else:
        key = (ctx.repository_id, ctx.provenance.symptom_number)
        item = ctx.provenance.metadata._issues[key]
        ctx.provenance.metadata._issues[key] = item.model_copy(update={"body": "unrelated symptom"})
    repo = GitRepo(ctx.repo_path)
    before = snapshot(repo)
    state = run_pipeline(PipelineState(), ctx)
    assert state.decision.outcome == DecisionOutcome.ABSTAIN
    assert state.pr_skipped and state.pr_id is None
    assert snapshot(repo) == before


def test_unrelated_downstream_change_cannot_certify_upstream_fix(tmp_path):
    from phase2_support import commit_all, git_cmd, write

    ctx = context(tmp_path)
    original = GitRepo(ctx.repo_path).file_at(ctx.new_rev, "app.py")
    # Preserve the removal patch's context, but fix the symptom locally too:
    # NEW now passes independently of the purported upstream causal change.
    write(ctx.repo_path, "app.py", original.replace(
        "return get_nickname(profile)", "return profile.get('nickname', 'anonymous')"))
    commit_all(ctx.repo_path, "unrelated downstream behavior change")
    git_cmd(ctx.repo_path, "tag", "-f", ctx.new_rev)
    repo = GitRepo(ctx.repo_path)
    before = snapshot(repo)
    state = run_pipeline(PipelineState(), ctx)
    assert state.decision.outcome == DecisionOutcome.ABSTAIN
    assert state.pr_id is None and state.pr_skipped
    assert snapshot(repo) == before


def test_git_provenance_reads_utf8_source_bytes_exactly(tmp_path):
    from phase2_support import commit_all, write

    ctx = context(tmp_path)
    content = "VALUE = '汉字 🧪 café'\n"
    write(ctx.repo_path, "unicode_dependency.py", content)
    sha = commit_all(ctx.repo_path, "UTF-8 dependency source")
    assert GitRepo(ctx.repo_path).file_at(sha, "unicode_dependency.py") == content


def test_non_utf8_git_provenance_fails_closed(tmp_path):
    from github.errors import GitError
    from phase2_support import commit_all
    from pathlib import Path

    ctx = context(tmp_path)
    (Path(ctx.repo_path) / "binary.bin").write_bytes(b"\xff\xfe")
    sha = commit_all(ctx.repo_path, "unsupported binary source")
    with pytest.raises(GitError):
        GitRepo(ctx.repo_path)._run("show", sha + ":binary.bin")


@pytest.mark.parametrize("case", ["ambiguous", "failed_removal_regression"])
def test_valid_provenance_with_insufficient_execution_abstains_without_mutation(tmp_path, case):
    from domain.models import WorkflowRun

    class AmbiguousSandbox(RecordingSandbox):
        def run_container(self, files, argv, env, **kwargs):
            if argv[1] == "probe.py":
                return ContainerResult("already works", "", 0, 0.01, dict(env))
            return super().run_container(files, argv, env, **kwargs)

    ctx = context(tmp_path)
    if case == "ambiguous":
        ctx = replace(ctx, sandbox=AmbiguousSandbox())
    else:
        ctx = replace(ctx, regression_argv=["python", "sentinel.py"])
    repo = GitRepo(ctx.repo_path)
    before = snapshot(repo)
    state = run_pipeline(PipelineState(workflow=WorkflowRun(id="wf:negative", hypothesis_id=None)), ctx)
    assert state.failure is None
    assert state.decision.outcome == DecisionOutcome.ABSTAIN
    assert state.workflow.state.value == "ABSTAINED"
    assert state.pr_id is None and state.pr_skipped
    assert snapshot(repo) == before
