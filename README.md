# UNBODGE — Evidence-Gated Autonomous Software Maintenance

> **Autonomous dependency workaround removal via historical counterfactual execution and cryptographic attestation.**  
> Built for the **Nebius × NVIDIA Global AI Hackathon** (Track: *Coding and Agentic Engineering*).

---

## 1. Project Purpose & Problem Statement

Production codebases accumulate technical debt in the form of defensive monkey-patches, compatibility shims, polyfills, and version pins introduced to circumvent upstream dependency bugs. When upstream libraries eventually fix these issues, downstream teams rarely remove the defensive code because nobody can guarantee that removing it won't introduce regressions.

Generative AI coding assistants try to solve this by guessing: they inspect code comments and predict whether a workaround "looks" obsolete. But **LLM confidence is never proof**. An assistant that hallucinates a bug fix risks introducing silent production outages.

**UNBODGE** solves this by treating maintenance as an **empirical hypothesis-testing problem**. Rather than relying on generative confidence, UNBODGE:
1. Reconstructs the exact historical conditions that necessitated the workaround.
2. Formulates a causal hypothesis using **NVIDIA Nemotron** via **Nebius Token Factory**.
3. Reconstructs historical environments across old and new dependency versions.
4. Executes a rigorous **4-cell counterfactual matrix (A, B, C, D)** inside an isolated sandbox.
5. Captures cryptographic execution receipts in a local attestation ledger.
6. Evaluates a deterministic policy engine that authorizes pull requests **only** when empirical proof is indisputable.

---

## 2. Core Workflow: The 4-Cell Matrix

```
event → investigation → workaround → causal hypothesis (NVIDIA Nemotron via Nebius)
  → historical reconstruction → counterfactual execution (A / B / C / D)
  → execution receipts & attestation → regression testing
  → deterministic policy gate → PROPOSE_REMOVAL or ABSTAIN
```

