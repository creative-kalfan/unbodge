"""Execution records must preserve streams and reject even whitespace tampering."""
import pytest

from domain.models import ExperimentRun, RegressionResult
from experiments.attestation import ExecutionLedger, artifact_hash
from history.states import HistoryError
from sandbox.docker import ContainerResult


@pytest.mark.parametrize("kind", [ExperimentRun, RegressionResult])
def test_exact_streams_survive_domain_roundtrip_and_receipt_check(kind):
    class Sandbox:
        def run_container(self, files, argv, env, **kwargs):
            return ContainerResult("  passed=3 failed=0\r\n", "\twarning\n", 0, .25, env)

    files, argv, env = {"probe.py": "print('ok')\n"}, ["python", "probe.py"], {"VALUE": " padded "}
    ledger = ExecutionLedger()
    receipt, result = ledger.execute(Sandbox(), files, argv, env, run_id="run", git_sha="a" * 40, timeout_s=10)
    fields = dict(id="run", status="PASS", git_sha="a" * 40, stdout=result.stdout,
                  stderr=result.stderr, exit_code=0, duration_s=.25, environment=env)
    if kind is ExperimentRun:
        fields.update(spec_id="spec", cell="A", command="python probe.py")
    else:
        fields.update(suite="regression", passed=3, failed=0, command=argv)
    record = kind.model_validate_json(kind(**fields).model_dump_json())
    assert record.environment == env
    args = dict(run_id=record.id, git_sha=record.git_sha, files_hash=artifact_hash(files),
                argv=argv, env=env, stdout=record.stdout, stderr=record.stderr,
                exit_code=record.exit_code, duration_s=record.duration_s)
    ledger.verify(receipt, **args)
    with pytest.raises(HistoryError, match="does not match"):
        ledger.verify(receipt, **{**args, "stdout": record.stdout.rstrip()})
