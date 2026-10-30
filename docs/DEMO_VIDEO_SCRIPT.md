# UNBODGE — Demo Video Script (2 Minutes 45 Seconds)

**Target Track:** Coding and Agentic Engineering  
**Pacing:** Clear, measured, technical, and confident.  
**Total Target Duration:** 2 minutes 45 seconds (under the 2:50 limit).

---

### [0:00 – 0:20] The Problem: Why Generative Agents Break Codebases
**Visual:** Opening screen / slide showing legacy Python codebase with an ugly defensive workaround:
```python
try:
    nickname = profile["nickname"]
except KeyError:
    # Workaround for fake-dep bug in v1.0
    nickname = "anonymous"
```
**Voiceover:**  
"Every production codebase contains defensive shims, monkey-patches, and version pins written to bypass bugs in upstream dependencies. When upstream libraries eventually fix these bugs, downstream teams almost never remove the workaround.  
Why? Because current AI coding agents rely on generative confidence. If an LLM hallucinates that a bug was resolved, removing defensive code creates silent production failures. LLM confidence is not proof."

---

### [0:20 – 0:45] The UNBODGE Approach: Empirical Hypothesis Testing
**Visual:** Terminal showing UNBODGE architecture diagram or running `python scripts/dashboard_demo.py`.
**Voiceover:**  
"Meet UNBODGE: an evidence-gated autonomous software maintenance agent.  
UNBODGE treats code maintenance not as autocomplete, but as an empirical hypothesis-testing problem. It reconstructs the exact historical conditions that necessitated the workaround, and empirically verifies whether upstream changes have made it obsolete.  
Our core safety rule: generative models propose, but deterministic evidence disposes."

---

### [0:45 – 1:10] NVIDIA Nemotron via Nebius Token Factory
**Visual:** Screen showing code in `packages/reasoning/nebius.py` and the dashboard view displaying the advisory hypothesis with `verified: false`.
**Voiceover:**  
"When an upstream event arrives, UNBODGE consults **NVIDIA Nemotron** running serverless on **Nebius Token Factory**.  
Nemotron analyzes the upstream issue description and the downstream code to synthesize a causal explanation of the bug.  
Crucially, UNBODGE tags Nemotron's output as strictly advisory: `verified = false`. It records model uncertainties and ensures that LLM prose alone can never authorize code modification."

---

### [1:10 – 1:45] Historical Provenance & Counterfactual 4-Cell Matrix
**Visual:** UNBODGE Dashboard 'Proof Explorer' and terminal output showing execution of cells A, B, C, D in Docker.
**Voiceover:**  
"Next, UNBODGE verifies deterministic Git provenance, binding the actual issue, the upstream fix commit, release ancestry, and dependency source files.  
Then comes our empirical core: a 4-cell counterfactual experiment inside isolated containers:
- In Cell A: old dependency with workaround. Must pass.
- In Cell B: old dependency without workaround. It reproduces the bug and must fail, proving the workaround was necessary.
- In Cell C: new dependency with workaround. Must pass.
- In Cell D: new dependency without workaround. Must pass!  
Every run produces an immutable execution receipt in our cryptographic attestation ledger."

---

### [1:45 – 2:15] Deterministic Policy Gate & Proposal Generation
**Visual:** Terminal showing policy evaluation `PROPOSE_REMOVAL` vs `ABSTAIN`, and the proposal commit created via Git plumbing.
**Voiceover:**  
"Before generating a pull request, UNBODGE runs a full regression suite on the candidate removal tree.  
Our deterministic policy engine requires all 6 proof pillars: verified provenance, a canonical 4-cell matrix, regression pass, receipt attestation, artifact match, and policy validation.  
If any check fails, or if provenance is unverified, UNBODGE abstains.  
When all proof succeeds, UNBODGE uses low-level Git plumbing to author an atomic proposal commit on a private index—without modifying the working tree or auto-merging."

---

### [2:15 – 2:40] The Production Dashboard Walkthrough
**Visual:** Interactive walkthrough of `http://localhost:5173`:
1. Overview screen showing metrics and integration health.
2. The dual-scenario demo: one `PROPOSE_REMOVAL` investigation and one honest `ABSTAIN` investigation where provenance was withheld.
3. Proof Explorer drill-down showing container receipts and secret-scrubbed evidence.
**Voiceover:**  
"Operators monitor all investigations through the UNBODGE dashboard built with React and Tailwind.  
Here we see our dual demonstration: on the left, a verified investigation with full proof authorized for proposal. On the right, an investigation where provenance was withheld—correctly halted in an abstained state.  
Notice operator credentials remain in memory only, and all logs are automatically scrubbed of secrets."

---

### [2:40 – 2:50] Conclusion & Track Selection
**Visual:** Final summary screen: UNBODGE logo, NVIDIA Nemotron, Nebius Token Factory, and GitHub repo link.
**Voiceover:**  
"UNBODGE bridges high-capacity NVIDIA reasoning with zero-trust empirical execution on Nebius Token Factory.  
Autonomous maintenance that proves before it prunes.  
Thank you."
