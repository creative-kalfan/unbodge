"""Independent proof verification at policy and PR mutation boundaries."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from domain.enums import DecisionOutcome, EvidenceType, PolicyMode, TestStatus, UniverseCell
from evidence.chain import run_payload
from evidence.hashing import sha256_hex
from evidence.validation import validate_item
from experiments.attestation import artifact_hash
from experiments.real import dependency_label_at, prepared_files
from experiments.runner import parse_regression_counts
from github.git import GitRepo
from history.reconstruction import Reconstructor
from history.states import HistoryError
from policy.engine import PolicyInput, evaluate_policy

if TYPE_CHECKING:
    from workflow.stages import PipelineContext, PipelineState


@dataclass(frozen=True)
class RemovalProof:
    context: PipelineContext
    state: PipelineState


def require(condition, message):
    if not condition:
        raise HistoryError(message)


def validate_proof(state, ctx) -> dict[str, str]:
    """Re-derive relationships/artifacts and authenticate every execution result.

The configured metadata client, Git checkout and sandbox/receipt ledger are
trusted application dependencies. Investigation fields and serialized proof
records are untrusted. No confidence, caller PASS or verification boolean is
accepted as authority.
    """
    require(ctx.provenance is not None, "upstream provenance verifier is not configured")
    observation = ctx.provenance.verify(ctx)
    repo = GitRepo(ctx.repo_path)
    old, new = repo.rev_parse(ctx.old_rev), repo.rev_parse(ctx.new_rev)
    require((old, new) == (observation["downstream_old"], observation["downstream_new"]),
            "repository references moved during provenance verification")
    hyp = state.hypothesis
    reg = state.regression
    if hyp is None or reg is None:
        raise HistoryError("incomplete proof")
    require((hyp.id, hyp.issue_id, hyp.fix_commit_id, hyp.release_id, hyp.candidate_id) == (
        f"{ctx.plan_id}:hyp", ctx.issue_id, ctx.fix_id, observation["release"]["id"], state.candidate_id
    ), "hypothesis differs from verified chain")
    candidate = next((c for c in state.candidates if c.id == hyp.candidate_id), None)
    changed = repo.diff_names(observation["introduction"] + "^", observation["introduction"])
    if candidate is None:
        raise HistoryError("candidate is unrelated to workaround introduction")
    require(candidate.file_path in changed,
            "candidate is unrelated to workaround introduction")
    by_id = {e.id: e for e in state.evidence}
    require(len(by_id) == len(state.evidence), "duplicate evidence identities")
    for item in state.evidence:
        require(validate_item(item).valid, "invalid or tampered evidence")

    def evidence(suffix, kind, payload, experiment_id=None):
        item = by_id.get(f"ev:{ctx.plan_id}:{suffix}")
        if item is None:
            raise HistoryError("required evidence is missing")
        require(item.evidence_type == kind and item.payload == payload
                and item.experiment_id == experiment_id, "evidence differs from verified execution/provenance")
        return item

    for suffix, kind in (("issue", EvidenceType.UPSTREAM_ISSUE), ("fix", EvidenceType.FIX_COMMIT),
                         ("release", EvidenceType.RELEASE)):
        evidence(suffix, kind, {"provenance": observation})
    code = evidence("workaround", EvidenceType.CODE_REFERENCE, {})
    require(code.artifact_ref == f"{candidate.file_path}:{candidate.start_line}-{candidate.end_line}",
            "workaround evidence does not reference candidate")
    recon = Reconstructor(repo, ctx.repository_id)
    for label, rev in (("old", old), ("new", new)):
        evidence("dep:" + label, EvidenceType.DEPENDENCY_STATE,
                 {"lock": dict(recon.state_at(rev).lock.packages)})
    require(len(state.runs) == 4 and {r.cell for r in state.runs} == set(UniverseCell),
            "proof requires four distinct counterfactual executions")
    require(state.matrix == {r.cell: r.status for r in state.runs}, "matrix differs from executions")
    artifacts = {}
    for index, run in enumerate(state.runs):
        cell = run.cell
        revision = old if cell in (UniverseCell.A, UniverseCell.B) else new
        files = prepared_files(repo, revision, ctx.workaround_patch,
                               present=cell in (UniverseCell.A, UniverseCell.C))
        identity = artifact_hash(files)
        artifacts[cell] = files
        spec_id = f"{ctx.plan_id}:cell:{cell.value}"
        require(run.id == spec_id + ":run" and run.spec_id == spec_id and run.git_sha == revision
                and run.command == " ".join(ctx.probe_argv)
                and run.test_report.get("artifact_hash") == identity,
                "experiment identity or input artifact mismatch")
        raw = ctx.execution.verify(
            run.test_report.get("receipt"), run_id=run.id, git_sha=revision, files_hash=identity,
            argv=ctx.probe_argv, env=ctx.probe_env, stdout=run.stdout, stderr=run.stderr,
            exit_code=run.exit_code, duration_s=run.duration_s,
        )
        require(run.status == (TestStatus.PASS if raw["exit_code"] == 0 else TestStatus.FAIL),
                "experiment status contradicts execution")
        transcript = "\n".join([spec_id, run.command, run.stdout, run.stderr, str(run.exit_code)])
        hashes = {"transcript": sha256_hex(transcript)}
        hashes.update({name: sha256_hex(content) for name, content in raw["artifacts"].items()})
        require(run.artifact_hashes == hashes and run.test_report == {
            "status": run.status.value, "exit_code": run.exit_code,
            "artifact_hash": identity, "receipt": run.test_report.get("receipt"),
        }, "execution artifacts or report were changed")
        expected_env = {**raw["environment"], "DEP_VERSION": cell.dependency.value,
                        "WORKAROUND": cell.workaround.value, "UNIVERSE_CELL": cell.value}
        package = ctx.provenance.package
        require(run.environment == expected_env and run.dependency_state == {
            package: dependency_label_at(repo, revision, package)
        }, "execution environment or dependency mismatch")
        evidence(f"exp:{cell.value}:{index}", EvidenceType.EXPERIMENT_RESULT, run_payload(run), run.id)
    target = artifacts[UniverseCell.D]
    require(reg.id == f"regression:{ctx.plan_id}:1" and reg.git_sha == new
            and reg.cell == UniverseCell.D and reg.artifact_hash == artifact_hash(target)
            and reg.command == ctx.regression_argv, "regression is not for exact proposed removal")
    raw_regression = ctx.execution.verify(
        reg.execution_receipt, run_id=reg.id, git_sha=new, files_hash=reg.artifact_hash,
        argv=reg.command, env=ctx.regression_env, stdout=reg.stdout, stderr=reg.stderr,
        exit_code=reg.exit_code, duration_s=reg.duration_s,
    )
    require(reg.environment == raw_regression["environment"], "regression environment mismatch")
    require(parse_regression_counts(reg.stdout) == (reg.passed, reg.failed)
            and (reg.exit_code == 0) == (reg.failed == 0 and reg.passed > 0)
            and reg.status == (TestStatus.PASS if reg.exit_code == 0 else TestStatus.FAIL),
            "regression status is not authenticated by execution")
    evidence("reg:0", EvidenceType.TEST_RESULT, reg.model_dump(mode="json"), reg.id)
    refs = (*state.upstream_evidence_ids, *state.evidence_ids)
    require(len(refs) == 11 and len(by_id) == 11 and set(refs) == set(by_id),
            "incomplete or unrelated evidence references")
    return target


def authorize_proposal(repo, decision, files, proof, base_branch):
    require(type(proof) is RemovalProof, "a complete execution-backed removal proof is required")
    ctx, state = proof.context, proof.state
    require(decision.outcome == DecisionOutcome.PROPOSE_REMOVAL
            and decision.policy_mode == PolicyMode.PROPOSE_ONLY, "decision does not authorize a proposal")
    require(Path(ctx.repo_path).resolve() == repo.root.resolve(), "proof belongs to another repository")
    target = validate_proof(state, ctx)
    require(dict(files) == target, "proposed files differ from executed removal artifact")
    require(repo.rev_parse(base_branch) == repo.rev_parse(ctx.new_rev), "proposal base differs from proof")
    require(not repo._run("status", "--porcelain"), "proposal requires a clean repository")
    if state.hypothesis is None or state.regression is None:
        raise HistoryError("incomplete proof")
    expected = evaluate_policy(PolicyInput(
        mode=PolicyMode.PROPOSE_ONLY, evidence_valid=True, matrix=state.matrix,
        regression=state.regression.status,
        evidence_ids=(*state.upstream_evidence_ids, *state.evidence_ids),
        hypothesis_id=state.hypothesis.id, decision_id=ctx.decision_id,
    ))
    require(state.decision is not None and decision.model_dump() == state.decision.model_dump()
            and decision.model_dump(exclude={"created_at"}) == expected.model_dump(exclude={"created_at"})
            and expected.outcome == DecisionOutcome.PROPOSE_REMOVAL,
            "decision does not match revalidated policy and evidence")
    return repo.rev_parse(ctx.new_rev)
