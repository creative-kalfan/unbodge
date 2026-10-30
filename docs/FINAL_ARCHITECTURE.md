# UNBODGE — Final Release Candidate Architecture

## System Overview

UNBODGE is an evidence-gated autonomous software maintenance agent. Unlike generative coding assistants that infer code obsolescence from LLM confidence or heuristic guessing, UNBODGE reconstructs the historical context that necessitated a dependency workaround and empirically tests whether upstream changes have rendered the workaround obsolete.

**Foundational Invariant:** Model confidence is advisory; deterministic empirical evidence authorizes action. The system operates strictly in `PROPOSE_ONLY` mode. No automatic merge capability exists.

```
+-------------------------------------------------------------------------------+
|                               UNBODGE WORKFLOW                                |
+-------------------------------------------------------------------------------+
|  1. Ingest Event       -> Ingest upstream issue / release notification        |
|  2. Reasoning          -> Optional NVIDIA Nemotron via Nebius Token Factory   |
|                           (Advisory only; status: ADVISORY_RECORDED; unverified)|
|  3. Upstream Evidence  -> GitProvenance: repo, issue, fix commit SHA          |
|  4. Identify Release   -> GitProvenance: release tag, ancestry, fix SHA      |
|  5. Form Hypothesis    -> Pinpoint workaround code, dependency, target claim  |
|  6. Plan Experiments   -> 4-cell counterfactual execution plan (A, B, C, D)   |
|  7. Run Experiments    -> Sandbox execution with ExecutionLedger receipts    |
|  8. Regression Suite   -> NEW revision without workaround execution           |
|  9. Validate Policy    -> Deterministic policy gate + RemovalProof validation|
| 10. Propose PR         -> Atomic git ref commit with RemovalProof validation  |
+-------------------------------------------------------------------------------+
```

---

## Component Architecture

### 1. Frontend Dashboard (`apps/dashboard`)
* **Technology Stack**: React 19, TypeScript, Vite, Tailwind CSS v4, Lucide React icons.
* **Architecture**: Standalone Single Page Application (SPA) consuming read-only backend API endpoints.
* **Security & Auth**: Operator Bearer tokens are stored exclusively in component memory (React state) and passed via the `Authorization: Bearer <token>` header. Tokens are never persisted to `localStorage`, `sessionStorage`, cookies, or browser URLs.
* **Capabilities**:
  * **Overview / Metrics**: Displays counts of total investigations, obsolete candidates, abstentions, active runs, and integration health.
  * **Investigations View**: Searchable list with badges distinguishing `OBSOLETE` vs `ABSTAIN` and synthetic vs live provenance.
  * **Investigation Detail**: Deep dive into workflow timeline, causal hypothesis, counterfactual 4-cell matrix (A, B, C, D), execution receipts, and policy rationale.
  * **Proof Explorer**: Visual breakdown of the 6 core proof pillars (Provenance, Matrix, Regression, Ledger, Artifact, Policy).
  * **Integration Health**: Real-time status of Nebius/Nemotron, GitHub client, Docker Sandbox, LangSmith tracer, and persistence stores. Secrets and sensitive tokens are strictly masked.

### 2. Dashboard API & Serialization (`packages/api/dashboard.py`, `packages/api/dashboard_server.py`)
* **Framework**: FastAPI (ASGI).
* **Endpoints**:
  * `GET /api/dashboard/snapshot`: Aggregate health, counts, and investigation summaries.
  * `GET /api/dashboard/readiness/{owner}/{repo}`: 9-point proof readiness assessment and repository preflight validation.
  * `GET /api/dashboard/investigations/{id}`: Detailed investigation dossier including observation, runs, regressions, and proposals.
* **Security Guardrails**:
  * Bearer token authentication via `UNBODGE_API_TOKEN` (constant-time comparison).
  * Read-only restriction enforced by middleware in demo mode (`405 Method Not Allowed` on mutations).
  * Secret scrubbing on all outgoing JSON payloads (regex scrubbing for tokens, keys, passwords).
  * Investigation isolation: 404 on mismatched or foreign identifier queries.

### 3. Advisory Reasoning Provider (`packages/reasoning/nebius.py`)
* **Engine**: Nebius Token Factory serverless endpoint (`https://api.tokenfactory.nebius.com/v1`).
* **Model**: NVIDIA Nemotron (`nvidia/Nemotron-3-Ultra-550b-a55b` or `Nemotron-3-Ultra-550b-a55b-serverless`).
* **Protocol**: OpenAI-compatible chat completions over standard HTTPS using Python standard library `urllib.request`. Zero external heavy SDK dependencies.
* **Structured Output**: Strictly parsed into Pydantic models (`UpstreamAnalysis`, `WorkaroundAnalysis`, `ReproductionProposal`, `EvidenceSynthesis`).
* **Trust Boundary**:
  * Model responses are explicitly marked `verified = False`.
  * Model failures (`ReasoningAuthError`, `ReasoningTimeoutError`, `ReasoningUnavailableError`, `ReasoningMalformedError`) fail safe without halting workflow execution.
  * Model claims can **never** satisfy proof requirements or alter deterministic policy evaluation.

