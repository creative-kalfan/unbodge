"""Read-only frontend boundary. All credentials below are synthetic sentinels."""
import json

import pytest
from fastapi.testclient import TestClient

from api import create_app
from api.dashboard import create_dashboard_app
from domain.enums import EvidenceType
from evidence.items import make_evidence
from persistence import MemoryStore


@pytest.fixture
def dashboard(monkeypatch):
    monkeypatch.delenv("UNBODGE_API_TOKEN", raising=False)
    store = MemoryStore()
    store.put("repositories", "r", {"id": "r", "full_name": "team/project"})
    store.put("workaround_candidates", "c", {"id": "c", "repository_id": "r", "file_path": "compat.py", "start_line": 1, "end_line": 3, "description": "Fallback", "detector": "test"})
    store.put("causal_hypotheses", "h", {"id": "h", "candidate_id": "c", "issue_id": "i", "claim": "Investigate fallback", "confidence": 0})
    item = make_evidence(id="e", evidence_type=EvidenceType.UPSTREAM_ISSUE, source="fixture", claim="Issue recorded")
    store.put("evidence", "e", item.model_dump(mode="json"))
    store.put("decisions", "d", {"id": "d", "hypothesis_id": "h", "outcome": "ABSTAIN", "policy_mode": "PROPOSE_ONLY", "rationale": "Missing proof", "evidence_ids": ["e"]})
    backend = create_app(store=store)
    return TestClient(create_dashboard_app(backend)), store, backend


def test_snapshot_uses_exact_backend_and_never_mints_proposals(dashboard):
    client, store, backend = dashboard
    before = store.list("decisions")
    data = client.get("/api/dashboard/snapshot").json()
    assert data["investigations"][0]["id"] == "h"
    assert data["investigations"][0]["workflow_status"] == "UNAVAILABLE"
    assert data["decisions"][0]["outcome"] == "ABSTAIN"
    assert data["decisions"][0]["created_at"] is None  # Never invent a stored timestamp from a model default.
    assert data["health"]["store"] == "MemoryStore"
    assert backend.state.store is store
    assert store.list("decisions") == before and not store.list("pr_results")
    assert client.post("/api/dashboard/snapshot").status_code == 405
    assert client.get("/health").status_code == 200  # original app still mounted


@pytest.mark.parametrize("path", ["/api/dashboard/snapshot", "/api/dashboard/investigations/h"])
def test_new_reads_require_existing_operator_token(dashboard, monkeypatch, path):
    client, _, _ = dashboard
    monkeypatch.setenv("UNBODGE_API_TOKEN", "synthetic-operator")
    assert client.get(path).status_code == 401
    assert client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 403
    assert client.get(path, headers={"Authorization": "Bearer synthetic-operator"}).status_code == 200


def test_missing_and_invalid_identifier(dashboard):
    client, _, _ = dashboard
    assert client.get("/api/dashboard/investigations/missing").status_code == 404
    assert client.get("/api/dashboard/investigations/bad%20id").status_code == 422
    response = client.get("/api/dashboard/investigations/password%3DSYNTHETIC_PRIVATE")
    assert response.status_code == 422
    assert "SYNTHETIC_PRIVATE" not in response.text


def test_evidence_integrity_and_exact_investigation_isolation(dashboard):
    client, store, _ = dashboard
    store.put("experiment_runs", "foreign", {"id": "foreign", "spec_id": "other:cell:A", "stdout": "private"})
    store.put("decisions", "other", {"id": "other", "hypothesis_id": "other", "outcome": "ABSTAIN", "policy_mode": "PROPOSE_ONLY", "rationale": "other", "evidence_ids": ["foreign-evidence"]})
    data = client.get("/api/dashboard/investigations/h").json()
    assert [e["id"] for e in data["evidence"]] == ["e"]
    assert data["runs"] == [] and len(data["decisions"]) == 1
    item = store.get("evidence", "e")
    item["claim"] = "tampered"
    store.put("evidence", "e", item)
    data = client.get("/api/dashboard/investigations/h").json()
    assert data["evidence"][0]["integrity"] == "INVALID"
    assert data["authorization_status"] == "UNVERIFIED"


def test_secrets_and_execution_capabilities_are_not_serialized(dashboard, monkeypatch):
    client, store, _ = dashboard
    sentinel = "ghp_SYNTHETIC_SENTINEL_1234567890"
    monkeypatch.setenv("NEBIUS_API_KEY", sentinel)
    row = store.get("decisions", "d")
    row["rationale"] = "token=" + sentinel
    store.put("decisions", "d", row)
    item = make_evidence(id="secret", evidence_type=EvidenceType.UPSTREAM_ISSUE, source=sentinel, claim=sentinel, payload={"execution_receipt": "opaque-sensitive", "env": {"PASSWORD": sentinel}})
    store.put("evidence", "secret", item.model_dump(mode="json"))
    row["evidence_ids"] = ["secret"]
    store.put("decisions", "d", row)
    for path in ("/api/dashboard/snapshot", "/api/dashboard/investigations/h"):
        response = client.get(path)
        assert response.status_code == 200
        assert sentinel not in response.text and "opaque-sensitive" not in response.text
        assert "no-store" in response.headers["cache-control"]
    assert store.get("evidence", "secret")["claim"] == sentinel


