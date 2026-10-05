# UNBODGE — Phase 1: Foundation & Deterministic Core

## Mission
Build the trustworthy deterministic foundation. Do not build the AI agent yet.

## Scope
Build `packages/domain`, `packages/evidence`, `packages/experiments`, `packages/sandbox`, `packages/policy`, plus foundational tests/configuration.

Implement:
- Pydantic domain contracts
- explicit workflow states and transitions
- immutable evidence records and deterministic validation
- sandbox interface
- experiment/counterfactual contracts
- `PROPOSE_ONLY` policy gate
- synthetic dependency scenario
- first green end-to-end proof

## Required Models
`Repository`, `UpstreamEvent`, `UpstreamIssue`, `FixCommit`, `Release`, `WorkaroundCandidate`, `CausalHypothesis`, `ReproductionPlan`, `ExperimentSpec`, `ExperimentRun`, `EvidenceItem`, `EvidenceGraph`, `RegressionResult`, `RemovalDecision`, `PullRequestResult`, `HumanReview`.

## Workflow
`DISCOVERED → INVESTIGATING → CANDIDATE_FOUND → CAUSAL_ANALYSIS → REPRODUCTION_PLANNED → HISTORICAL_EXECUTION → COUNTERFACTUAL_EXECUTION → EVIDENCE_VALIDATION → REGRESSION_TESTING → POLICY_DECISION → ABSTAINED / APPROVED_FOR_PR → PR_CREATED`

Invalid transitions must be rejected.

## Counterfactual Contract
A = OLD + workaround
B = OLD + no workaround
C = NEW + workaround
D = NEW + no workaround

Canonical success:
- A PASS
- B FAIL
- C PASS
- D PASS

## Sandbox
Define `create`, `execute`, `collect`, `destroy`. First implementation is local. Enforce timeout, CPU/memory limits, filesystem boundary, environment sanitization, network policy, command validation, artifact limits, and cleanup.

Never execute unrestricted model-generated commands on the host.

## Policy
Policies: `PROPOSE_ONLY`, `STRICT_AUTO_MERGE`, `HUMAN_APPROVAL_REQUIRED`. MVP is `PROPOSE_ONLY`. Model text cannot override policy.

## Mandatory First Green Test
OLD + workaround → PASS
OLD + no workaround → FAIL
NEW + no workaround → PASS
regression tests → PASS
evidence → VALID
decision → PROPOSE_REMOVAL

## Explicitly Out of Scope
UI, chatbot, Nemotron/Nebius, Tavily, LangSmith, Toloka, Tendem, Temporal, real external investigation, Kubernetes, Kafka, vector DBs, multi-agent swarm, auto-merge, multi-language support.

## OpenCode/ECC Rule
Use ECC for planning, TDD, implementation, review, security review, verification, and refactoring. Every task must identify its contract, deterministic test, future consumer, and infrastructure cost.

## Exit Criteria
All foundation tests are green; synthetic proof passes; evidence validates; policy returns `PROPOSE_REMOVAL`; no external AI/service is required.

## Anti-Drift Rule
If a task does not directly strengthen the deterministic foundation or its tests, defer it.
