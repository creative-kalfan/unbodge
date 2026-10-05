# Benchmark methodology (unbodge-history-v1)

## Dataset: 10 cases

- 2 OBSOLETE, measured via full Docker pipeline runs
  (`case:packaging-pep685`, `case:packaging-pep685-norm`).
- 3 AMBIGUOUS, measured via full pipeline runs that must abstain
  (normalized input, case variant, punctuation variant).
- 5 UNPROVABLE: real upstream metadata (urllib3#3053, urllib3#3734,
  anyio#1189, packaging#674, packaging#712) with no verified
  workaround link; resolved through the evidence-completeness gate
  without execution. Expected outcome: ABSTAIN.

Labels reflect reality, never manufacturing: nothing is claimed
measured unless executed. Provenance per case cites real artifacts.

## Baselines (same 10 cases, honest mechanisms)

1. `llm_only` — mock reasoning synthesis only. The conservative stub
   abstains everywhere (removal recall 0 by construction).
2. `llm_plus_search` — plus mock research. Still no execution: abstains.
3. `no_counterfactual` — real policy gate over an incomplete matrix:
   abstains (demonstrates the gate).
4. `full_unbodge` — measured pipeline outcomes + completeness gates.

## Metrics (11, all measured; `None` when undefined)

safe_removal_precision, abstention_accuracy, causal_link_accuracy,
historical_reconstruction_success, counterfactual_success,
regression_pass_rate, unsafe_removal_rate, human_agreement, latency,
cost, time_saved (estimate, labeled as such).

## TARGET vs MEASURED

`TARGETS` in `benchmark/metrics.py` holds aspirations (e.g. dataset
size 30). Reports print both columns; a target is never presented as
a result. Current measured highlights: precision 1.0 on proposed
removals, unsafe rate 0.0, cost $0.00.
