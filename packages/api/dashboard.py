"""Isolated, read-only dashboard adapter over an existing API application's Store.

No proof evaluation, execution, Git mutation, credential checks against external
services, or workflow orchestration occurs here. Stored records are observations,
never live authorization capabilities. Existing API modules are untouched.
"""
from __future__ import annotations

import os
import re
from typing import Literal, overload

from fastapi import Depends, FastAPI, Header, HTTPException, Path, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from api.app import _require_token, create_app
from domain.models import (CausalHypothesis, EvidenceItem, ExperimentRun, PullRequestResult,
                           RegressionResult, RemovalDecision, Repository, UpstreamEvent,
                           WorkaroundCandidate, utcnow)
from evidence.chain import run_payload
from evidence.scrub import scrub_text
from evidence.validation import validate_item
from workflow.observations import WorkflowObservation

LIMIT = 200
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9:._/-]{0,255}$"


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Record(Output):
    id: str
    title: str
    repository_id: str | None = None
    repository: str | None = None
    file_path: str | None = None
    created_at: str | None = None


class Investigation(Record):
    candidate_id: str
    issue_id: str
    fix_id: str | None = None
    release_id: str | None = None
    workflow_status: str = "UNAVAILABLE"


class Decision(Output):
    id: str
    hypothesis_id: str | None
    outcome: str
    policy_mode: str
    rationale: str
    evidence_ids: list[str]
    created_at: str | None


class Proposal(Output):
    id: str
    decision_id: str
    title: str
    branch: str
    base: str | None
    body: str
    authorization_status: Literal["UNVERIFIED"] = "UNVERIFIED"


class Evidence(Output):
    id: str
    evidence_type: str
    source: str
    claim: str
    hash: str | None = None
    integrity: Literal["VALID", "INVALID"]
    artifact_ref: str | None = None
    experiment_id: str | None = None
    timestamp: str | None = None


class Run(Output):
    id: str
    cell: str
    status: str
    git_sha: str
    artifact_hash: str | None
    duration_s: float
    exit_code: int
    receipt_status: Literal["NOT_EXPOSED_PROCESS_LOCAL"] = "NOT_EXPOSED_PROCESS_LOCAL"


class Regression(Output):
    id: str
    status: str
    passed: int
    failed: int
    git_sha: str | None
    artifact_hash: str | None


class ReadinessCheck(Output):
    name: str
    status: Literal["PASS", "MISSING", "UNSUPPORTED", "UNVERIFIED"]
    explanation: str


class ReadinessAssessment(Output):
    repository: str
    owner: str
    name: str
    default_branch: str | None = None
    accessible: bool
    checks: list[ReadinessCheck]
    can_connect: bool
    proof_ready: bool
    summary: str


class Integration(Output):
    name: str
    configuration: str
    authentication: Literal["NOT_TESTED"] = "NOT_TESTED"
    operation: Literal["NOT_TESTED", "AVAILABLE", "UNAVAILABLE"] = "NOT_TESTED"
    note: str


class Health(Output):
    store: str
    cache: str
    authentication: Literal["BEARER_REQUIRED", "LOCAL_DEV_READ_ONLY"]
    integrations: list[Integration]


class Snapshot(Output):
    observed_at: str
    repositories: list[Record]
    events: list[Record]
    candidates: list[Record]
    investigations: list[Investigation]
    decisions: list[Decision]
    proposals: list[Proposal]
    health: Health
    truncated: bool
    invalid_records: int


class Detail(Output):
    investigation: Investigation
    decisions: list[Decision]
    evidence: list[Evidence]
    runs: list[Run]
    regressions: list[Regression]
    proposals: list[Proposal]
    missing_evidence_ids: list[str]
    authorization_status: Literal["UNVERIFIED"] = "UNVERIFIED"
    workflow_status: Literal["UNAVAILABLE"] = "UNAVAILABLE"
    warnings: list[str]
    observation: dict | None = None


