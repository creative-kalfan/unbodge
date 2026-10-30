# UNBODGE implementation status and remaining work

Updated 2026-10-26 (Asia/Calcutta). Base: `main`, `27352f5ffd14c6390d938334749e74f2883482bf`, plus the uncommitted proof-authorization repair described here. No commit or push was made.

This document supersedes the 2026-10-23 report. That report mixed real implementation with nonexistent files/endpoints, an absent Phase 5 plan, and unsupported test/coverage counts. Its claims of a complete/trustworthy MVP and 1,055 tests/91.07% coverage are withdrawn. Current results below are fresh results from this repair.

## Current assessment

The controlled local proof-authorization boundary is repaired and permanently regression-tested. This is not a claim that the whole product is finished or deployed. Redis, API serialization, frontend, persistence wiring and deployment were outside this task and were not modified.

Available specifications: PHASE_1_FOUNDATION.md, PHASE_2_PROOF_ENGINE.md, PHASE_3_REASONING_REAL_CASES.md and PHASE_4_PRODUCT_EVALUATION_SUBMISSION.md. The original implementation blueprint and complete architecture plan remain unavailable in this checkout. No new architecture or product scope was substituted for them.

## What changed and why

1. **Provenance:** `GitProvenance.verify` reads the configured metadata adapter and upstream/downstream Git objects. It checks repository and issue identity; an independently retrieved symptom linked to the issue; fixing-commit identity/content and issue reference; old/fix/release ancestry; release metadata; introduction ancestry and issue/symptom references; the actual introduction/removal patch; pinned dependency version; dependency-source content binding; and an OLD-to-NEW change restricted to bound dependency sources plus the single requirements pin. Independent downstream fixes cannot masquerade as upstream causality. Caller-provided release/issue/fix fields alone cannot authorize.
2. **Exact artifact:** source artifact hashes bind paths and UTF-8 content. Regression materializes NEW, removes the recorded workaround, and executes that complete tree. The same removal artifact must match counterfactual D and the proposed PR tree. Unsupported/omitted files and modes fail closed rather than receiving partial proof.
3. **Execution:** a process-local execution ledger records immutable JSON snapshots from the configured sandbox. Opaque receipts bind experiment identity, revision, artifact, argv, requested environment, outputs, exit code and duration. Evidence/run records are checked against these receipts, including output-artifact hashes, actual environment and parsed regression counts. Caller-supplied PASS records, unknown receipts and rehashed-but-inconsistent evidence cannot authorize.
4. **PR boundary:** `LocalPrGenerator.create_proposal` requires a complete `RemovalProof`, re-verifies provenance/execution/evidence, re-evaluates policy, checks decision equality, target tree, base revision and clean checkout, and requires PROPOSE_ONLY/PROPOSE_REMOVAL before mutation.
5. **Exact commit:** Git plumbing uses a private index to commit the complete authorized text tree, including deletions, without changing the worktree/index/HEAD. Atomic new-ref creation and replay rejection replace the duplicate-branch fallback.
6. **UTF-8 source integrity:** Git proof reads explicitly decode UTF-8 rather than the Windows locale encoding. Non-UTF-8 proof source fails closed. An offline real-dependency provenance check passes with 39 bound source records; this is not a container or authenticated public-history result.
7. **Failure behavior:** missing/contradictory proof yields ABSTAIN with an explicit terminal `PipelineState.failure` and no proposal. The last legal workflow position is preserved; stages are not fabricated to jump to a terminal workflow enum. Re-entering a failed state does nothing.
8. **Preserved invariants:** the policy engine still accepts no model prose/confidence, remains PROPOSE_ONLY and contains no automatic-merge path.

## Trust boundary and limitations

