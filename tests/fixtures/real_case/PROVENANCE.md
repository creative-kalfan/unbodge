# Real case provenance: packaging PEP 685 extras vs pip workaround

All values below were hand-verified live against PyPI and GitHub on
2026-10-04 (network available at research time). The test suite itself is
fully offline: every byte it executes ships in this directory.

## Upstream: pypa/packaging (pure Python, stdlib-only at runtime)

- Upstream problem: markers with extras ignored PEP 685 normalization.
  - Issue pypa/packaging#545 "Adhere to PEP 685 when evaluating markers
    with extras" (opened 2022-05-10, closed; part of #526; original
    problem https://discuss.python.org/t/7614).
- Fix commit: `53dbb257e5fef150d32ef85c7427133d71651989`
  (2022-05-12, PR pypa/packaging#545, merged 2022-05-12).
  Touches `packaging/markers.py` (+20/-2) and `tests/test_markers.py` (+8).
- Release containing the fix: packaging **22.0** (2022-12-07).
  First tag containing the fix commit (verified via `git tag --contains`).
- OLD version: packaging **21.3** (2021-11-17) — last minor line without it.
- Behavior (executed, real sdist bytes):
  `Marker("extra == 'foo-bar'").evaluate({"extra": "foo_bar"})`
  is `False` on 21.3 and `True` on 22.0.

## Vendored upstream bytes (SHA-256 verified against PyPI JSON API)

- `packaging-21.3.tar.gz`
  `dd47c42927d89ab911e606518907cc2d3a1f38bbd026385970643f9c5b8ecfeb`
- `packaging-22.0.tar.gz`
  `2198ec20bd4c017b8f9717e00f0c8714076fc2fd93816750ab48e2c41de2cfd3`
- `pyparsing-3.0.9.tar.gz` (packaging 21.3 marker parser dependency)
  `2b020ecf7d21b687f219b71ecad3631f644a47f01403fa1d1036b0c6416d70fb`

Staged subsets (real bytes, extracted at test time):
- 21.3: `packaging/{__init__,markers,requirements,version,specifiers,
  utils,_structures}.py` + `pyparsing/` package.
- 22.0: same minus pyparsing, plus `packaging/{_parser,_tokenizer}.py`.

## Downstream: pypa/pip (workaround + removal, both real commits)

- Downstream symptom: pypa/pip#10757 "Inconsistency in `_` -> `-`
  normalization (extras)" (opened 2022-01-03, closed); also pypa/pip#11924
  "pip does not apply packages' constraints to same package with extras"
  (opened 2023-04-05, closed).
- Workaround introduction: pypa/pip#12095 "Improve handling of constraints
  on requirements with extras" (merged 2023-10-05, first released in pip
  23.3): `_unnormalized_extras` tracking in
  `src/pip/_internal/resolution/resolvelib/candidates.py` plus the 3-way
  `match_markers` evaluation (`safe_extra` / `canonicalize_name`
  fallbacks) in `src/pip/_internal/req/req_install.py`, both carrying
  `TODO: ... when packaging is upgraded to support ... PEP 685`.
- Workaround removal: commit
  `4d70566c687d83cd8e0c0c41040b9beaca41492c`
  "Remove various extras normalization workarounds" (authored 2023-09-29
  by Stephane Bidoul, merged via pypa/pip#12300 "Upgrade vendored
  packaging to 24.0" on 2024-05-04). First stable release containing it:
  pip **24.1** (2024-06-20, verified via `git tag --contains`).
- Workaround bytes executed by the harness: `safe_extra()` verbatim from
  `src/pip/_internal/utils/packaging.py` at pip 23.3 (stdlib-only), plus a
  faithful 1:1 transcription of the 3-way `match_markers` evaluation from
  `src/pip/_internal/req/req_install.py` at pip 23.3 (the method itself
  requires `InstallRequirement` machinery, so the harness mirrors its
  exact evaluation logic; pip's real method is covered by pip's own
  `tests/unit/test_req.py::test_markers_match*` cases, whose requirement
  strings and expectations are reused verbatim as regression data).

## Causal chain (all links verified)

upstream problem (#545) -> fix commit (53dbb25) -> release (22.0) ->
downstream symptom (#11924, #10757) -> workaround introduction
(#12095, pip 23.3) -> historical reproduction (21.3 vs 22.0 vendored
bytes) -> counterfactual (compensated/plain x old/new) -> regression
(real pip marker assertions) -> evidence -> policy.