def test_stored_proposal_does_not_imply_authorization(dashboard):
    client, store, _ = dashboard
    store.put("pr_results", "p", {"id": "p", "decision_id": "d", "title": "Contradictory proposal", "branch": "test", "base": "main"})
    data = client.get("/api/dashboard/snapshot").json()
    assert data["proposals"][0]["authorization_status"] == "UNVERIFIED"
    assert data["decisions"][0]["outcome"] == "ABSTAIN"


def test_invalid_records_and_missing_links_are_visible(dashboard):
    client, store, _ = dashboard
    store.put("causal_hypotheses", "bad", {"id": "bad", "claim": []})
    row = store.get("decisions", "d")
    row["evidence_ids"] = ["missing"]
    store.put("decisions", "d", row)
    assert client.get("/api/dashboard/snapshot").json()["invalid_records"] > 0
    assert client.get("/api/dashboard/investigations/h").json()["missing_evidence_ids"] == ["missing"]


def test_store_failure_returns_no_exception_details(dashboard, monkeypatch):
    client, store, _ = dashboard
    def fail(*args, **kwargs):
        raise RuntimeError("password=SYNTHETIC_PRIVATE")
    monkeypatch.setattr(store, "list", fail)
    response = client.get("/api/dashboard/snapshot")
    assert response.status_code == 503
    assert "SYNTHETIC_PRIVATE" not in response.text


def test_exact_linked_execution_is_displayed_without_foreign_cell_join(dashboard):
    from domain.models import ExperimentRun
    from evidence.chain import run_payload
    client, store, _ = dashboard
    run = ExperimentRun(id="run:owned", spec_id="plan:owned:cell:A", cell="A", command="python probe.py", status="PASS",
                        git_sha="a" * 40, duration_s=0.1, test_report={"artifact_hash": "b" * 64, "receipt": "private-receipt"})
    store.put("experiment_runs", run.id, run.model_dump(mode="json"))
    store.put("experiment_runs", "foreign", run.model_copy(update={"id": "foreign", "spec_id": "plan:foreign:cell:A"}).model_dump(mode="json"))
    item = make_evidence(id="exp:owned", evidence_type=EvidenceType.EXPERIMENT_RESULT, source="fixture", claim="Recorded run", experiment_id=run.id, payload=run_payload(run))
    store.put("evidence", item.id, item.model_dump(mode="json"))
    decision = store.get("decisions", "d")
    decision["evidence_ids"] = [item.id]
    store.put("decisions", "d", decision)
    data = client.get("/api/dashboard/investigations/h").json()
    assert [r["id"] for r in data["runs"]] == [run.id]
    assert data["runs"][0]["artifact_hash"] == "b" * 64
    assert "private-receipt" not in json.dumps(data)
    run = run.model_copy(update={"git_sha": "c" * 40})
    store.put("experiment_runs", run.id, run.model_dump(mode="json"))
    data = client.get("/api/dashboard/investigations/h").json()
    assert not data["runs"] and data["authorization_status"] == "UNVERIFIED"


def test_collection_limits_and_secret_shaped_ids_are_visible_as_omissions(dashboard):
    client, store, _ = dashboard
    for i in range(201):
        store.put("repositories", str(i), {"id": str(i), "full_name": "team/project"})
    store.put("pr_results", "secret", {"id": "ghp_SYNTHETIC_SENTINEL_1234567890", "decision_id": "d", "title": "private", "branch": "test"})
    response = client.get("/api/dashboard/snapshot")
    assert response.status_code == 200
    assert len(response.json()["repositories"]) == 200
    assert response.json()["truncated"] and response.json()["invalid_records"] > 0
    assert "ghp_SYNTHETIC" not in response.text


def test_existing_repository_api_ids_and_encoded_investigation_ids_work(dashboard):
    client, store, _ = dashboard
    created = client.post("/repositories", json={"full_name": "actual/backend"})
    assert created.status_code == 201
    data = client.get("/api/dashboard/snapshot").json()
    assert any(r["id"] == created.json()["id"] for r in data["repositories"])
    row = store.get("causal_hypotheses", "h")
    row["id"] = "h:actual/backend"
    store.put("causal_hypotheses", row["id"], row)
    result = client.get("/api/dashboard/investigations/h%3Aactual%2Fbackend")
    assert result.status_code == 200
    assert result.json()["investigation"]["id"] == row["id"]


def test_repository_readiness_assessment_and_negative_cases(dashboard):
    client, _, _ = dashboard
    # Normal readiness check for owner/repo
    res = client.get("/api/dashboard/readiness/psf/requests")
    assert res.status_code == 200
    data = res.json()
    assert data["repository"] == "psf/requests"
    assert data["owner"] == "psf"
    assert data["name"] == "requests"
    assert data["can_connect"] is True
    assert data["proof_ready"] is False
    assert len(data["checks"]) == 9
    check_names = [c["name"] for c in data["checks"]]
    assert "Repository accessible" in check_names
    assert "Dependency manifest detected" in check_names
    assert "Docker execution available" in check_names
    assert "Provenance verification available" in check_names

    # Negative case: invalid identifier / injection attempts rejected
    assert client.get("/api/dashboard/readiness/invalid owner/repo").status_code in (404, 422)
    assert client.get("/api/dashboard/readiness/psf/requests%3Brm").status_code == 422