- Metadata adapters, upstream checkouts and sandbox implementations are trusted, operator-configured application dependencies. They must never be constructed from untrusted repository contents, LLM outputs or job JSON. This is not a sandbox against arbitrary Python code running inside the application process.
- A fixture metadata client and generated upstream mirror establish controlled-test provenance, not authenticated GitHub history. The current conservative verifier requires explicit canonical issue/symptom references in the configured commit history; implicit associations need separately verified handling and otherwise abstain.
- Historical-dependency fixtures replay real packaged source bytes in a controlled Git mirror with its own generated fix SHA. They do not assert that a generated fixture commit is the original public upstream commit.
- No live GitHub/PyPI transport was added. Real operational provenance requires an authenticated/verified metadata source and a corresponding upstream checkout. Existing jobs without these configured dependencies now abstain.
- Receipts are intentionally process-local. Serialized evidence is not a reusable authorization capability; after process loss/restart, execution must be repeated. Durable receipt storage/recovery is not implemented here.
- The current causal comparison supports a single exact package pin in requirements.txt and explicitly mapped dependency-source files; unrelated OLD-to-NEW application/configuration changes abstain. Supporting other manifest layouts or compound upgrades requires separate verified handling.
- Complete artifacts currently support bounded regular non-executable UTF-8 text trees. Binary, hidden/omitted, symlink or unsupported-mode artifacts fail closed. Broader artifact support is future work, not implicit proof.
- The general evidence model still permits nested payload mutation; deterministic hash validation and receipt/provenance comparison reject changed records at authorization. Deep immutability itself was not redesigned.
- Docker-backed historical verification is UNVERIFIED in this session: the Docker Linux-engine named pipe was unavailable. No historical container PASS is claimed.

## Revised requirement statuses

| Requirement | Current status | Evidence / remaining limitation |
|---|---|---|
| Caller claims cannot authorize a removal | DONE — VERIFIED | Unsupported issue/fix and caller-only release regression tests; explicit ABSTAIN/safe failure |
| Local Git/metadata provenance gate | DONE — VERIFIED | Controlled upstream/downstream repositories and independent configured metadata; live authenticity is separate |
| Regression bound to exact removal tree | DONE — VERIFIED | Captured inputs exclude workaround; file-sensitive failure sentinel; artifact/receipt/revision checks |
| Direct PR authorization before mutation | DONE — VERIFIED | Complete-proof negative tests plus reference/index/worktree snapshots |
| Evidence/experiment/decision consistency | DONE — VERIFIED | Tampering, rehashing, missing evidence, wrong receipt/identity/artifact tests |
| Exact proposed Git tree and replay prevention | DONE — VERIFIED | Positive authorized proposal tree equality, actual deletion, unchanged HEAD/worktree, replay rejection |
| Synthetic proof and policy abstention | DONE — VERIFIED | Existing synthetic and policy suites |
| Real historical container proof | UNVERIFIED | Docker engine unavailable; required tests remain present and skipped explicitly |
| Live GitHub/PyPI integration | NOT STARTED | Existing interfaces/fixtures remain; transport was outside this repair |
| Restart/durable authorization | PARTIAL | Fail-closed process-local receipts; durable integration still absent |
| Full product readiness | PARTIAL | Existing backend, serialization, frontend, workflow and deployment gaps remain |

No overall completion percentage is asserted.

## Permanent regression coverage

`tests/test_proof_authorization.py` contains 30 cases and covers:

- unrelated issue/nonexistent fix and caller-only release;
- independent wrong issue, unknown commit, unverified release and unlinked symptom;
- retained workaround versus exact removal regression;
- wrong regression revision and mismatched experiment identity;
- direct ABSTAIN, invalid-evidence references, failed-regression decision and unauthorized mode;
- missing regression, changed artifact, unknown receipt, foreign experiment and incomplete evidence;
- tampered evidence and rehashed output-artifact/regression records;
- valid controlled proof, exact deletion/tree identity, unchanged checkout and replay rejection;
- explicit missing-provenance ABSTAIN/safe failure and safe re-entry;
- rejection of a downstream-local fix that confounds upstream attribution;
- exact UTF-8 Git source reads and rejection of non-UTF-8 blobs;
- end-to-end abstention with valid provenance but ambiguous execution or a genuinely failed removal regression.

