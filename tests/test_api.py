"""Production API: endpoints, gates, webhook security, idempotency."""

import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from api import create_app
from domain.enums import EvidenceType
from evidence.items import make_evidence
from experiments.planner import plan_counterfactual
from persistence import MemoryStore
from sandbox.local import LocalDeterministicSandbox
from experiments.synthetic import synthetic_handler, regression_handler


def _client(**kwargs):
    store = kwargs.pop("store", None) or MemoryStore()
    return TestClient(create_app(store=store, **kwargs)), store


def _signed(body: bytes, secret: str = "test-secret") -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_health():
    client, _ = _client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["proof_loop"] == "intact"


def test_repositories_round_trip_and_validation():
    client, _ = _client()
    created = client.post("/repositories", json={"full_name": "acme/downstream"})
    assert created.status_code == 201
    assert created.json()["id"] == "repo:acme/downstream"
    assert client.get("/repositories").json()["repositories"][0]["full_name"] == "acme/downstream"
    bad = client.post("/repositories", json={"full_name": "not-a-repo"})
    assert bad.status_code == 422
    assert client.post("/repositories", json={}).status_code == 422


def test_webhook_ingest_validates_and_dedupes(monkeypatch):
    monkeypatch.setenv("UNBODGE_WEBHOOK_SECRET", "test-secret")
    client, store = _client()
    body = json.dumps({
        "action": "opened",
        "repository": {"full_name": "acme/downstream"},
        "issue": {"number": 7, "title": "bug"},
    }).encode()
    headers = {
        "X-GitHub-Event": "issues",
        "X-GitHub-Delivery": "delivery-1",
        "X-Hub-Signature-256": _signed(body),
    }
    first = client.post("/webhooks/github", content=body, headers=headers)
    assert first.status_code == 202
    assert first.json()["event_id"] == "evt:delivery-1"
    events = client.get("/events").json()["events"]
    assert len(events) == 1 and "Secret" not in json.dumps(events)
    duplicate = client.post("/webhooks/github", content=body, headers=headers)
    assert duplicate.json()["duplicate"] is True
    assert len(client.get("/events").json()["events"]) == 1


def test_webhook_rejects_forgery_and_shape():
    import os

    os.environ["UNBODGE_WEBHOOK_SECRET"] = "test-secret"
    try:
        client, _ = _client()
        body = b'{"action": "opened"}'
        headers = {
            "X-GitHub-Event": "issues",
            "X-GitHub-Delivery": "d2",
            "X-Hub-Signature-256": "sha256=" + "0" * 64,
        }
        assert client.post("/webhooks/github", content=body, headers=headers).status_code == 400
        headers["X-Hub-Signature-256"] = _signed(body)
        headers["X-GitHub-Event"] = "fork"
        assert client.post("/webhooks/github", content=body, headers=headers).status_code == 400
        headers["X-GitHub-Event"] = "issues"
        headers["X-GitHub-Delivery"] = ""
        assert client.post("/webhooks/github", content=body, headers=headers).status_code == 400
        assert client.post("/webhooks/github", content=b"not json", headers={
            "X-GitHub-Event": "issues", "X-GitHub-Delivery": "d3",
            "X-Hub-Signature-256": _signed(b"not json"),
        }).status_code == 400
    finally:
        del os.environ["UNBODGE_WEBHOOK_SECRET"]


def test_webhook_rejects_oversized_payload(monkeypatch):
    monkeypatch.setenv("UNBODGE_WEBHOOK_SECRET", "s")
    client, _ = _client()
    body = b'{"x": "' + b"y" * (1_000_001 + 10) + b'"}'
    response = client.post("/webhooks/github", content=body, headers={
        "X-GitHub-Event": "issues", "X-GitHub-Delivery": "big",
        "X-Hub-Signature-256": _signed(body, "s"),
    })
    assert response.status_code == 400


def test_webhook_fails_closed_without_secret(monkeypatch):
    monkeypatch.delenv("UNBODGE_WEBHOOK_SECRET", raising=False)
    client, _ = _client()
    body = json.dumps({"action": "opened"}).encode()
    response = client.post("/webhooks/github", content=body, headers={
        "X-GitHub-Event": "issues", "X-GitHub-Delivery": "d-nosecret",
        "X-Hub-Signature-256": _signed(body, "anything"),
    })
    assert response.status_code == 400


def test_bearer_token_gates_writes(monkeypatch):
    monkeypatch.setenv("UNBODGE_API_TOKEN", "operator-secret")
    client, _ = _client()
    assert client.post("/repositories", json={"full_name": "a/b"}).status_code == 401
    bad = client.post(
        "/repositories", json={"full_name": "a/b"},
        headers={"Authorization": "Bearer wrong"},
    )
    assert bad.status_code == 403
    good = client.post(
        "/repositories", json={"full_name": "a/b"},
        headers={"Authorization": "Bearer operator-secret"},
    )
    assert good.status_code == 201
    assert client.get("/health").status_code == 200  # reads stay public


def test_security_headers_present():
    client, _ = _client()
    headers = client.get("/health").headers
    assert "content-security-policy" in headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"


