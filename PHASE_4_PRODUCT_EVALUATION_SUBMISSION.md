# UNBODGE — Phase 4: Product, Cloud, Evaluation & Submission

## Mission
Turn the proven proof loop into a secure, evaluated, deployable, judge-facing product.

## Scope
Build Nebius sandbox execution, production API, frontend, benchmark suite, baselines, security tests, performance profiling, observability, final demo, and submission artifacts.

## Nebius Sandbox
Implement `NebiusSandbox` behind the same interface as `LocalDockerSandbox`. Preserve timeout, resource, filesystem, network, command, artifact, and cleanup controls.

## FastAPI
Initial endpoints:
POST /webhooks/github
POST /repositories
GET /repositories
GET /events
GET /candidates
GET /experiments/{id}
GET /evidence/{id}
GET /decisions/{id}
POST /experiments/{id}/rerun
POST /decisions/{id}/approve
GET /health

The API must not bypass the policy gate.

## Frontend
Build only:
1. Dashboard
2. Investigation / Causal Graph
3. Proof View
4. Evidence Ledger / PR View

Do not start with a chatbot.

## Evaluation
Run 10 cases first, then 30, target 30–50. Track:
`safe_removal_precision`, `abstention_accuracy`, `causal_link_accuracy`, `historical_reconstruction_success`, `counterfactual_success`, `regression_pass_rate`, `unsafe_removal_rate`, `human_agreement`, `latency`, `cost`, `time_saved`.

## Baselines
Compare:
1. LLM-only recommendation
2. LLM + deterministic search
3. UNBODGE without counterfactual proof
4. full UNBODGE

## Security
Test wrong issue/version, ambiguous workaround, missing release, broken reproduction, flaky tests, sandbox timeout, contradictory evidence, hallucinated commit, prompt injection in repository content, malicious package execution, command injection, secret exposure, and resource exhaustion.

Repository content is untrusted. Insufficient evidence => `ABSTAIN`.

## Performance
Measure API/workflow/model/search/sandbox/experiment/database/PR latency and token cost before optimizing. If a genuine CPU hot path appears, introduce Rust behind a stable interface rather than rewriting the system.

## Deployment
Target:
FastAPI + Temporal worker + PostgreSQL + Redis + frontend + sandbox service, using Docker/Nebius and GitHub Actions CI.

## Final Demo
Primary story:
upstream bug → upstream fix → release → workaround discovery → causal graph → historical reconstruction → old/no-workaround FAIL → new/no-workaround PASS → regression PASS → evidence ledger → GitHub PR.

Then show:
ambiguous/insufficient evidence → ABSTAIN → no PR.

## MVP Boundary
Python + PyPI + GitHub + one repository + one dependency + one real workaround + one upstream fix + one counterfactual proof + one PR.

Do not prematurely add multi-language support, Kubernetes, Kafka, vector databases, multi-agent swarms, or auto-merge.

## Submission
Public repository, OSS license, hosted/testable build, Nebius/NVIDIA explanation, benchmark results, under-3-minute demo, final Devpost submission.

## Anti-Drift Rule
The proof loop always wins:
event → investigation → workaround → causal hypothesis → historical reconstruction → counterfactual execution → evidence validation → regression tests → policy decision → PR OR ABSTAIN.