Existing synthetic, policy, evidence, safety, historical and benchmark tests remain. Fixture wiring now supplies explicit controlled provenance instead of relying on unsupported claims. An already-fixed OLD fixture without a real fixing change may correctly abstain before counterfactual execution.

## Files changed

Application:

- packages/domain/models.py
- packages/experiments/attestation.py (new)
- packages/experiments/real.py
- packages/github/git.py
- packages/history/provenance.py (new)
- packages/policy/authorization.py (new)
- packages/pr/generator.py
- packages/workflow/pipeline.py
- packages/workflow/stages.py

Tests:

- tests/proof_support.py (new)
- tests/test_proof_authorization.py (new)
- tests/phase2_support.py
- tests/realcase_support.py
- tests/test_phase2_proof.py
- tests/test_realcase.py
- tests/test_proof_chain.py
- tests/test_benchmark.py (fixture wiring only)

Documentation: this file. Redis, API, frontend and deployment source/configuration are unchanged.

## ECC planning contracts

| Slice | Contract | Deterministic proof | Consumer | Infrastructure cost |
|---|---|---|---|---|
| Provenance | Configured metadata + Git objects yield a checked chain or safe failure | Unsupported/unrelated issue, fix, release, symptom and downstream-confounder tests | Policy stage and PR authorization | Local Git; zero external spend in this run |
| Artifact/execution | Exact removal input and sandbox receipt bind each result | Retained-workaround, wrong-revision/artifact/receipt and rehash tests | Policy and PR boundary | Injected execution in unit tests; local Docker when available |
| PR boundary | Only a matching complete PROPOSE_ONLY proof may mutate Git | Direct-call rejection, exact committed tree and replay tests | Workflow create_pr stage | Local Git only |
| Failure/source integrity | Missing proof abstains; supported text preserves exact UTF-8 content | Terminal safe-failure, UTF-8 and invalid-text tests | Local workflow/CLI and provenance reads | No services or cloud |

## TDD and verification evidence

Journeys/acceptance criteria came directly from the user's proof-authorization repair request and the mandatory latest-audit bypass cases. ECC TDD, surgical-patch and verification workflows were applied; manual security review checked the trust roots, exact-artifact binding, receipt integrity and pre-mutation PR boundary. User instruction prohibited checkpoint commits, so red/green evidence is preserved here instead.

- Initial RED: `py -3.11 -m pytest -p no:cacheprovider tests/test_proof_authorization.py -q`: **9 failed in 23.10s**, all on the reproduced authorization/state/identity defects.
- First nine-case GREEN after configured fixture provenance: same target, **9 passed in 43.96s**.
- Explicit missing-proof failure RED: `py -3.11 -m pytest -p no:cacheprovider tests/test_proof_authorization.py::test_missing_provenance_returns_explicit_safe_failure -q`: **1 failed in 3.64s**, before pipeline failure handling was implemented.
- Positive exact-tree/replay target: **1 passed in 25.16s**.
- Later focused proof/synthetic/policy target: **13 passed in 30.72s**.
- Additional RED: independent downstream-fix confounder, **1 failed in 27.70s**; GREEN with the positive exact-tree proof, **2 passed in 41.85s**.
- UTF-8 RED, **1 failed in 5.73s**; invalid-text RED, **1 failed in 4.99s**; both GREEN, **2 passed in 9.64s**.
- Valid-provenance ambiguous/failed-regression end-to-end cases: **2 passed in 52.19s**.
- Initial concurrent full attempts before the last hardening each reported **3 failed, 313 passed, 22 skipped**. Git subprocess timeout traces included negative remaining timeout values and about 9h20m reported elapsed time, consistent with a host suspension/timing interruption. These are not clean acceptance runs or usable performance measurements; positive fixture failures safely abstained. Later final reruns below supersede them.
- Intermediate focused/full runs were stopped when further security/source-integrity defects were identified; incomplete runs are not counted as completed acceptance verification.

