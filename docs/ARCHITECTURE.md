# UNBODGE architecture (Phase 4)

## Proof loop (highest priority, never weakened)

```
GitHub event / issue
  -> ingest_event -> collect_upstream_evidence -> identify_release
  -> scan_repository (AST detectors) -> analyze_candidates
  -> build_causal_hypothesis -> plan_reproduction
  -> prepare_environment (historical states + installability)
  -> run_experiments (A/B/C/D counterfactual, isolated sandboxes)
  -> collect_evidence (immutable, hashed, validated)
  -> run_regression_tests (post-removal state)
  -> validate_policy (PROPOSE_ONLY gate)
  -> create_pr  OR  ABSTAIN (no PR)
```

## Packages

| Package | Role | Authority? |
|---|---|---|
| `domain` | contracts, enums, state machine, errors | yes (types) |
| `evidence` | records, hashing, validation, graph, scrub | yes |
| `experiments` | contracts, planner, runners (synthetic + real) | yes |
| `sandbox` | ABC, local, Docker | yes (execution) |
| `policy` | deterministic gate | yes (decision) |
| `github`, `pypi` | adapters (fixture + real-git) | data |
| `analysis` | AST detectors | signals |
| `history` | pins, locks, reconstruction | data |
| `reasoning` | mock + Nebius providers | advisory only |
| `research` | Tavily + cache + mock | inputs only |
| `tracing` | local, LangSmith, OTel spans | observability |
| `benchmark` | dataset, metrics, baselines, runner | evaluation |
| `evaluation` | judgments, review packets, stubs | evaluation |
| `persistence` | store ABC, memory, Postgres | storage |
| `cache` | cache ABC, memory, Redis | transient only |
| `cloud` | NebiusSandbox (fail-closed) | execution |
| `api` | FastAPI app, webhooks, 4 UI views | serving |
| `workflow` | stages, pipeline, Temporal mapping, CLI | orchestration |
| `pr` | local PR generation | artifact |

Temporal mapping: `workflow/temporal.py` declares the 13 stages as
versioned idempotent activities; `LocalWorkflowRunner` executes them;
`TemporalWorkflowRunner` fails closed without a server/SDK.