def _text(value: str) -> str:
    # Scrub before bounding: truncating first can leave partial credentials.
    if len(value) > 100_000:
        return "[oversized text omitted]"
    cleaned = scrub_text(value)[0]
    cleaned = re.sub(r"(?:gh[pousr]_|github_pat_|sk-)[A-Za-z0-9_-]{8,}", "[redacted]", cleaned)
    cleaned = re.sub(r"(?i)(https?://)[^\s/@]+:[^\s/@]+@", r"\1[redacted]@", cleaned)
    return cleaned[:4096]


@overload
def _id(value: str) -> str: ...


@overload
def _id(value: None) -> None: ...


def _id(value: str | None) -> str | None:
    if value is None:
        return None
    if not re.fullmatch(ID_PATTERN, value) or _text(value) != value:
        raise ValueError("unsupported identifier")
    return value


def _model(model, row):
    parsed = model.model_validate(row)
    _id(parsed.id)
    return parsed


def _decision(row) -> Decision:
    d = _model(RemovalDecision, row)
    return Decision(id=d.id, hypothesis_id=_id(d.hypothesis_id), outcome=d.outcome.value,
                    policy_mode=d.policy_mode.value, rationale=_text(d.rationale),
                    evidence_ids=[_id(x) for x in d.evidence_ids],
                    created_at=d.created_at.isoformat() if row.get("created_at") is not None else None)


def _proposal(row) -> Proposal:
    p = _model(PullRequestResult, row)
    return Proposal(id=p.id, decision_id=_id(p.decision_id), title=_text(p.title),
                    branch=_text(p.branch), base=_text(p.base) if row.get("base") is not None else None, body=_text(p.body))


def _investigation(row, store) -> Investigation:
    h = _model(CausalHypothesis, row)
    candidate = store.get("workaround_candidates", _id(h.candidate_id))
    repo_id = path = repo_name = None
    if candidate is not None:
        c = _model(WorkaroundCandidate, candidate)
        if c.id != h.candidate_id:
            raise ValueError("candidate identity mismatch")
        repo_id, path = _id(c.repository_id), _text(c.file_path)
        repo = store.get("repositories", repo_id)
        if repo is not None:
            r = _model(Repository, repo)
            if r.id == repo_id:
                repo_name = _text(r.full_name)
    status = "UNAVAILABLE"
    observation = store.get("workflow_observations", h.id)
    if observation is not None:
        obs = WorkflowObservation.model_validate(observation)
        if obs.id != h.id or obs.hypothesis_id != h.id:
            raise ValueError("observation identity mismatch")
        if obs.workflow:
            status = obs.workflow.state.value
    return Investigation(id=h.id, title=_text(h.claim), candidate_id=_id(h.candidate_id), workflow_status=status,
                         issue_id=_id(h.issue_id), fix_id=_id(h.fix_commit_id), release_id=_id(h.release_id),
                         repository_id=repo_id, repository=repo_name, file_path=path)


def _health(backend) -> Health:
    store = type(backend.state.store).__name__
    cache = type(backend.state.cache).__name__
    store = store if store in {"MemoryStore", "PostgresStore"} else "CustomStore"
    cache = cache if cache in {"MemoryCache", "RedisCache"} else "CustomCache"
    integrations = []
    for name, keys in (("Nebius Token Factory", ("NEBIUS_API_KEY", "NEBIUS_MODEL")),
                       ("GitHub", ("GITHUB_TOKEN",)), ("Tavily", ("TAVILY_API_KEY",)),
                       ("LangSmith", ("LANGSMITH_API_KEY",))):
        integrations.append(Integration(name=name, configuration="CONFIGURED" if all(os.environ.get(k) for k in keys) else "NOT_CONFIGURED",
                                        note="Environment presence only; authentication and workflow integration not tested."))
    integrations.extend([
        Integration(name="PostgreSQL", configuration=store, note="Actual application Store; DSN presence does not establish PostgreSQL use."),
        Integration(name="Redis", configuration=cache, note="Actual application Cache; no network probe performed."),
        Integration(name="Docker execution", configuration="ATTACHED" if backend.state.sandbox is not None else "NOT_ATTACHED",
                    operation="UNAVAILABLE" if backend.state.sandbox is None else "NOT_TESTED",
                    note="Sandbox attachment only; no container or paid service is started by this page."),
    ])
    return Health(store=store, cache=cache, authentication="BEARER_REQUIRED" if os.environ.get("UNBODGE_API_TOKEN") else "LOCAL_DEV_READ_ONLY",
                  integrations=integrations)