| Final verification | Command / invocation | Actual result |
|---|---|---|
| Python 3.11 complete supported suite | `py -3.11 -` with the in-memory trace harness described below, calling `pytest.main(['-p','no:cacheprovider','-q','-rs'])` | **321 passed, 22 skipped in 359.76s**; exit 0 |
| Python 3.14 complete supported suite | `py -3.14 -` with the temporary system-awake wrapper below, calling the same pytest arguments | **321 passed, 22 skipped in 262.39s**; exit 0; temporary system-awake request successfully released |
| Offline historical provenance prerequisites | Temporary real-dependency fixture and controlled upstream mirror, calling `ctx.provenance.verify(ctx)` without a sandbox | **PASS: 39 bound source records**; generated fix SHA differs from the public historical SHA; execution remains UNVERIFIED |
| Docker historical/container tests | Tests remain in the complete suite, gated by `docker_available()` | **UNVERIFIED:** Linux-engine named pipe unavailable; 20 Docker-dependent tests skipped |
| Unrelated database integrations | Complete suite optional integration tests | 2 skipped: disposable PostgreSQL/Redis URLs unset; outside this repair |

Before the successful final 3.14 rerun, a complete attempt reported **4 failed, 317 passed, 22 skipped in 45996.92s**. All four failures were fixture Git subprocess timeouts with negative remaining timeouts and a reported multi-hour elapsed time, consistent with a host timing interruption; that attempt is recorded as failed, not PASS. A subsequent incomplete run was restarted after its tool output/session handle was lost. The final rerun held a temporary Windows system-awake request for the test process; no power plan was changed.

Python 3.14 wrapper (stdin to `py -3.14 -`):

```python
import ctypes,sys,pytest
kernel=ctypes.windll.kernel32
previous=kernel.SetThreadExecutionState(0x80000001)
print('TEMPORARY_SYSTEM_AWAKE_REQUEST',bool(previous),flush=True)
try:
    code=pytest.main(['-p','no:cacheprovider','-q','-rs'])
finally:
    restored=kernel.SetThreadExecutionState(0x80000000)
    print('TEMPORARY_SYSTEM_AWAKE_RELEASED',bool(restored),flush=True)
raise SystemExit(code)

```

- `pyright.cmd packages/domain/models.py packages/experiments/attestation.py packages/experiments/real.py packages/github/git.py packages/history/provenance.py packages/policy/authorization.py packages/pr/generator.py packages/workflow/pipeline.py packages/workflow/stages.py`: **0 errors, 0 warnings, 0 informations**.
- Standard-library `ast.parse` syntax checks on the 11 new/changed core and proof-test files: **PASS**.
- `git diff --check`: **PASS**. Scope review found no changes to Redis, API, frontend or deployment code. Repository HEAD remains `27352f5ffd14c6390d938334749e74f2883482bf`.

All Python tests used PYTHONDONTWRITEBYTECODE=1 and pytest cacheprovider was disabled. No credentials or external/cloud services were used. New fixture execution backends are injected, file-sensitive test doubles; they are not reported as real containers.

Coverage was measured in memory with Python's standard-library `trace.Trace(count=True, trace=False, ignoredirs=[sys.prefix, sys.base_prefix])` wrapping `pytest.main(['-p','no:cacheprovider','-q','-rs'])`. Executable lines came from `trace._find_executable_linenos`; no coverage database/configuration was created. This is line coverage of the three new boundary modules, not branch coverage or a fabricated whole-repository percentage.

| New module | Executable lines covered |
|---|---|
| packages/experiments/attestation.py | 31/31 (100.0%) |
| packages/history/provenance.py | 113/114 (99.1%) |
| packages/policy/authorization.py | 138/141 (97.9%) |
| Total of these three modules | **282/286 (98.6%)** |

