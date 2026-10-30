# UNBODGE evidence operations dashboard

React, TypeScript, Vite, Tailwind, React Router, Radix Dialog and Zod. This is a
read-only interface over the existing Python API application's actual Store.
It has no chatbot, browser workflow engine, execution controls, proposal minting,
approval, Git mutation or merge action. No demo fallback ships in the app.

## Run locally (PowerShell, repository root)

Use Node 22.22+ and Python 3.11+. Dependencies are pinned in the single npm lockfile
under this directory. Existing backend dependencies include FastAPI and Uvicorn.

Terminal 1:

```powershell
# If needed in your Python environment:
py -3.11 -m pip install fastapi uvicorn pydantic packaging
$env:PYTHONPATH = 'packages'
$env:PYTHONDONTWRITEBYTECODE = '1'
py -3.11 -m uvicorn api.dashboard_server:app --host 127.0.0.1 --port 8000
```

Terminal 2:

```powershell
cd apps/dashboard
npm.cmd ci
npm.cmd run dev
```

Open http://127.0.0.1:5173. Both services bind loopback. Only `/api/dashboard`
is proxied to the API. No wildcard CORS, provider credentials, `.env` import or
frontend build secrets are used. If the backend process has `UNBODGE_API_TOKEN`
configured through your normal secret management, enter its operator token in
Connection settings. It is held in React memory, sent as an Authorization header,
and cleared on tab reload. Never enter GitHub, Nebius, Tavily or LangSmith keys.

The existing backend permits its original write routes without a configured API
token in local development. This is unchanged and visibly disclosed by the UI.
The frontend has no write path and its proxy does not forward those legacy routes.
Do not expose the local stack publicly. New dashboard reads enforce the existing
operator bearer check when configured, including every detail request.

`api.dashboard_server` creates the same default MemoryStore/MemoryCache application
as the original `api.server`; it does not connect a separate existing process.
To integrate an operator-configured application, call
`create_dashboard_app(existing_app)` **inside the same ASGI process**, passing the
actual existing FastAPI instance. The adapter uses that instance's Store, Cache
and sandbox attachment; it creates no independent database/cache client.

The CLI/demo/worker currently does not persist its complete proof state into this
API Store. Therefore an empty fresh dashboard is expected; running a demo in
another process will not magically populate it. This frontend does not change
Antigravity's demo or any persistence/workflow wiring to hide that limitation.

## Verified contract and screens

The original API was audited: JSON reads include `/health`, `/repositories`,
`/events`, `/candidates`, `/experiments/{id}`, `/evidence/{id}` and
`/decisions/{id}`. Existing proof, evidence and proposal lists are HTML under
`/ui/`. There was no React scaffold, JS package manager or lockfile.

Some existing raw JSON/HTML views have inconsistent redaction and experiment
association. The React client does **not** fetch them or parse HTML as JSON.
Those existing routes are unchanged and retain their pre-existing limitations.
The isolated adapter adds exactly two read routes, with explicit Pydantic response
models and the original bearer-token verification:

| Route | Actual data source | Usage |
|---|---|---|
| `GET /api/dashboard/snapshot` | Existing Store: repositories, upstream_events, workaround_candidates, causal_hypotheses, decisions, pr_results; actual app state and safe configuration-presence booleans | Overview, search/filter, proposal inventory, integration inventory |
| `GET /api/dashboard/investigations/{id}` | Exact causal_hypothesis ID; candidate/repository foreign IDs; decisions with exact hypothesis_id; evidence_ids explicitly cited by those decisions; matching experiment_id and payload | Investigation detail and Proof Explorer |

"Investigation records" means stored causal hypotheses, not a newly invented
durable investigation table. Candidate/event records remain separate. Listing
counts are observations from this API instance, capped at 200 per collection.
Capped or invalid/omitted records produce visible warnings. There is no active
workflow or globally verified proposal count because the backend cannot supply it.

| Screen | Functional today | Explicitly unavailable |
|---|---|---|
| Overview | Real bounded counts, stored hypotheses, recorded decisions and upstream events | Active workflow counts, live authorization |
| Investigations | Search and decision filtering, repositories/candidates, exact detail links | Creation, execution, persisted workflow lifecycle |
| Investigation detail | Hypothesis metadata, exact linked decisions/evidence/executions and missing-reference warnings | Stage success/timestamps; no success inferred from missing errors |
| Proof Explorer | Backend integrity results, original evidence hash, exact linked run/regression revision and artifact hashes | Live provenance/receipt revalidation or browser authorization |
| Proposal Review | Actual stored PR artifacts, branch/base/body, linked recorded decisions and proof navigation | Diff/changed files, approval status, live authorization, creation/approval/merge actions |
| Integrations | Actual Store/Cache types, sandbox attachment, safe provider configuration presence | Authentication/operational claims, expensive health probes |

