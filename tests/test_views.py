"""Judge-facing views: dashboard, causal graph, proof, ledger, PRs."""

from fastapi.testclient import TestClient

from api import create_app
from domain.enums import EvidenceType
from evidence.items import make_evidence
from persistence import MemoryStore


def _seeded():
    store = MemoryStore()
    store.put("repositories", "repo:a/b", {"id": "repo:a/b", "full_name": "a/b"})
    store.put("decisions", "d:1", {
        "id": "d:1", "hypothesis_id": "h", "outcome": "PROPOSE_REMOVAL",
        "policy_mode": "PROPOSE_ONLY", "rationale": "canonical proof holds",
        "evidence_ids": ["ev:1"], "created_at": "2026-01-01T00:00:00+00:00",
    })
    store.put("decisions", "d:2", {
        "id": "d:2", "hypothesis_id": "h", "outcome": "ABSTAIN",
        "policy_mode": "PROPOSE_ONLY", "rationale": "weak matrix",
        "evidence_ids": ["ev:1"], "created_at": "2026-01-01T00:00:00+00:00",
    })
    item = make_evidence(
        id="ev:1", evidence_type=EvidenceType.CODE_REFERENCE, source="ast-scan",
        claim="try/except fallback guards lookup",
    )
    store.put("evidence", item.id, item.model_dump(mode="json"))
    store.put("experiments", "suite:1::result", {
        "id": "suite:1::result", "suite_id": "suite:1",
        "matrix": {"A": "PASS", "B": "FAIL", "C": "PASS", "D": "PASS"},
        "is_canonical_success": True,
    })
    for cell, outcome in (("A", "PASS"), ("B", "FAIL"), ("C", "PASS"), ("D", "PASS")):
        store.put("experiment_runs", f"run:{cell}", {
            "id": f"run:{cell}", "spec_id": f"suite:1:cell:{cell}", "cell": cell,
            "command": "probe", "stdout": "ok", "stderr": "",
            "exit_code": 0 if outcome == "PASS" else 1, "duration_s": 0.1,
            "status": outcome, "environment": {"DEP_VERSION": "OLD", "WORKAROUND": "PRESENT"},
            "git_sha": "a" * 40, "dependency_state": {"fake-dep": "fake-dep==1.0"},
            "test_report": {}, "artifact_hashes": {"t": "b" * 64},
        })
    store.put("pr_results", "pr:1", {
        "id": "pr:1", "decision_id": "d:1", "title": "Remove workaround",
        "body": "Matrix: A=PASS", "branch": "unbodge/w", "base": "main",
        "created_at": "2026-01-01T00:00:00+00:00",
    })
    return TestClient(create_app(store=store))


def test_dashboard_counts_state():
    body = _seeded().get("/ui/").text
    assert "UNBODGE dashboard" in body
    assert "proposed removals: <b>1</b>" in body
    assert "abstentions: <b>1</b>" in body
    assert "canonical proof holds" in body


def test_causal_graph_renders_svg_and_chain():
    client = _seeded()
    body = client.get("/ui/graph").text
    assert "<svg" in body and "try/except fallback" in body
    assert "workaround" in body and "experiment" in body
    empty = TestClient(create_app(store=MemoryStore())).get("/ui/graph").text
    assert "No evidence recorded yet" in empty


def test_proof_view_shows_matrix_and_runs():
    body = _seeded().get("/ui/proof/suite:1::result").text
    for token in ("A", "B", "FAIL", "PASS", "fake-dep", "PRESENT", "bbbbbbbb"):
        assert token in body
    assert _seeded().get("/ui/proof/missing").status_code == 404


def test_evidence_ledger_and_pr_views():
    client = _seeded()
    ledger = client.get("/ui/evidence").text
    assert "Evidence ledger" in ledger and "CODE_REFERENCE" in ledger
    prs = client.get("/ui/prs").text
    assert "Remove workaround" in prs
    detail = client.get("/ui/prs/pr:1").text
    assert "PROPOSE_REMOVAL" in detail and "Matrix: A=PASS" in detail
    assert client.get("/ui/prs/missing").status_code == 404


def test_views_escape_untrusted_content():
    store = MemoryStore()
    store.put("decisions", "d:x", {
        "id": "d:x", "hypothesis_id": "h", "outcome": "ABSTAIN",
        "policy_mode": "PROPOSE_ONLY",
        "rationale": "<script>alert(1)</script>",
        "evidence_ids": [], "created_at": "2026-01-01T00:00:00+00:00",
    })
    body = TestClient(create_app(store=store)).get("/ui/").text
    assert "<script>" not in body
    assert "&lt;script&gt;" in body
