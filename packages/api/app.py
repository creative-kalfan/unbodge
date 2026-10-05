"""Production API (Phase 4).

Thin HTTP layer over the existing domain/workflow contracts. The API
never bypasses evidence validation, regression validation, or the
policy gate: it serves stored records (evidence always scrubbed),
replays validated executions, and records human approvals. No endpoint
can mint PROPOSE_REMOVAL; approval never merges.

Write routes are gated by an operator bearer token when
``UNBODGE_API_TOKEN`` is set (constant-time compare); webhooks use
HMAC instead. Without a token the API runs in documented local-dev
mode. Security headers ship on every response.
"""

from __future__ import annotations

import hmac
import os
import time
import uuid

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse

from api.models import DecisionOut, RepositoryIn, RepositoryOut
from api.views import causal_graph, dashboard, evidence_ledger, pr_detail, pr_list, proof_view
from api.webhooks import WebhookError, parse_webhook
from cache import Cache
from cache.memory import MemoryCache
from domain.enums import DecisionOutcome, ReviewVerdict, UniverseCell
from domain.models import EvidenceItem, HumanReview, Repository, UpstreamEvent, utcnow
from evidence.scrub import scrub_item
from experiments.contracts import CounterfactualResult, CounterfactualSuite
from experiments.runner import run_suite
from persistence import Store
from persistence.memory import MemoryStore
from pydantic import ValidationError
from tracing import LocalTracer, TraceEvent, Tracer

VERSION = "4.0.0"


def api_token() -> str:
    return os.environ.get("UNBODGE_API_TOKEN", "")