def test_reviewer_name_slugified():
    client, store = _client()
    store.put("decisions", "d:9", {
        "id": "d:9", "hypothesis_id": "h", "outcome": "PROPOSE_REMOVAL",
        "policy_mode": "PROPOSE_ONLY", "rationale": "proof",
        "evidence_ids": ["ev:1"], "created_at": "2026-01-01T00:00:00+00:00",
    })
    response = client.post("/decisions/d:9/approve", json={"reviewer": "a/b c"})
    assert response.status_code == 201
    assert response.json()["review_id"] == "d:9:approval:a-b-c"


def test_poisoned_rows_do_not_break_views():
    client, store = _client()
    store.put("decisions", "d:evil", {
        "id": 12345, "outcome": {"$ne": 1}, "rationale": ["x"],
        "evidence_ids": "nope", "policy_mode": "X",
    })
    store.put("pr_results", "pr:evil", {
        "id": "pr:evil", "title": {"nested": True}, "branch": ["b"],
        "base": None, "body": 42, "decision_id": {"evil": True},
    })
    assert client.get("/ui/").status_code == 200
    assert client.get("/ui/prs").status_code == 200
    assert client.get("/ui/prs/pr:evil").status_code == 200
    assert client.get("/decisions/d:evil").status_code == 422


def test_missing_records_404():
    client, _ = _client()
    assert client.get("/experiments/nope").status_code == 404
    assert client.get("/evidence/nope").status_code == 404
    assert client.get("/decisions/nope").status_code == 404
    assert client.post("/experiments/nope/rerun").status_code in (404, 503)
    assert client.post("/decisions/nope/approve", json={"reviewer": "a"}).status_code == 404


def test_evidence_endpoint_serves_scrubbed_view():
    client, store = _client()
    item = make_evidence(
        id="ev:sec", evidence_type=EvidenceType.CODE_REFERENCE, source="s",
        claim="token sk-live-ABCDEF1234567890 leaked in output",
    )
    store.put("evidence", item.id, item.model_dump(mode="json"))
    body = client.get(f"/evidence/{item.id}").json()
    assert body["hash"] == item.hash
    assert "sk-live" not in body["claim"]
    assert body["redactions"] >= 1


def test_rerun_requires_backend_and_replays_deterministically():
    client, store = _client()
    suite = plan_counterfactual("api:proof")
    store.put("experiments", "suite:1", {
        "id": "suite:1",
        "specs": {cell.value: spec.model_dump(mode="json") for cell, spec in suite.specs.items()},
    })
    assert client.post("/experiments/suite:1/rerun").status_code == 503

    sandbox = LocalDeterministicSandbox(handlers={
        "synthetic-check": synthetic_handler, "regression-suite": regression_handler,
    })
    client2, store2 = _client(sandbox=sandbox)
    store2.put("experiments", "suite:1", {
        "id": "suite:1",
        "specs": {cell.value: spec.model_dump(mode="json") for cell, spec in suite.specs.items()},
    })
    first = client2.post("/experiments/suite:1/rerun")
    assert first.status_code == 200
    assert first.json()["matrix"] == {"A": "PASS", "B": "FAIL", "C": "PASS", "D": "PASS"}
    second = client2.post("/experiments/suite:1/rerun")
    assert second.json()["result_id"] == first.json()["result_id"]
    stored = client2.get("/experiments/suite:1::result").json()
    assert stored["is_canonical_success"] is True
    bad = dict(store2.get("experiments", "suite:1"))
    bad["specs"] = {"A": {"id": "broken"}}
    store2.put("experiments", "broken:1", {"id": "broken:1", **bad, "specs": {"A": {"id": "x"}}})
    assert client2.post("/experiments/broken:1/rerun").status_code == 422


def test_approve_records_review_without_merging():
    client, store = _client()
    store.put("decisions", "d:1", {
        "id": "d:1", "hypothesis_id": "h", "outcome": "PROPOSE_REMOVAL",
        "policy_mode": "PROPOSE_ONLY", "rationale": "proof",
        "evidence_ids": ["ev:1"], "created_at": "2026-01-01T00:00:00+00:00",
    })
    store.put("decisions", "d:2", {
        "id": "d:2", "hypothesis_id": "h", "outcome": "ABSTAIN",
        "policy_mode": "PROPOSE_ONLY", "rationale": "weak",
        "evidence_ids": ["ev:1"], "created_at": "2026-01-01T00:00:00+00:00",
    })
    assert client.get("/decisions/d:1").json()["outcome"] == "PROPOSE_REMOVAL"
    denied = client.post("/decisions/d:2/approve", json={"reviewer": "alice"})
    assert denied.status_code == 422
    assert client.post("/decisions/d:1/approve", json={}).status_code == 422
    approved = client.post(
        "/decisions/d:1/approve", json={"reviewer": "alice", "comment": "proof checked"}
    )
    assert approved.status_code == 201
    assert approved.json()["merged"] is False
    assert approved.json()["review_id"] == "d:1:approval:alice"
    # decision itself is untouched by approval
    assert client.get("/decisions/d:1").json()["outcome"] == "PROPOSE_REMOVAL"


def test_api_never_mints_proposals():
    import api.app as app_module
    import inspect

    source = inspect.getsource(app_module)
    assert "PROPOSE_REMOVAL" in source  # only read for the approve gate
    assert "RemovalDecision(" not in source
    assert "evaluate_policy" not in source
