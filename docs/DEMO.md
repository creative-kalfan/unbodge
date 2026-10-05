# Demo script (under 3 minutes)

```bash
PYTHONPATH="packages;tests" python scripts/demo.py
```

Two tiers, one proof loop:

1. **Real case** (~60s, needs Docker): packaging PEP 685
   (`pypa/packaging#545`) — upstream bug, fix, release, workaround,
   causal graph, historical reconstruction, OLD/no-workaround FAIL,
   NEW/no-workaround PASS, regression PASS, evidence ledger,
   proposed PR. Skips cleanly without Docker.
2. **Synthetic proof** (~2s, always runs): A PASS, B FAIL, C/D PASS,
   regression PASS, evidence VALID, PROPOSE_REMOVAL; plus the
   ambiguous path (ABSTAIN, no PR) in the test suite.

The demo executes the actual engines (no "AI magic" path): the same
`run_pipeline` / `run_suite` / `evaluate_policy` the tests verify.