The system verifies a strict 4-cell truth table:
* **Cell A (`OLD + workaround`):** Must **PASS** (confirms workaround worked in original broken environment).
* **Cell B (`OLD - workaround`):** Must **FAIL** (reproduces bug; proves workaround was necessary).
* **Cell C (`NEW + workaround`):** Must **PASS** (confirms new dependency doesn't break existing workaround).
* **Cell D (`NEW - workaround`):** Must **PASS** (proves workaround is safe to remove).

If **any** cell fails to match this signature, or if the independent regression suite fails on the removal tree, UNBODGE **abstains**. It will never guess.

---

## 3. Repository Connection & Proof Readiness Assessment

UNBODGE provides a dedicated repository onboarding wizard and truthful proof-readiness assessment:
* **Step 1 — Repository URL**: The operator inputs a GitHub URL (e.g. `https://github.com/psf/requests`). Unsupported hosts and malformed URLs are rejected to prevent SSRF.
* **Step 2 — Safe Inspection**: Read-only inspection retrieves metadata without cloning or executing untrusted code.
* **Step 3 — 9-Point Proof Readiness Evaluation**:
  1. *Repository accessible* (`PASS` / `MISSING` / `UNVERIFIED`)
  2. *Dependency manifest detected* (`UNVERIFIED` — requires local checkout)
  3. *Supported package pin detected* (`UNVERIFIED` — requires single-package `requirements.txt` pin)
  4. *Upstream issue reference available* (`UNVERIFIED` — requires tracker reference)
  5. *Candidate fixing commit available* (`UNVERIFIED` — requires linked fix SHA)
  6. *Release tag available* (`UNVERIFIED` — requires tag matching fix ancestry)
  7. *Historical source artifacts available* (`UNVERIFIED` — requires fixture tree)
  8. *Docker execution available* (`PASS` / `MISSING` — detects daemon & `python:3.11-slim`)
  9. *Provenance verification available* (`UNVERIFIED` — live GitHub history unverified)
* **Step 4 — Workspace Registration**: The repository is safely persisted via `POST /repositories`. Live proof readiness remains incomplete until authenticated provenance is provided, making the security boundary transparent.

---

## 4. Architecture & Safety Model

```mermaid
flowchart LR
    GH[GitHub / Git History] --> H[history: GitProvenance]
    PYPI[PyPI Releases] --> H
    H --> AN[analysis & detectors]
    AN --> EX[experiments: 4-Cell Engine]
    SB[(sandbox: Docker / Local)] --> EX
    EX --> AT[(attestation: ExecutionLedger)]
    AT --> EV[evidence validation]
    RE[NVIDIA Nemotron via Nebius] -.->|advisory only: verified=false| EV
    EV --> PO[deterministic policy gate]
    PO --> PR[LocalPrGenerator: atomic ref commit | ABSTAIN]
    API[FastAPI Read-Only API] --> DB[(Memory / Postgres / Redis)]
    DASH[React / Vite Dashboard] --> API
```

### Safety Invariants
1. **Advisory Reasoning:** Models propose hypotheses; deterministic evidence disposes. Model claims can **never** authorize code removal (`verified = false`).
2. **Deterministic Provenance:** Upstream issue identity, fix commit SHA, release tag ancestry, and source files are verified through Git object hashes.
3. **Execution Attestation:** Process-local `ExecutionLedger` cryptographically binds `(run_id, git_sha, files_hash, argv, env, stdout, stderr, exit_code)`. Whitespace tampering or falsified exit codes are rejected.
4. **Exact Removal Binding:** The candidate removal tree used in counterfactual Cell D must match the regression tree and the proposed PR tree byte-for-byte.
5. **No Auto-Merge (`PROPOSE_ONLY`):** The system has zero automated merge capability. PR proposals are committed to private Git refs for human review.
6. **Credential Privacy:** Operator Bearer tokens are held strictly in React memory; no credentials ever touch `localStorage`, `sessionStorage`, or URLs. All logs and API payloads undergo automated secret redaction.

---

## 4. Technology Integrations

| Technology | Role | Status | Integration Details |
| :--- | :--- | :--- | :--- |
| **NVIDIA Nemotron** (`nvidia/Nemotron-3-Ultra-550b-a55b`) | Advisory Causal Reasoning | **Operational** | Synthesizes upstream bug causes and identifies uncertainties in `packages/reasoning/nebius.py`. |
| **Nebius Token Factory** | Serverless Inference Platform | **Operational** | OpenAI-compatible endpoint (`https://api.tokenfactory.nebius.com/v1`) using Python stdlib `urllib`. |
| **Docker Sandbox** | Isolated Container Execution | **Operational** | Runs containerized test cells with resource caps and `--network none`. |
| **GitHub Client** | Repository Metadata Client | **Operational (Read-Only)** | `ReadOnlyGitHubClient` provides read-only repository inspection. Live authenticated chains are labeled `UNVERIFIED` in demos. |
| **Tavily Search** | Research Evidence Collection | **Operational** | Search provider in `packages/research/tavily.py` with caching and offline fallback. |
| **LangSmith Tracing** | Observability & Telemetry | **Operational** | Non-blocking execution event tracing in `packages/tracing/langsmith.py`. |
| **React Dashboard** | Frontend User Interface | **Operational** | React 19 + TypeScript + Vite + Tailwind CSS v4 in `apps/dashboard`. |

---

## 5. Getting Started & Setup

### Prerequisites
* Python 3.11+ (Python 3.14 verified for core engines).
* Node.js 18+ & npm.
* Docker (required for real container execution).

### Backend Setup
```bash
# Clone the repository
git clone https://github.com/creative-kalfan/unbodge.git
cd unbodge

# Install Python dependencies
pip install -e ".[dev]"

# Optional: configure environment variables
cp .env.example .env
# Edit .env with your NEBIUS_API_KEY if testing live inference
```

### Frontend Setup
```bash
cd apps/dashboard
npm install
npm run build
```

---

## 6. Running the Demo & Tests

### 1. Dual Scenario Dashboard Demonstration
Runs both a positive proof scenario (`PROPOSE_REMOVAL`) and a negative scenario (`ABSTAIN`) and serves the read-only dashboard:

```bash
# Run demonstration and serve dashboard API on port 8000:
python scripts/dashboard_demo.py --serve --port 8000

# In a separate terminal, launch the dashboard UI:
cd apps/dashboard
npm run dev
# Open http://localhost:5173
```

To include live NVIDIA Nemotron inference via Nebius Token Factory (requires `NEBIUS_API_KEY` in `.env`):
```bash
python scripts/dashboard_demo.py --serve --live-reasoning
```

### 2. Backend Test Suite
```bash
# Full test suite (382 tests, offline-safe, zero paid credits consumed):
python -m pytest

# Run proof-authorization tests only:
python -m pytest tests/test_proof_authorization.py -v

# Run container & real-case tests:
python -m pytest tests/test_benchmark.py tests/test_phase2_proof.py tests/test_realcase.py
```

### 3. Frontend Tests & Build
```bash
cd apps/dashboard
npm test -- --run   # 15 Vitest unit & component tests
npm run build       # TypeScript typecheck + production Vite bundle
```

---

## 7. Known Limitations

1. **Artifact Tree Types:** Proof artifacts currently support regular non-executable UTF-8 text files. Symlinks, binary files, or hidden files fail closed.
2. **Dependency Manifests:** Counterfactual isolation currently supports single package pins in `requirements.txt`. Complex compound manifest upgrades require separate verified handling.
3. **Execution Receipts:** Attestation receipts are process-local capabilities in memory. Cross-process persistence of executable authorization is not implemented; proof must be re-run freshly.
4. **Live GitHub Transport:** GitHub API integration is read-only. For end-to-end demonstrations without external rate limits, controlled synthetic Git fixtures are utilized and explicitly labeled `CONTROLLED_FIXTURE`.

---

## 8. Hackathon Submission Package

* [docs/FINAL_ARCHITECTURE.md](file:///c:/Users/pathan%20Kalfan/unbodge/docs/FINAL_ARCHITECTURE.md): Comprehensive system specification.
* [docs/HACKATHON_SUBMISSION.md](file:///c:/Users/pathan%20Kalfan/unbodge/docs/HACKATHON_SUBMISSION.md): Submission overview for Devpost.
* [docs/NEBIUS_NVIDIA_FEEDBACK.md](file:///c:/Users/pathan%20Kalfan/unbodge/docs/NEBIUS_NVIDIA_FEEDBACK.md): Candid platform feedback on Token Factory and Nemotron.
* [docs/HACKATHON_DEVELOPMENT_DISCLOSURE.md](file:///c:/Users/pathan%20Kalfan/unbodge/docs/HACKATHON_DEVELOPMENT_DISCLOSURE.md): Baseline attribution and new work disclosure.
* [docs/DEMO_VIDEO_SCRIPT.md](file:///c:/Users/pathan%20Kalfan/unbodge/docs/DEMO_VIDEO_SCRIPT.md): 2-minute 45-second timed demo video script.
* [docs/SUBMISSION_CHECKLIST.md](file:///c:/Users/pathan%20Kalfan/unbodge/docs/SUBMISSION_CHECKLIST.md): Devpost submission checklist.

---

## 9. License

This project is licensed under the [MIT License](file:///c:/Users/pathan%20Kalfan/unbodge/LICENSE).