### 4. Deterministic Provenance Engine (`packages/history/provenance.py`)
* **Class**: `GitProvenance`.
* **Verification Checks**:
  1. Verifies repository identity and canonical issue identity.
  2. Independently checks fixing-commit SHA and presence in upstream git object database.
  3. Validates release tag ancestry to ensure fix commit is an ancestor of the release.
  4. Binds workaround introduction patch and dependency version pin.
  5. Computes SHA-256 hashes of all bound source artifacts.
  6. Restricts change validation strictly to bound dependency files and the single requirements pin.

### 5. Counterfactual Execution & Attestation Ledger (`packages/experiments/attestation.py`, `packages/experiments/real.py`)
* **Counterfactual Matrix**:
  * **Cell A**: OLD dependency + workaround PRESENT -> Expected: **PASS**
  * **Cell B**: OLD dependency + workaround ABSENT  -> Expected: **FAIL** (proves workaround was necessary)
  * **Cell C**: NEW dependency + workaround PRESENT -> Expected: **PASS**
  * **Cell D**: NEW dependency + workaround ABSENT  -> Expected: **PASS** (proves workaround is obsolete)
* **Execution Ledger (`ExecutionLedger`)**:
  * Process-local ledger that mints immutable execution receipts for every sandbox run.
  * Receipts cryptographically bind `(run_id, git_sha, files_hash, argv, env, stdout, stderr, exit_code, duration_s)`.
  * Verifies exact artifact hash, command arguments, and container execution outcomes.
  * Rejects whitespace tampering, falsified exit codes, and caller-supplied unverified receipts.

### 6. Deterministic Policy Gate (`packages/policy/authorization.py`, `packages/policy/engine.py`)
* **Requirements for `PROPOSE_REMOVAL`**:
  1. Complete counterfactual matrix matches canonical pattern `A: PASS, B: FAIL, C: PASS, D: PASS`.
  2. Independent regression suite on NEW revision without workaround passes (`status == PASS, failed == 0, passed > 0`).
  3. Execution receipts for all cells and regression exist in the local `ExecutionLedger` and match hashes.
  4. Regression artifact matches counterfactual Cell D artifact and proposed PR tree.
  5. Valid provenance chain confirmed from upstream issue, commit, release, and downstream history.
  6. All evidence items pass cryptographic validation.
* **Failure Behavior**: Any failure or missing evidence forces immediate `ABSTAIN` with an explicit terminal failure reason. No proposal is generated.

### 7. Proposal Generator (`packages/pr/generator.py`)
* **Class**: `LocalPrGenerator`.
* **Enforcement**:
  * Requires a verified `RemovalProof` object.
  * Re-verifies provenance, execution receipts, artifact hashes, and policy decision before any Git mutation.
  * Uses Git low-level plumbing (`read-tree`, `write-tree`, `commit-tree`, `update-ref`) to create the proposal commit via a private index.
  * The working directory, index, and HEAD branch are never modified.
  * Replay attempts on an existing proposal ref are strictly rejected.

### 8. Persistence & Storage (`packages/persistence/`)
* **Implementations**:
  * `MemoryStore`: Fast in-memory storage used for testing and isolated demonstrations.
  * `PostgresStore`: PostgreSQL persistence with connection retry and schema validation (`schema.sql`).
  * `RedisCache`: Redis caching backend with fallback.
* **Durable Storage Invariant**: Execution receipts are process-local capabilities. Stored investigation snapshots are marked with observation status and cannot authorize fresh git modifications across process restarts without re-attestation.

---

## Integration Status Summary

| Integration | Implementation | Test Status | Operational Role |
| :--- | :--- | :--- | :--- |
| **NVIDIA Nemotron** | `packages/reasoning/nebius.py` | Verified (Mock + Unit) | Advisory causal hypothesis generation |
| **Nebius Token Factory** | `packages/reasoning/nebius.py` | Verified (Live HTTP 200) | Serverless LLM inference backend |
| **Execution Ledger** | `packages/experiments/attestation.py` | Verified (Unit + Integration) | Process-local execution receipt attestation |
| **Docker Sandbox** | `packages/sandbox/docker.py` | Verified (Container tests) | Isolated container execution environment |
| **GitHub Client** | `packages/github/client.py` | Verified (Read-only mock) | Read-only metadata retrieval |
| **Tavily Search** | `packages/research/tavily.py` | Verified (Unit tests) | Advisory search evidence collection |
| **LangSmith Tracing** | `packages/tracing/langsmith.py` | Verified (Unit tests) | Non-blocking telemetry & event tracing |
| **Frontend Dashboard** | `apps/dashboard/` | Verified (Vitest + Build) | Operator visualization and proof explorer |
