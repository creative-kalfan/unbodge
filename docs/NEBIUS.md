# Nebius / NVIDIA usage (Phase 4)

## Actually used

Nothing executed on Nebius infrastructure in Phase 4. No credits
consumed ($0.00, mechanically enforced by the offline test fixture).

## Prepared integrations (fail-closed, tested without cloud)

- `NebiusReasoningProvider` (`NEBIUS_API_KEY`, `NEBIUS_BASE_URL`,
  `NEBIUS_MODEL`): OpenAI-compatible chat completions for Nemotron-class
  models behind `ReasoningProvider`. Unit-tested via injected transports
  (auth/timeout/rate-limit/malformed mapped to typed errors; outputs
  forced `verified=False`).
- `NebiusSandbox` (`NEBIUS_API_KEY`, `NEBIUS_SANDBOX_URL`): same sandbox
  ABC as `DockerSandbox` (identical validation semantics, portable
  experiment specs). Request/response mapping unit-tested via injected
  transport. Without credentials every execution raises
  `SandboxUnavailableError`; local Docker execution stays authoritative.

## Where Nebius provides value next

Model inference (causal hypotheses, reproduction plans, evidence
synthesis review) and elastic sandbox capacity for the 30-50-case
benchmark expansion. Both plug behind existing stable interfaces with
no proof-loop changes.
