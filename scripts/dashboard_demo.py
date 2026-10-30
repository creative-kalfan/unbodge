"""Explicit synthetic-history demo, real Docker, shared read-only dashboard Store.

Run from the source checkout (fixture builders live in tests). No proposal stage
is executed. Only temporary fixture repositories are initialized/committed.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "packages"), str(ROOT / "tests")]

from api.app import create_app
from api.dashboard import create_dashboard_app
from domain.models import Repository, WorkflowRun
from persistence import MemoryStore
from workflow.observations import persist_observation
from workflow.pipeline import run_pipeline
from workflow.stages import PipelineState, STAGE_NAMES


def build_demo(root, reasoning=None):
    from phase2_support import build_downstream_fixture
    from test_phase2_proof import _context, _releases

    store = MemoryStore()
    ctx = replace(_context(build_downstream_fixture(Path(root) / "downstream"), _releases()),
                  plan_id="demo:synthetic", decision_id="decision:demo:synthetic", reasoning=reasoning)
    ctx = replace(ctx, event=ctx.event.model_copy(update={
        "title": "SYNTHETIC: missing nickname raises KeyError",
        "body": "Controlled fixture: fake-dep 1.0 indexes profile['nickname']; 1.1 uses "
                "profile.get('nickname', 'anonymous'). Downstream catches KeyError. "
                "Hypothesize why the workaround may be obsolete; retain uncertainties. "
                "This is synthetic context, not authenticated live GitHub metadata.",
    }))
    state = run_pipeline(PipelineState(workflow=WorkflowRun(id="wf:demo", hypothesis_id=None)),
                         ctx, stages=STAGE_NAMES[:-1])
    if state.hypothesis is None or state.decision is None:
        raise RuntimeError("Demo did not reach a recorded hypothesis/decision")
    state = state.model_copy(update={"hypothesis": state.hypothesis.model_copy(update={
        "claim": "SYNTHETIC: nickname workaround removal — controlled proof"})})
    repo = Repository(id=ctx.repository_id, full_name="unbodge-fixtures/downstream")
    store.put("repositories", repo.id, repo.model_dump(mode="json"))
    persist_observation(store, state, ctx, execution="REAL_DOCKER" if state.runs else "NOT_EXECUTED",
                        provenance="CONTROLLED_FIXTURE", reasoning=("LIVE_NEBIUS" if state.advisory
                        else "UNAVAILABLE" if reasoning else "NOT_REQUESTED"))

    # A separate investigation loses its configured trust root after hypothesis
    # construction. The same pipeline must refuse policy authorization.
    negative_ctx = replace(ctx, plan_id="demo:insufficient", decision_id="decision:demo:insufficient", reasoning=None)
    negative = run_pipeline(PipelineState(workflow=WorkflowRun(id="wf:negative", hypothesis_id=None)),
                            negative_ctx, stages=STAGE_NAMES[:6])
    negative_ctx = replace(negative_ctx, provenance=None)
    negative = run_pipeline(negative, negative_ctx, stages=("validate_policy",))
    if negative.hypothesis is None or negative.decision.outcome.value != "ABSTAIN" or negative.pr_id:
        raise RuntimeError("Negative demonstration failed")
    negative = negative.model_copy(update={"hypothesis": negative.hypothesis.model_copy(update={
        "claim": "SYNTHETIC: insufficient provenance — ABSTAIN"})})
    persist_observation(store, negative, negative_ctx, execution="NOT_EXECUTED",
                        provenance="UNVERIFIED", reasoning="NOT_REQUESTED")
    if store.list("pr_results"):
        raise RuntimeError("Demo must not create proposals")
    return store, state, negative


def demo_app(store):
    app = create_dashboard_app(create_app(store=store))

    @app.middleware("http")
    async def reads_only(request, call_next):
        from fastapi.responses import JSONResponse
        if request.method not in {"GET", "HEAD"} or not request.url.path.startswith("/api/dashboard/"):
            return JSONResponse({"detail": "Demo exposes dashboard reads only"}, status_code=405)
        return await call_next(request)

    return app


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--live-reasoning", action="store_true", help="One paid Nebius request; no automatic retry")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    reasoning = None
    if args.live_reasoning:
        from env_config import load_env
        from reasoning.nebius import NebiusReasoningProvider
        load_env(ROOT / ".env")
        reasoning = NebiusReasoningProvider(timeout_s=60)
        if not reasoning.configured:
            raise SystemExit("Nebius configuration unavailable; no call made")
    with tempfile.TemporaryDirectory(prefix="unbodge-dashboard-demo-") as tmp:
        store, positive, negative = build_demo(tmp, reasoning)
        print("SYNTHETIC history and provenance; real Docker execution; live GitHub UNVERIFIED", flush=True)
        print("positive:", positive.decision.outcome.value, "negative:", negative.decision.outcome.value, flush=True)
        print("reasoning:", positive.reasoning_status, "proposals: 0 (creation stage excluded)", flush=True)
        if positive.failure:
            print("Positive proof unavailable; inspect test results before recording video.", flush=True)
        if args.serve:
            import uvicorn
            uvicorn.run(demo_app(store), host="127.0.0.1", port=args.port)
        return 0 if positive.decision.outcome.value == "PROPOSE_REMOVAL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