Security review: unauthorized calls are validated before Git mutation; receipt snapshots are immutable JSON; filesystem artifacts are deterministically hashed and re-derived; proposal commits use argv-only Git plumbing, a private index and atomic new-ref creation; no merge/model-authority capability was added. External scanner results are not claimed.

Known environment warnings: pytest-asyncio loop-scope deprecation on 3.11; installed LangSmith's Pydantic-v1 compatibility warning on 3.14. Ruff/Bandit and third-party coverage packages were not installed; syntax/type checks, tests, standard-library coverage and manual security review were used.

## Remaining work, in priority order

1. Restore Docker and rerun the historical proof and adversarial container tests; independently validate authenticated upstream metadata/Git snapshots rather than treating the controlled mirror as public-history proof.
2. Integrate operator-configured metadata/execution dependencies and durable workflows/persistence without weakening receipt or PR authorization. Missing configuration must continue to abstain.
3. Reverify and address the previously reported Redis, public serialization and proof-view isolation defects in separate scoped changes; none was reverified or repaired here.
4. Complete real external adapter verification, realistic evaluation/human labels, deployment and submission artifacts after these safety and integration gates.

## External API Integration Audit and Safe Wiring (2026-10-26)

Audit performed under isolation rules (Codex proof authorization boundaries strictly preserved).

### Integration Summary

| Integration | Classification | Status & Verification Details |
|---|---|---|
| Environment Configuration (`.env`) | VERIFIED WORKING | `.env` ignored by git, `.env.example` created with placeholders, `.dockerignore` excludes secrets, `packages/env_config.py` provides non-overwriting process loading. Corrected keys `NEBIUS_API_KEY` and `NEBIUS_MODEL`. |
| Nebius Token Factory & Nemotron | MOCK-VERIFIED / BLOCKED (LIVE) | Mocked tests pass (100% invariant enforcement: models cannot claim verification). Base URL `https://api.tokenfactory.nebius.com/v1`. Live key validation returned HTTP 401 Unauthorized; live test blocked pending valid credentials. Model `Nemotron-3-Ultra-550b-a55b-serverless` validated against official provider documentation. |
| Tavily Research | MOCK-VERIFIED / VERIFIED LIVE AUTH | Authenticated ping via search endpoint returns HTTP 400 (Query missing) with valid key vs HTTP 401 with invalid key. Mock tests verify provenance hashes and timeout handling. Research outputs cannot bypass deterministic proof gates. |
| LangSmith Tracing | VERIFIED WORKING / MOCK-VERIFIED | Live `/info` endpoint verified HTTP 200 with configured key. Dynamic tracer selection (`get_default_tracer()`) defaults to `LocalTracer` and enables `LangSmithTracer` when key is present. Sentinel secret scrubbing active before buffering. Proof loop unaffected by tracing failures. |
| GitHub API Access | MOCK-VERIFIED / VERIFIED LIVE AUTH | Live read token authenticated against `/rate_limit` (5,000 req/hr). Implemented `ReadOnlyGitHubClient` in `packages/github/client.py`; all mutations (`create_branch`, `create_commit`, `create_pull_request`) fail-closed with `GitHubReadOnlyError`. |
| PostgreSQL / Redis | CONFIGURED BUT DISCONNECTED | Intentionally left disabled/local per task instructions due to known independent defects. |

### Verification Evidence
- Python 3.11: 333 passed, 22 skipped in 219.81s (full suite clean).
- Python 3.14: 12 passed in 0.22s on new integration suite (`tests/test_integrations_audit.py`).
- Zero modifications to protected Codex files (`stages.py`, `pipeline.py`, `pr/generator.py`, `policy/authorization.py`, `history/provenance.py`).
- No git commits or pushes performed.

## Final status

The local proof-authorization repairs are supported by the fresh tests above. Full real-container verification remains explicitly unavailable. The application is not declared production-ready. No automatic merging, production credentials, cloud expenditure, repository commit or push was introduced.

