# UNBODGE — Hackathon Submission

**Nebius × NVIDIA Global AI Hackathon**  
**Track:** Coding and Agentic Engineering  
**Project Name:** UNBODGE  
**Tagline:** Evidence-gated autonomous software maintenance agent that removes obsolete workarounds through historical counterfactual execution.

---

## 1. Executive Summary & Problem

Software codebases are littered with defensive workarounds, monkey patches, polyfills, and version pins introduced to circumvent upstream dependency bugs. When upstream libraries eventually patch these defects, downstream teams rarely remove the defensive shims because:
1. Nobody remembers which specific bug required the workaround.
2. The developers who authored the workaround have moved on.
3. Code review fear: removing defensive code feels risky without absolute proof that nothing will break.

Current AI coding assistants attempt to address maintenance by reading code and guessing whether a comment or pattern looks obsolete. This approach fails because **LLM confidence is not empirical proof**. An LLM hallucinating that a bug is fixed can introduce catastrophic production regressions.

## 2. The Solution: UNBODGE

UNBODGE treats software maintenance not as a generative autocomplete task, but as an empirical hypothesis-testing problem.

Instead of trusting model confidence, UNBODGE:
1. Identifies the historical upstream issue and fix commit.
2. Formulates a causal hypothesis using **NVIDIA Nemotron** via **Nebius Token Factory**.
3. Reconstructs historical environments across old and new dependency versions.
4. Executes a rigorous **4-cell counterfactual experiment matrix (A, B, C, D)** inside an isolated sandbox.
5. Captures cryptographic execution receipts in a local attestation ledger.
6. Runs a full regression suite on the candidate removal artifact.
7. Evaluates a deterministic policy gate: only when every cell behaves as required does UNBODGE author a clean pull request.

If any evidence is missing, ambiguous, or failing, UNBODGE **abstains**. It will never guess.

---

## 3. How NVIDIA and Nebius Technologies Are Used

### NVIDIA Nemotron
* **Model:** `nvidia/Nemotron-3-Ultra-550b-a55b` (and `Nemotron-3-Ultra-550b-a55b-serverless`).
* **Role in Architecture:** Advisory causal reasoning.
  * When an upstream release or issue event is ingested, Nemotron analyzes the issue title, description, and downstream code to synthesize a causal explanation of why the workaround was introduced and why it might now be obsolete.
  * Nemotron's structured output is captured in a formal domain schema (`UpstreamAnalysis`) with explicit tracking of uncertainties.
* **Safety Integration:** Nemotron's outputs are strictly tagged `verified = False`. The policy engine that authorizes pull requests operates purely on deterministic Git provenance and container execution receipts, ensuring that generative reasoning proposes while empirical proof disposes.

### Nebius Token Factory
* **Endpoint:** `https://api.tokenfactory.nebius.com/v1`
* **Role in Architecture:** High-throughput, low-latency serverless model inference.
  * Standardized OpenAI-compatible API protocol executed directly over lightweight Python standard library HTTP (`urllib.request`), eliminating bloat and dependency vulnerabilities.
  * Reliable token-based authentication and streaming structured JSON completions.
  * Enabled fast turnarounds during reasoning integration and verification.

---

## 4. Key Differentiators

| Traditional LLM Coding Agents | UNBODGE |
| :--- | :--- |
| Operates on prompt confidence | Operates on empirical counterfactual execution |
| Generates PRs based on textual resemblance | Requires cryptographic execution receipts in an attestation ledger |
| Often hallucinates that a bug fix resolved an issue | Verifies Git ancestry and exact commit objects in the upstream repo |
| May silently delete needed safety code | Strict 4-cell matrix proves necessity (B: FAIL) and obsolescence (D: PASS) |
| Autonomous merge risks breaking production | Strictly `PROPOSE_ONLY`; zero automatic merge capability |

---

## 5. System Workflow: The 4-Cell Matrix

UNBODGE executes four distinct cells in an isolated container sandbox:

* **Cell A (OLD Dep + Workaround PRESENT):** Must **PASS**. Confirms the workaround functioned in the original broken environment.
* **Cell B (OLD Dep + Workaround ABSENT):** Must **FAIL**. Confirms the workaround was genuinely necessary and reproduced the upstream bug.
* **Cell C (NEW Dep + Workaround PRESENT):** Must **PASS**. Confirms the updated dependency doesn't crash existing code.
* **Cell D (NEW Dep + Workaround ABSENT):** Must **PASS**. Confirms the workaround can safely be discarded.

Only if `A=PASS`, `B=FAIL`, `C=PASS`, `D=PASS`, plus independent regression `PASS` with zero failures, does UNBODGE's deterministic policy engine approve proposal generation.

---

## 6. Target Audience

* **Enterprise Maintenance Teams:** Maintaining millions of lines of legacy code with accumulated technical debt.
* **Open Source Maintainers:** Managing libraries with workarounds for old versions of dependencies like `packaging`, `cryptography`, or `requests`.
* **Platform & SRE Teams:** Ensuring dependency upgrades are accompanied by clean removal of obsolete monkey-patches.

---

## 7. Honest Limitations & Boundaries

To ensure complete scientific and engineering integrity, we disclose all known architectural boundaries:
1. **Scope of Proof Artifacts:** UNBODGE currently validates regular non-executable UTF-8 text trees. Binary files, symlinks, and unsupported modes fail closed.
2. **Dependency Manifests:** Counterfactual isolation currently supports single package pins in `requirements.txt`. Complex compound manifest upgrades (e.g. multi-package solver locks) abstain.
3. **Execution Receipts:** Attestation receipts are process-local capabilities in memory. Cross-process persistence of executable authorization is not implemented; proof must be re-run freshly.
4. **Live GitHub Transport:** GitHub API integration is read-only. For end-to-end demonstrations without third-party rate limits, controlled synthetic Git fixtures are utilized and explicitly labeled `CONTROLLED_FIXTURE`.
5. **No Auto-Merge:** UNBODGE will never merge code automatically. All successful investigations produce a proposal ref for human maintainer review.
