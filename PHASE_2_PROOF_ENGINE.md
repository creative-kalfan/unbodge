# UNBODGE — Phase 2: Proof Engine & Historical Reconstruction

## Mission
Turn the deterministic foundation into a complete local proof loop capable of reconstructing software history and executing controlled counterfactual experiments.

## Scope
Build GitHub/PyPI adapters, deterministic repository analysis, workaround detectors, historical dependency environments, counterfactual execution, regression execution, evidence graph integration, local PR generation, and durable workflow interfaces where required.

## GitHub
Support repository/issue/comments/PR/files/commit/release/tag reads plus branch creation, commits, and PR creation. Use GitHub API for metadata and git for history.

## PyPI
Support package metadata, versions, release metadata, and latest release. Historical dependency states must be reproducible.

## Deterministic Analysis
Use Python AST and Tree-sitter. Initial detectors:
- VersionCheckDetector
- MonkeyPatchDetector
- CompatibilityBranchDetector
- ExceptionWorkaroundDetector
- UpstreamReferenceDetector

Signals include TODO/FIXME, workaround, temporary, compat, upstream references, version checks, retries, shims, and dependency-specific branches. Detectors produce evidence/signals, not truth.

## Counterfactual Engine
Execute isolated OLD/NEW configurations and store raw outputs, environment, Git SHA, dependency lock/state, command, exit code, and artifacts.

Required proof:
- OLD + workaround PASS
- OLD + no workaround FAIL
- NEW + no workaround PASS

## Historical Reconstruction
Establish:
upstream problem → fixing commit → release containing fix → downstream symptom → workaround introduction.

Every link requires evidence. Causal relationships remain hypotheses until supported by execution/evidence.

## Regression & Safety
Before removal proposal: reproduce historical failure, establish fixed behavior, remove workaround, run regression suite, validate evidence, apply policy. Insufficient evidence => `ABSTAIN`.

## PR Generator
Generate branch, commit, PR title/body, evidence references, and test results. PR body must be rendered from structured evidence.

## Workflow
Logical stages:
`ingest_event → collect_upstream_evidence → identify_release → scan_repository → analyze_candidates → build_causal_hypothesis → plan_reproduction → prepare_environment → run_experiments → collect_evidence → run_regression_tests → validate_policy → create_pr`

Make activities idempotent where practical.

## Exit Criteria
Adapters work against controlled cases; candidate detection works; historical states are reproducible; isolated counterfactuals execute; evidence and regression testing work; unsupported removals are blocked; synthetic/local PR artifact can be produced; an ambiguous case abstains.

## Anti-Drift Rule
Do not add AI to compensate for missing deterministic tooling. Mark uncertainty and preserve the interface for later reasoning.