Proposal artifacts are always labeled **Authorization unverified** in this
read-only view, including when a stored decision says PROPOSE_REMOVAL. ABSTAIN is
visually distinct and never becomes an authorized proposal. A hash integrity pass
only concerns the stored record; it does not authorize removal. No private receipt,
environment mapping, raw payload, stdout/stderr or trace is serialized to React.
Receipt availability is not assumed across application restarts.

Association follows exact stored IDs only. No joins on A/B/C/D suffixes, titles,
timestamps, repository proximity or shared text. Linked execution records must
match their validated evidence payload. Missing/contradictory records stay missing
or invalid. The adapter does not redefine policy or re-run protected authorization.

## Security and isolation

- All preflight files, including uncommitted proof repair and Antigravity changes,
  were hashed before implementation; final comparison is recorded below.
- All task files are new. No original backend/API, protected proof file, existing
  test, deployment config, README or status report is edited.
- Provider environment values are never returned; presence is not authentication.
- Identifiers are bounded/validated; display text is allowlisted, redacted before
  truncation, and rendered as React text. Unknown/malformed responses fail closed
  through Zod. Error messages are fixed safe strings, never server exception bodies.
- No localStorage/sessionStorage, browser provider API calls, credential cookies,
  analytics or external font/CDN requests. Operator token is ephemeral memory only.
- New responses have `Cache-Control: no-store`, restrictive security headers and
  generic failures. Legacy API behavior/headers are preserved by the optional mount.
- This is operator-level access over the existing Store, not a new tenant or
  per-user authorization system. Exact association prevents accidental cross-record
  joins; it does not invent ownership absent from the backend schema.
- Secret-shape redaction is defense in depth; arbitrary unknown secrets cannot be
  recognized mathematically. Do not put credentials into human-readable record
  fields. The adapter deliberately omits high-risk internal payloads and logs.

The requested dev-team review used PM, Architect, Developer and QA lenses. All four
flagged missing data relationships and the risk of misleading green states as
blocking design concerns. The chosen contract displays observations with explicit
limits instead of adding workflow or authorization logic. The UI-animation review
kept motion to press feedback and disclosure chevrons (140–150ms); navigation and
data loading do not animate. Reduced-motion overrides remove transitions and
pressed transforms. Three.js was reviewed but not added: 3D provides no functional
benefit to this dashboard. Focus states, a skip link, native controls and a Radix
focus-trapped dialog provide keyboard access.

## Task files

All 18 files are new; no pre-existing file was edited:

- `apps/dashboard/package.json`, `package-lock.json`, `.gitignore`, `index.html`,
  `tsconfig.json`, `vite.config.ts`, and this `README.md`.
- `apps/dashboard/src/App.tsx`, `api.ts`, `main.tsx`, `styles.css`.
- `apps/dashboard/src/App.test.tsx`, `api.test.ts`, `test/records.ts`, `test/setup.ts`.
- `packages/api/dashboard.py`, `packages/api/dashboard_server.py`.
- `tests/test_dashboard_api.py`.

## Verification

```powershell
cd apps/dashboard
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
# No separate lint configuration was introduced.
```

