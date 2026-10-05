# UNBODGE — Phase 3: Reasoning, Research & Real Cases

## Mission
Add intelligence to the proven deterministic system without allowing intelligence to become the authority.

## Scope
Build `ReasoningProvider`, `MockReasoningProvider`, `NebiusReasoningProvider`, structured Pydantic outputs, Tavily research, research evidence/caching, LangSmith tracing, first real historical cases, benchmark dataset foundation, and human-evaluation preparation.

## Reasoning Interface
Operations:
- `analyze_upstream()`
- `analyze_workaround()`
- `generate_reproduction()`
- `synthesize_evidence()`

Reasoning may propose interpretations, candidates, hypotheses, reproduction plans, and evidence synthesis. It never authorizes removal.

## Provider Order
Prove with `MockReasoningProvider` first, then integrate Nebius/Nemotron behind the same interface using:
`NEBIUS_API_KEY`, `NEBIUS_BASE_URL`, `NEBIUS_MODEL`.

## Causal Analysis
Reasoning helps connect:
upstream issue → fixing commit → release → behavior change → downstream symptom → workaround.

Deterministic evidence validates the claims.

## Tavily
Use for issue discovery, release research, documentation, migration notes, and relevant discussions. Search results are evidence inputs, not automatic truth. Cache and record queries/results.

## LangSmith
Trace workflow, model calls, tool calls, sandbox runs, and decisions. Create benchmark dataset `unbodge-history-v1`.

## First Real Case
Choose a real Python/PyPI case where an upstream bug existed, a downstream workaround was introduced, the bug was later fixed and released, the workaround is isolatable, historical versions install, and behavior reproduces. Hand-verify first.

## Safety Gate
A proposal requires verified upstream fix, release, workaround, causal support, historical reproduction, expected old/no-workaround failure, new/no-workaround pass, regression pass, and captured evidence. Otherwise `ABSTAIN`.

## Human Evaluation
Labels: `OBSOLETE`, `NOT_OBSOLETE`, `AMBIGUOUS`, `UNPROVABLE`. Toloka is optional evaluation infrastructure; Tendem is only for selected high-value abstentions.

## Credit Discipline
Do not consume credits for architecture/core. Order: Nebius/Nemotron → LangSmith → Tavily → Toloka → Tendem.

## Exit Criteria
Mock and real reasoning providers share an interface; structured reasoning works; deterministic evidence remains authoritative; research is captured; tracing works; at least one real case is reproduced and one insufficient case abstains.

## Anti-Drift Rule
When something fails, determine whether the problem is missing evidence, missing tooling, or missing reasoning before increasing model capability.
