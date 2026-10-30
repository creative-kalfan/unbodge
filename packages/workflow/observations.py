"""Store observations for display, never portable proof capabilities."""
from typing import Literal

from pydantic import Field
from domain.models import UnbodgeModel, WorkflowRun
from reasoning.models import UpstreamAnalysis


class WorkflowObservation(UnbodgeModel):
    id: str
    hypothesis_id: str
    scenario: Literal["SYNTHETIC"]
    execution: Literal["REAL_DOCKER", "NOT_EXECUTED"]
    provenance: Literal["CONTROLLED_FIXTURE", "UNVERIFIED"]
    reasoning: Literal["NOT_REQUESTED", "LIVE_NEBIUS", "UNAVAILABLE"]
    completed_stages: list[str] = Field(default_factory=list)
    workflow: WorkflowRun | None = None
    advisory: UpstreamAnalysis | None = None


def persist_observation(store, state, ctx, *, execution, provenance, reasoning):
    """Explicit demo export; no proposal generation and no ledger serialization."""
    if state.hypothesis is None:
        raise ValueError("a recorded hypothesis is required for dashboard linkage")
    for entity, values in (
        ("upstream_events", [ctx.event]),
        ("workaround_candidates", state.candidates),
        ("causal_hypotheses", [state.hypothesis]),
        ("experiment_runs", state.runs),
        ("evidence", state.evidence),
        ("regression_results", [state.regression] if state.regression else []),
        ("decisions", [state.decision] if state.decision else []),
    ):
        for value in values:
            store.put(entity, value.id, value.model_dump(mode="json"))
    observation = WorkflowObservation(
        id=state.hypothesis.id, hypothesis_id=state.hypothesis.id,
        scenario="SYNTHETIC", execution=execution, provenance=provenance,
        reasoning=reasoning, completed_stages=list(state.completed_stages),
        workflow=state.workflow, advisory=state.advisory,
    )
    store.put("workflow_observations", observation.id, observation.model_dump(mode="json"))
