"""Execution receipts issued by the configured, trusted sandbox boundary.

Receipts are process-local, opaque and backed by immutable JSON snapshots.
Serialized PASS records cannot mint receipts. A restart requires fresh proof.
The sandbox implementation is operator-controlled, never repository/LLM input.
"""
from __future__ import annotations

import json
import secrets
from dataclasses import asdict

from evidence.hashing import canonical_json, sha256_hex
from history.states import HistoryError


def artifact_hash(files: dict[str, str]) -> str:
    return sha256_hex(canonical_json({k: sha256_hex(v) for k, v in files.items()}))


class ExecutionLedger:
    def __init__(self) -> None:
        self._records: dict[str, str] = {}

    def execute(self, sandbox, files, argv, env, *, run_id, git_sha, timeout_s):
        identity = artifact_hash(files)
        result = sandbox.run_container(dict(files), list(argv), dict(env), timeout_s=timeout_s)
        receipt = secrets.token_hex(32)
        self._records[receipt] = canonical_json({
            "run_id": run_id, "git_sha": git_sha, "artifact_hash": identity,
            "argv": list(argv), "requested_env": dict(env), "result": asdict(result),
        })
        return receipt, result

    def verify(self, receipt, *, run_id, git_sha, files_hash, argv, env,
               stdout, stderr, exit_code, duration_s):
        try:
            record = json.loads(self._records[receipt])
        except (KeyError, TypeError):
            raise HistoryError("missing or unknown sandbox execution receipt") from None
        expected = (run_id, git_sha, files_hash, list(argv), dict(env))
        actual = tuple(record[k] for k in ("run_id", "git_sha", "artifact_hash", "argv", "requested_env"))
        raw = record["result"]
        if actual != expected or (stdout, stderr, exit_code, duration_s) != (
            raw["stdout"], raw["stderr"], raw["exit_code"], raw["duration_s"]
        ):
            raise HistoryError("execution receipt does not match artifact, command or result")
        return raw
