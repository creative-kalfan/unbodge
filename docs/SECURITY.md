# Security model (Phase 4)

Repository content, issue text, research results, patches, sdists, and
container outputs are UNTRUSTED throughout.

## Boundaries

- Commands: allowlist + grammar + argv vectors; no shell anywhere.
- Paths: traversal guards on git show, archives, patches, markers,
  staging, container files, sdist extraction.
- Secrets: allowlist env sanitization; deterministic redaction pass
  (`evidence/scrub.py`) for public representations; raw records
  immutable and never served.
- Network: containers `--network none`; suite blocks live sockets
  (autouse fixture); providers fail closed without credentials.
- Resources: timeouts (+kill), output/artifact/env/patch caps,
  scan caps, buffer caps.
- Webhooks: HMAC-SHA256, size cap, event allowlist, idempotent
  delivery handling, rate limiting.
- Policy: deterministic gate over validated evidence only; no text
  inputs; no auto-merge path exists (asserted in tests).
- Retries: idempotent upserts by natural key; no duplicate PRs.

## Tested attacker behaviors

Command/prompt injection, path traversal, malicious repos/packages,
secret leakage, resource exhaustion, sandbox escape attempts, webhook
forgery, malformed/oversized API input, duplicate delivery,
flaky/contradictory evidence, hallucinated commits. See
`tests/test_failure_modes.py`, `tests/test_security.py`,
`tests/test_sandbox.py`, `tests/test_docker_sandbox.py`.