def create_dashboard_app(backend: FastAPI | None = None) -> FastAPI:
    """Pass the running backend instance to share precisely its configured backends.

    Default construction mirrors api.server's current in-memory configuration.
    This factory does not repair worker persistence or DSN/cache wiring.
    """
    backend = backend if backend is not None else create_app()
    app = FastAPI(title="UNBODGE dashboard reads", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.backend = backend

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        # Default FastAPI validation details echo the raw identifier/input.
        return JSONResponse({"detail": "Invalid dashboard request"}, status_code=422)

    def auth(authorization: str = Header(default="")):
        _require_token(authorization)

    @app.middleware("http")
    async def headers(request: Request, call_next):
        if not request.url.path.startswith("/api/dashboard/"):
            return await call_next(request)
        if request.url.path.startswith("/api/dashboard/") and request.method not in {"GET", "HEAD"}:
            return JSONResponse({"detail": "Dashboard is read-only"}, status_code=405, headers={"Cache-Control": "no-store"})
        try:
            response = await call_next(request)
        except Exception:
            if not request.url.path.startswith("/api/dashboard/"):
                raise
            response = JSONResponse({"detail": "Dashboard data unavailable"}, status_code=503)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response

    def rows(entity):
        return backend.state.store.list(entity, limit=LIMIT + 1)

    @app.get("/api/dashboard/snapshot", response_model=Snapshot, dependencies=[Depends(auth)])
    def snapshot():
        store = backend.state.store
        invalid = 0
        truncated = False

        def collect(entity, convert):
            nonlocal invalid, truncated
            records = rows(entity)
            truncated |= len(records) > LIMIT
            result = []
            for row in records[:LIMIT]:
                try:
                    result.append(convert(row))
                except (ValueError, TypeError, KeyError, AttributeError):
                    invalid += 1
            return result

        def basic(model, row, kind):
            r = _model(model, row)
            if kind == "repo":
                return Record(id=r.id, title=_text(r.full_name))
            if kind == "event":
                return Record(id=r.id, title=_text(r.title), repository_id=_id(r.repository_id),
                              created_at=r.created_at.isoformat() if row.get("created_at") is not None else None)
            return Record(id=r.id, title=_text(r.description), repository_id=_id(r.repository_id), file_path=_text(r.file_path))

        return Snapshot(observed_at=utcnow().isoformat(),
                        repositories=collect("repositories", lambda r: basic(Repository, r, "repo")),
                        events=collect("upstream_events", lambda r: basic(UpstreamEvent, r, "event")),
                        candidates=collect("workaround_candidates", lambda r: basic(WorkaroundCandidate, r, "candidate")),
                        investigations=collect("causal_hypotheses", lambda r: _investigation(r, store)),
                        decisions=collect("decisions", _decision), proposals=collect("pr_results", _proposal),
                        health=_health(backend), truncated=truncated, invalid_records=invalid)

    @app.get("/api/dashboard/investigations/{investigation_id:path}", response_model=Detail, dependencies=[Depends(auth)])
    def detail(investigation_id: str = Path(pattern=ID_PATTERN)):
        store = backend.state.store
        row = store.get("causal_hypotheses", investigation_id)
        if row is None:
            raise HTTPException(404, "Investigation record not found")
        try:
            investigation = _investigation(row, store)
            if investigation.id != investigation_id:
                raise ValueError("identity mismatch")
        except (ValueError, TypeError, KeyError, AttributeError):
            raise HTTPException(422, "Stored investigation is invalid") from None
        warnings = ["Workflow state and stage timestamps are not persisted by the current Store contract.",
                    "Stored evidence integrity is not live proof authorization. Execution receipts are process-local and are not exposed."]
        decision_rows = rows("decisions")
        if len(decision_rows) > LIMIT:
            warnings.append("Decision listing capped at 200; related records may be omitted.")
        decisions = []
        for r in decision_rows[:LIMIT]:
            if not isinstance(r, dict) or r.get("hypothesis_id") != investigation_id:
                continue
            try:
                decisions.append(_decision(r))
            except (ValueError, TypeError):
                warnings.append("A related decision is invalid and was omitted.")
        evidence, runs, regressions, missing = [], [], [], []
        refs = list(dict.fromkeys(e for d in decisions for e in d.evidence_ids))
        if len(refs) > LIMIT:
            warnings.append("Evidence references capped at 200; proof is incomplete in this view.")
        for ref in refs[:LIMIT]:
            raw = store.get("evidence", ref)
            if raw is None:
                missing.append(ref)
                continue
            try:
                item = _model(EvidenceItem, raw)
                valid = item.id == ref and validate_item(item).valid
                evidence.append(Evidence(id=ref, evidence_type=item.evidence_type.value,
                                         source=_text(item.source), claim=_text(item.claim), hash=item.hash,
                                         integrity="VALID" if valid else "INVALID", artifact_ref=_text(item.artifact_ref) if item.artifact_ref else None,
                                         experiment_id=_id(item.experiment_id),
                                         timestamp=item.timestamp.isoformat() if raw.get("timestamp") is not None else None))
                if not valid or not item.experiment_id:
                    continue
                entity = "experiment_runs" if item.evidence_type.value == "EXPERIMENT_RESULT" else "regression_results"
                run_row = store.get(entity, item.experiment_id)
                if run_row is None:
                    warnings.append("A referenced execution record is unavailable.")
                    continue
                if entity == "experiment_runs":
                    run = _model(ExperimentRun, run_row)
                    if run.id != item.experiment_id or run_payload(run) != item.payload:
                        raise ValueError("execution evidence mismatch")
                    digest = run.test_report.get("artifact_hash")
                    runs.append(Run(id=run.id, cell=run.cell.value, status=run.status.value, git_sha=run.git_sha,
                                    artifact_hash=digest if isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest) else None,
                                    duration_s=run.duration_s, exit_code=run.exit_code))
                else:
                    reg = _model(RegressionResult, run_row)
                    if reg.id != item.experiment_id or reg.model_dump(mode="json") != item.payload:
                        raise ValueError("regression evidence mismatch")
                    regressions.append(Regression(id=reg.id, status=reg.status.value, passed=reg.passed, failed=reg.failed,
                                                   git_sha=reg.git_sha, artifact_hash=reg.artifact_hash))
            except (ValueError, TypeError, KeyError, AttributeError):
                warnings.append("Invalid or mismatched evidence/execution record omitted; no successful proof is implied.")
                if not any(e.id == ref for e in evidence):
                    evidence.append(Evidence(id=ref, evidence_type="UNKNOWN", source="Unavailable", claim="Stored evidence is invalid", integrity="INVALID"))
        proposals = []
        proposal_rows = rows("pr_results")
        if len(proposal_rows) > LIMIT:
            warnings.append("Proposal listing capped at 200.")
        for p in proposal_rows[:LIMIT]:
            if isinstance(p, dict) and p.get("decision_id") in {d.id for d in decisions}:
                try:
                    proposals.append(_proposal(p))
                except (ValueError, TypeError):
                    warnings.append("Invalid proposal omitted.")
        observation = None
        recorded = store.get("workflow_observations", investigation_id)
        if recorded is not None:
            try:
                obs = WorkflowObservation.model_validate(recorded)
                if obs.id != investigation_id or obs.hypothesis_id != investigation_id:
                    raise ValueError("observation identity mismatch")
                observation = {
                    "scenario": obs.scenario, "execution": obs.execution,
                    "provenance": obs.provenance, "reasoning": obs.reasoning,
                    "completed_stages": [_text(s) for s in obs.completed_stages],
                    "state": obs.workflow.state.value if obs.workflow else "UNAVAILABLE",
                    "transitions": [{"state": t.to_state.value, "at": t.at.isoformat()}
                                    for t in obs.workflow.history] if obs.workflow else [],
                    "advisory": {"summary": _text(obs.advisory.summary),
                                 "suspected_cause": _text(obs.advisory.suspected_cause),
                                 "uncertainties": [_text(u) for u in obs.advisory.uncertainties],
                                 "verified": False} if obs.advisory else None,
                }
                warnings[0] = "Recorded workflow observations are historical; no current authorization is implied."
            except (ValueError, TypeError, AttributeError):
                warnings.append("Invalid workflow observation omitted.")
        return Detail(investigation=investigation, decisions=decisions, evidence=evidence, runs=runs,
                      regressions=regressions, proposals=proposals, missing_evidence_ids=missing,
                      warnings=warnings, observation=observation)

    @app.get("/api/dashboard/readiness/{owner}/{repo}", response_model=ReadinessAssessment, dependencies=[Depends(auth)])
    def readiness(owner: str = Path(pattern=r"^[A-Za-z0-9_.-]{1,100}$"), repo: str = Path(pattern=r"^[A-Za-z0-9_.-]{1,100}$")):
        full_name = f"{owner}/{repo}"
        accessible = False
        default_branch = None

        gh_token = os.environ.get("GITHUB_TOKEN")
        gh_status = "UNVERIFIED"
        gh_expl = "Live GitHub token not configured in environment; accessibility cannot be verified without credentials."

        if gh_token:
            try:
                from github.client import ReadOnlyGitHubClient
                client = ReadOnlyGitHubClient(token=gh_token, timeout_s=5.0)
                repo_obj = client.get_repository(full_name)
                accessible = True
                default_branch = repo_obj.default_branch
                gh_status = "PASS"
                gh_expl = f"Repository accessible on GitHub (default branch: {default_branch})."
            except Exception:
                gh_status = "MISSING"
                gh_expl = "Repository inaccessible, private, or not found on GitHub."

        try:
            from sandbox.docker import docker_available
            has_docker = docker_available()
        except Exception:
            has_docker = False

        docker_status = "PASS" if has_docker else "MISSING"
        docker_expl = ("Docker daemon and python:3.11-slim execution image available."
                       if has_docker else
                       "Docker daemon or required python:3.11-slim container image not detected.")

        checks = [
            ReadinessCheck(
                name="Repository accessible",
                status=gh_status,
                explanation=gh_expl,
            ),
            ReadinessCheck(
                name="Dependency manifest detected",
                status="UNVERIFIED",
                explanation="Manifest detection requires local checkout or file inspection; unverified via read-only metadata.",
            ),
            ReadinessCheck(
                name="Supported package pin detected",
                status="UNVERIFIED",
                explanation="Single-package pin requirement (requirements.txt) requires repository file analysis.",
            ),
            ReadinessCheck(
                name="Upstream issue reference available",
                status="UNVERIFIED",
                explanation="Upstream issue reference must be supplied in candidate workaround metadata.",
            ),
            ReadinessCheck(
                name="Candidate fixing commit available",
                status="UNVERIFIED",
                explanation="Candidate fix SHA must be linked to upstream issue before counterfactual generation.",
            ),
            ReadinessCheck(
                name="Release tag available",
                status="UNVERIFIED",
                explanation="Release tag must match fixing commit ancestry in upstream provenance.",
            ),
            ReadinessCheck(
                name="Historical source artifacts available",
                status="UNVERIFIED",
                explanation="Reconstructed source trees must be available in local fixture store or git object store.",
            ),
            ReadinessCheck(
                name="Docker execution available",
                status=docker_status,
                explanation=docker_expl,
            ),
            ReadinessCheck(
                name="Provenance verification available",
                status="UNVERIFIED",
                explanation="Live GitHub provenance is unverified; only controlled fixture mirrors currently prove authenticity.",
            ),
        ]

        return ReadinessAssessment(
            repository=full_name,
            owner=owner,
            name=repo,
            default_branch=default_branch,
            accessible=accessible,
            checks=checks,
            can_connect=True,
            proof_ready=False,
            summary="Repository format is valid for workspace connection. Live proof readiness remains incomplete: authenticated upstream provenance, manifest verification, and source artifacts must be established before autonomous proof execution.",
        )

    app.mount("/", backend)
    return app