def _require_token(authorization: str) -> None:
    expected = api_token()
    if not expected:
        return  # local-dev mode (documented); webhook HMAC still enforced
    scheme, _, presented = authorization.partition(" ")
    if scheme.lower() != "bearer" or not presented or len(presented) > 512:
        raise HTTPException(
            status_code=401,
            detail="bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not hmac.compare_digest(presented, expected):
        raise HTTPException(status_code=403, detail="invalid token")


def _slug(value: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in ("-", "_") else "-" for c in value)
    return cleaned.strip("-_")[:64] or "reviewer"


def create_app(
    store: Store | None = None,
    cache: Cache | None = None,
    tracer: Tracer | None = None,
    sandbox=None,
) -> FastAPI:
    app = FastAPI(title="UNBODGE", version=VERSION)
    app.state.store = store or MemoryStore()
    app.state.cache = cache or MemoryCache()
    app.state.tracer = tracer or LocalTracer()
    app.state.sandbox = sandbox

    def _trace(name: str, **attributes: str) -> None:
        app.state.tracer.record(
            TraceEvent(trace_id=uuid.uuid4().hex, name=name, attributes=attributes)
        )

    @app.middleware("http")
    async def _security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; style-src 'unsafe-inline'; frame-ancestors 'none'"
        )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    def _client_ip(request: Request) -> str:
        client = request.client
        host = client.host if client is not None else "unknown"
        return "".join(c for c in host if c.isalnum() or c in (".", ":", "-", "_"))[:64]

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": VERSION, "proof_loop": "intact"}

    @app.post("/webhooks/github", status_code=202)
    async def github_webhook(
        request: Request,
        x_github_event: str = Header(default=""),
        x_github_delivery: str = Header(default=""),
        x_hub_signature_256: str = Header(default=""),
    ) -> dict:
        safe_key = "".join(
            c for c in f"{x_github_event}:{x_github_delivery}" if c.isalnum() or c in "-_."
        )[:96]
        if not app.state.cache.allow(f"webhook:{_client_ip(request)}:{safe_key}", limit=60, window_s=60):
            raise HTTPException(status_code=429, detail="webhook rate limit exceeded")
        if not app.state.cache.allow("webhook:global", limit=600, window_s=60):
            raise HTTPException(status_code=429, detail="webhook rate limit exceeded")
        body = await request.body()
        try:
            record = parse_webhook(
                event=x_github_event,
                delivery_id=x_github_delivery,
                signature=x_hub_signature_256,
                body=body,
            )
        except WebhookError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if app.state.cache.get(f"webhook:receipt:{record['delivery_id']}"):
            return {"delivery_id": record["delivery_id"], "duplicate": True}
        if not app.state.cache.acquire_lock(
            f"webhook:lock:{record['delivery_id']}", ttl_s=300
        ):
            return {"delivery_id": record["delivery_id"], "duplicate": True}
        try:
            event = UpstreamEvent(
                id=f"evt:{record['delivery_id']}",
                repository_id=record["repository"] or "repo:unknown",
                title=f"github {record['event']}:{record['action'] or 'event'}",
                body="",
                source="github-webhook",
            )
            app.state.store.put("upstream_events", event.id, event.model_dump(mode="json"))
            app.state.cache.set(
                f"webhook:receipt:{record['delivery_id']}", event.id, ttl_s=86400
            )
        finally:
            app.state.cache.release_lock(f"webhook:lock:{record['delivery_id']}")
        _trace("webhook.received", event=record["event"], delivery=record["delivery_id"])
        return {"delivery_id": record["delivery_id"], "event_id": event.id}

    @app.post("/repositories", response_model=RepositoryOut, status_code=201)
    def create_repository(payload: RepositoryIn, authorization: str = Header(default="")) -> dict:
        _require_token(authorization)
        repo = Repository(id=f"repo:{payload.full_name}", full_name=payload.full_name)
        app.state.store.put("repositories", repo.id, repo.model_dump(mode="json"))
        return {"id": repo.id, "full_name": repo.full_name}

    @app.get("/repositories")
    def list_repositories(limit: int = 100) -> dict:
        return {"repositories": app.state.store.list("repositories", limit=min(max(limit, 1), 500))}

    @app.get("/events")
    def list_events(limit: int = 100) -> dict:
        return {"events": app.state.store.list("upstream_events", limit=min(max(limit, 1), 500))}

    @app.get("/candidates")
    def list_candidates(limit: int = 100) -> dict:
        return {
            "candidates": app.state.store.list(
                "workaround_candidates", limit=min(max(limit, 1), 500)
            )
        }

    @app.get("/experiments/{experiment_id}")
    def get_experiment(experiment_id: str) -> dict:
        record = app.state.store.get("experiments", experiment_id[:256])
        if record is None:
            raise HTTPException(status_code=404, detail="experiment not found")
        return record

    @app.get("/evidence/{evidence_id}")
    def get_evidence(evidence_id: str) -> dict:
        record = app.state.store.get("evidence", evidence_id[:256])
        if record is None:
            raise HTTPException(status_code=404, detail="evidence not found")
        try:
            item = EvidenceItem(**record)
        except Exception:
            raise HTTPException(status_code=422, detail="stored record invalid")
        return scrub_item(item).model_dump(mode="json")

    @app.get("/decisions/{decision_id}", response_model=DecisionOut)
    def get_decision(decision_id: str) -> dict:
        record = app.state.store.get("decisions", decision_id[:256])
        if record is None:
            raise HTTPException(status_code=404, detail="decision not found")
        try:
            outcome = record["outcome"]
            rationale = record.get("rationale", "")
            record_id = record["id"]
            if not isinstance(outcome, str) or not outcome:
                raise KeyError("outcome")
        except (KeyError, TypeError, AttributeError):
            raise HTTPException(status_code=422, detail="stored record invalid")
        return {"id": record_id, "outcome": outcome, "rationale": rationale}

    @app.post("/experiments/{experiment_id}/rerun")
    def rerun_experiment(
        experiment_id: str, authorization: str = Header(default="")
    ) -> dict:
        from domain.models import ExperimentSpec

        _require_token(authorization)
        if not app.state.cache.allow(f"rerun:{experiment_id[:128]}", limit=10, window_s=60):
            raise HTTPException(status_code=429, detail="rerun rate limit exceeded")
        if app.state.sandbox is None:
            raise HTTPException(status_code=503, detail="no execution backend configured")
        record = app.state.store.get("experiments", experiment_id[:256])
        if record is None:
            raise HTTPException(status_code=404, detail="experiment not found")
        try:
            specs = {
                UniverseCell(cell): ExperimentSpec(**spec)
                for cell, spec in record["specs"].items()
            }
            suite = CounterfactualSuite(specs=specs)
        except Exception:
            raise HTTPException(status_code=422, detail="stored record invalid")
        result: CounterfactualResult = run_suite(sandbox=app.state.sandbox, suite=suite)
        for run in result.runs.values():
            app.state.store.put("experiment_runs", run.id, run.model_dump(mode="json"))
        result_id = f"{experiment_id[:200]}::result"
        matrix = {cell.value: status.value for cell, status in result.matrix.items()}
        app.state.store.put(
            "experiments",
            result_id,
            {
                "id": result_id,
                "suite_id": experiment_id,
                "matrix": matrix,
                "is_canonical_success": result.is_canonical_success,
            },
        )
        _trace("experiment.rerun", suite=experiment_id, result=result_id)
        return {"result_id": result_id, "matrix": matrix}

    @app.post("/decisions/{decision_id}/approve", status_code=201)
    def approve_decision(decision_id: str, payload: dict, authorization: str = Header(default="")) -> dict:
        _require_token(authorization)
        reviewer = str(payload.get("reviewer", ""))
        if not reviewer.strip():
            raise HTTPException(status_code=422, detail="reviewer is required")
        record = app.state.store.get("decisions", decision_id[:256])
        if record is None:
            raise HTTPException(status_code=404, detail="decision not found")
        if record.get("outcome") != DecisionOutcome.PROPOSE_REMOVAL.value:
            raise HTTPException(
                status_code=422,
                detail="only PROPOSE_REMOVAL decisions can be approved; nothing is auto-merged",
            )
        slug = _slug(reviewer.strip())
        try:
            review = HumanReview(
                id=f"{decision_id[:128]}:approval:{slug}",
                decision_id=decision_id[:256],
                reviewer=reviewer.strip()[:64],
                verdict=ReviewVerdict.APPROVE,
                comment=str(payload.get("comment", ""))[:1024],
                created_at=utcnow(),
            )
        except ValidationError:
            raise HTTPException(status_code=422, detail="stored record invalid")
        app.state.store.put("human_reviews", review.id, review.model_dump(mode="json"))
        _trace("decision.approve", decision=decision_id, reviewer=review.reviewer)
        return {"review_id": review.id, "decision_id": decision_id, "merged": False}

    @app.get("/ui/", response_class=HTMLResponse)
    def ui_dashboard() -> HTMLResponse:
        return dashboard(app.state.store)

    @app.get("/ui/graph", response_class=HTMLResponse)
    def ui_graph() -> HTMLResponse:
        return causal_graph(app.state.store)

    @app.get("/ui/proof/{result_id}", response_class=HTMLResponse)
    def ui_proof(result_id: str) -> HTMLResponse:
        return proof_view(app.state.store, result_id[:256])

    @app.get("/ui/evidence", response_class=HTMLResponse)
    def ui_evidence() -> HTMLResponse:
        return evidence_ledger(app.state.store)

    @app.get("/ui/prs", response_class=HTMLResponse)
    def ui_prs() -> HTMLResponse:
        return pr_list(app.state.store)

    @app.get("/ui/prs/{pr_id}", response_class=HTMLResponse)
    def ui_pr_detail(pr_id: str) -> HTMLResponse:
        return pr_detail(app.state.store, pr_id[:256])

    return app


__all__ = ["VERSION", "api_token", "create_app"]
