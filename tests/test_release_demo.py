"""Advisory integration and observation safety, without paid requests."""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.dashboard import create_dashboard_app
from domain.models import WorkflowRun
from persistence import MemoryStore
from reasoning.models import UpstreamAnalysis
from reasoning.errors import ReasoningTimeoutError
from test_proof_authorization import context
from workflow.observations import persist_observation
from workflow.pipeline import run_pipeline
from workflow.stages import PipelineState, STAGE_NAMES


@pytest.mark.parametrize("failure", [False, True])
def test_advisory_cannot_change_authorization_and_failure_is_optional(tmp_path, failure):
    class Provider:
        calls = 0

        def analyze_upstream(self, **kwargs):
            self.calls += 1
            assert kwargs['title'] and kwargs['issue_id']
            if failure:
                raise ReasoningTimeoutError("private transport error")
            return UpstreamAnalysis(issue_id=kwargs['issue_id'], summary="Model says remove",
                                    suspected_cause="model hypothesis", verified=True,
                                    uncertainties=["Not authenticated"])

    provider = Provider()
    ctx = replace(context(tmp_path), reasoning=provider)
    state = run_pipeline(PipelineState(workflow=WorkflowRun(id="wf", hypothesis_id=None)), ctx,
                         stages=STAGE_NAMES[:-1])
    assert state.decision.outcome.value == "PROPOSE_REMOVAL" and not state.failure
    assert provider.calls == 1
    if failure:
        assert state.advisory is None and state.reasoning_status == "UNAVAILABLE"
    else:
        assert state.advisory.verified is False
        assert state.advisory.uncertainties == ["Not authenticated"]
        assert "Model says remove" not in state.hypothesis.claim
    # Already-completed ingestion must not incur a second request.
    run_pipeline(state, ctx, stages=STAGE_NAMES[:-1])
    assert provider.calls == 1
    # Same advisory, absent deterministic trust root: always ABSTAIN, no proposal.
    denied = run_pipeline(state.model_copy(update={"completed_stages": ()}),
                          replace(ctx, provenance=None), stages=("validate_policy",))
    assert denied.decision.outcome.value == "ABSTAIN" and denied.pr_id is None


def test_observations_are_isolated_scrubbed_and_never_authorization(tmp_path, monkeypatch):
    monkeypatch.delenv("UNBODGE_API_TOKEN", raising=False)
    ctx = context(tmp_path)
    state = run_pipeline(PipelineState(workflow=WorkflowRun(id="wf", hypothesis_id=None)),
                         ctx, stages=STAGE_NAMES[:-1])
    state = state.model_copy(update={"advisory": UpstreamAnalysis(issue_id=ctx.issue_id,
        summary="token=ghp_SYNTHETIC_SENTINEL_1234567890", uncertainties=["unverified"])})
    store = MemoryStore()
    persist_observation(store, state, ctx, execution="NOT_EXECUTED", provenance="CONTROLLED_FIXTURE", reasoning="NOT_REQUESTED")
    client = TestClient(create_dashboard_app(create_app(store=store)))
    response = client.get('/api/dashboard/investigations/' + state.hypothesis.id)
    assert response.status_code == 200
    assert 'SYNTHETIC_SENTINEL' not in response.text
    data = response.json()
    assert data['authorization_status'] == 'UNVERIFIED'
    assert data['observation']['advisory']['verified'] is False
    assert data['observation']['completed_stages'] == list(state.completed_stages)
    assert len(data['runs']) == 4 and len(data['regressions']) == 1
    assert data['proposals'] == [] and not store.list('pr_results')
    assert client.get('/api/dashboard/investigations/foreign').status_code == 404


def test_demo_server_blocks_original_api_writes(monkeypatch):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location('dashboard_demo', Path(__file__).parents[1] / 'scripts/dashboard_demo.py')
    demo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(demo)
    monkeypatch.delenv('UNBODGE_API_TOKEN', raising=False)
    client = TestClient(demo.demo_app(MemoryStore()))
    assert client.post('/repositories', json={'full_name': 'x/y'}).status_code == 405
    assert client.post('/api/dashboard/snapshot').status_code == 405
    assert client.get('/api/dashboard/snapshot').status_code == 200
    monkeypatch.setenv('UNBODGE_API_TOKEN', 'synthetic-operator')
    assert client.get('/api/dashboard/snapshot').status_code == 401