From repository root:

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
py -3.11 -m pytest -p no:cacheprovider tests/test_dashboard_api.py -q
py -3.11 -m pytest -p no:cacheprovider tests/test_api.py tests/test_views.py tests/test_reasoning.py tests/test_integrations_audit.py -q
py -3.11 -m pytest -p no:cacheprovider tests/test_proof_authorization.py -q
py -3.11 -m pytest -p no:cacheprovider -q -rs
pyright.cmd packages/api/dashboard.py packages/api/dashboard_server.py
```

Actual session results (2026-10-27):

- New adapter: all 12 cases passed in the final targeted backend group below.
  Earlier standalone run: 11 passed in 1.31s. Initial RED: missing module collection error;
  first implementation 2 failed/7 passed exposed HTTP method handling and a
  synthetic sentinel shape gap; both repaired in the new adapter only. Additional
  RED/GREEN cases cover validation-error input echo, missing stored timestamps,
  real repository IDs and encoded investigation IDs.
- Frontend: **14 tests passed** across two files in 4.52s; type checking passed. Tests cover
  routing/navigation, loading, safe HTTP errors/retry, empty/unavailable states,
  ABSTAIN, missing evidence, unsupported schemas, transient auth, search/filter,
  hostile/long text, request timeout/cancellation and encoded IDs.
- Production build passed: JS 418.12 kB / 128.27 kB gzip, CSS 19.28 kB / 5.57 kB
  gzip at the recorded build. A later build may have a different content hash.
- Final API/view/reasoning/integration group plus all 12 new adapter cases:
  **62 passed in 1.69s**. No existing test was changed to achieve this.
- New Python modules: Pyright 0 errors, 0 warnings, 0 informations.
- Browser: actual loopback Uvicorn + Vite; overview, investigations, proof,
  proposals and health navigated successfully with real empty Store responses.
  Radix token input autofocus, Tab to Connect, Escape close and focus restoration
  verified. Narrow development layout and desktop production-preview layout
  inspected. Production deep-link fallback and real API 404 display verified.
  Populated detail data is covered by
  API/component tests, not claimed as a live external workflow.
- Lint: not configured. No external scanner or physical touch-device validation
  is claimed. No paid external-service verification was performed.
- Full Python 3.11 suite: **361 passed, 4 failed, 2 skipped in 560.51s**. This run
  preceded the final adapter-only error/default-value/identifier hardening; the
  final 62-test group and type checks above cover that final adapter state. All
  **30 existing proof-authorization regression cases passed** within the full run.
- Docker is now available (server 29.7.2), unlike the preceding repair session.
  Its container tests ran. The four failures are existing protected backend paths:
  `tests/test_benchmark.py::test_measured_variants_match_expected_outcomes`,
  `tests/test_phase2_proof.py::test_phase2_local_proof_end_to_end`,
  `tests/test_realcase.py::test_real_case_proposes_removal`, and
  `tests/test_realcase.py::test_real_case_ambiguous_abstains`. Expected proposals
  instead abstain; the last trace explicitly reports
  `execution receipt does not match artifact, command or result`, leaving workflow
  state at REGRESSION_TESTING. These are **FAIL**, not UNVERIFIED or PASS.
- The standalone command targeting only
  `tests/test_phase2_proof.py::test_phase2_local_proof_end_to_end` reproduced
  **1 failed in 26.41s**, without importing the frontend or dashboard adapter.
  Canonical matrix and regression PASS assertions succeed before the proposal
  assertion fails. No protected code or existing tests were changed to suppress it.
- The two full-suite skips are optional PostgreSQL/Redis service integrations
  because their disposable test connection variables are unset.
- Final isolation: all **169 preflight files remain byte-for-byte unchanged**;
  protected proof files and all Antigravity work are preserved. Repository HEAD
  and staged state remain unchanged. No commit or push was made.

The complete backend run uses the same pytest arguments above inside a temporary
Windows `SetThreadExecutionState(0x80000001)` request, released in `finally` with
`SetThreadExecutionState(0x80000000)`, to avoid host sleep during Git fixture tests.
This changes no power plan or repository configuration.

The Docker receipt failure needs a separate protected-backend task. This frontend
does not present failed real-container proof as authorized, and does not weaken
the proof boundary to get a green demonstration.

## Production deployment still required

`npm.cmd run build` emits `dist/`. `npm.cmd run preview` serves it on loopback
port 4173 with the same development API proxy for local inspection only. Production
needs a proper static asset host with SPA history fallback, same-origin reverse
proxy for only `/api/dashboard`, HTTPS, CSP/frame restrictions at the hosting
boundary, configured operator authentication and a deliberately shared backend
instance. Existing Docker/Compose files do not build or serve this React bundle
and were preserved. No production deployment or cloud expenditure was attempted.

Next integration work belongs in separate tasks: persist/link real workflow proof
records into the backend Store, expose authoritative workflow/diff/review metadata,
and establish durable receipt/authorization and authenticated provider health.
Never infer those capabilities from a frontend status indicator.

Implementation references: [Vite server options](https://vite.dev/config/server-options),
[Tailwind with Vite](https://tailwindcss.com/docs/installation/using-vite),
[React Router declarative routing](https://reactrouter.com/start/declarative/routing).
