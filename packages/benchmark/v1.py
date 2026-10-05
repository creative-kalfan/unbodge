"""Benchmark dataset unbodge-history-v1 (Phase 4).

10 cases: 2 measured OBSOLETE (real pipeline runs), 3 measured
AMBIGUOUS (real pipeline runs that must abstain), 5 UNPROVABLE (real
upstream metadata, no verified workaround link -- expected ABSTAIN via
the completeness gate, never executed). Nothing is manufactured: every
field traces to a verified upstream artifact listed in ``provenance``.
"""

from __future__ import annotations

from benchmark.models import (
    BenchmarkCase,
    BenchmarkDataset,
    BenchmarkDependency,
    BenchmarkHistory,
    BenchmarkLabel,
    BenchmarkProvenance,
    BenchmarkRepository,
    BenchmarkUpstream,
    BenchmarkWorkaround,
)
from domain.enums import DecisionOutcome


def _provenance(*sources: str, method: str) -> BenchmarkProvenance:
    return BenchmarkProvenance(sources=list(sources), method=method)


_PACKAGING_ISSUE_TITLE = "Adhere to PEP 685 when evaluating markers with extras"


def _packaging_case(
    case_id: str,
    label: BenchmarkLabel,
    expected: DecisionOutcome,
    marker: str,
    extra: str,
) -> BenchmarkCase:
    return BenchmarkCase(
        id=case_id,
        repository=BenchmarkRepository(id="repo:pip", full_name="pypa/pip"),
        dependency=BenchmarkDependency(
            name="packaging", old_version="21.3", new_version="22.0"
        ),
        upstream=BenchmarkUpstream(
            issue_id="issue:packaging-545",
            issue_url="https://github.com/pypa/packaging/issues/545",
            issue_title=_PACKAGING_ISSUE_TITLE,
            fix_commit_id="fix:packaging-53dbb25",
            fix_commit_sha="53dbb257e5fef150d32ef85c7427133d71651989",
            release_id="rel:packaging-22.0",
            release_tag="22.0",
        ),
        workaround=BenchmarkWorkaround(
            candidate_id="cand:pip-compat",
            file_path="pip_compat.py",
            description="compensated marker evaluation (safe_extra fallback)",
        ),
        history=BenchmarkHistory(),
        expected_outcome=expected,
        evidence_refs=[],
        label=label,
        provenance=_provenance(
            "https://github.com/pypa/packaging/issues/545",
            "https://github.com/pypa/pip/pull/12095",
            method=f"hand-verified; symptom marker={marker!r} extra={extra!r}",
        ),
    )


def _unprovable(
    case_id: str,
    repo_id: str,
    full_name: str,
    dependency: str,
    old_version: str,
    new_version: str,
    issue_id: str,
    issue_url: str,
    issue_title: str,
    fix_id: str,
    fix_sha: str,
    release_id: str,
    release_tag: str,
) -> BenchmarkCase:
    return BenchmarkCase(
        id=case_id,
        repository=BenchmarkRepository(id=repo_id, full_name=full_name),
        dependency=BenchmarkDependency(
            name=dependency, old_version=old_version, new_version=new_version
        ),
        upstream=BenchmarkUpstream(
            issue_id=issue_id,
            issue_url=issue_url,
            issue_title=issue_title,
            fix_commit_id=fix_id,
            fix_commit_sha=fix_sha,
            release_id=release_id,
            release_tag=release_tag,
        ),
        workaround=BenchmarkWorkaround(),
        history=BenchmarkHistory(),
        expected_outcome=DecisionOutcome.ABSTAIN,
        evidence_refs=[],
        label=BenchmarkLabel.UNPROVABLE,
        provenance=_provenance(
            issue_url,
            method="metadata-verified; no verified downstream workaround link",
        ),
    )


def build_v1() -> BenchmarkDataset:
    dataset = BenchmarkDataset(name="unbodge-history-v1", version="0.1.0")
    measured = [
        _packaging_case(
            "case:packaging-pep685", BenchmarkLabel.OBSOLETE,
            DecisionOutcome.PROPOSE_REMOVAL,
            "extra == 'foo-bar'", "foo_bar",
        ),
        _packaging_case(
            "case:packaging-pep685-norm", BenchmarkLabel.OBSOLETE,
            DecisionOutcome.PROPOSE_REMOVAL,
            "extra == 'pep-685-norm'", "PEP_685...norm",
        ),
        _packaging_case(
            "case:packaging-pep685-normalized-input", BenchmarkLabel.AMBIGUOUS,
            DecisionOutcome.ABSTAIN,
            "extra == 'foo-bar'", "foo-bar",
        ),
        _packaging_case(
            "case:packaging-pep685-case-variant", BenchmarkLabel.AMBIGUOUS,
            DecisionOutcome.ABSTAIN,
            "extra == 'SECURITY'", "security",
        ),
        _packaging_case(
            "case:packaging-pep685-punct-variant", BenchmarkLabel.AMBIGUOUS,
            DecisionOutcome.ABSTAIN,
            "extra == 'Different.punctuation..is...equal'",
            "different__punctuation_is_EQUAL",
        ),
    ]
    unprovable = [
        _unprovable(
            "case:urllib3-chunked-encoding", "repo:urllib3", "urllib3/urllib3",
            "urllib3", "2.2.2", "2.2.3",
            "issue:urllib3-3053",
            "https://github.com/urllib3/urllib3/issues/3053",
            "urllib3 with version 2.0.* treats control character differently",
            "fix:urllib3-07f236ba",
            "07f236ba64a635d01498cc6ec17d471cc594a100",
            "rel:urllib3-2.2.3", "2.2.3",
        ),
        _unprovable(
            "case:urllib3-read-chunked", "repo:urllib3", "urllib3/urllib3",
            "urllib3", "2.6.1", "2.6.2",
            "issue:urllib3-3734",
            "https://github.com/urllib3/urllib3/issues/3734",
            "read_chunked leftover data with compressed chunked responses",
            "fix:urllib3-571a9b7b",
            "571a9b7b894cee5733c7c2cf72fa260cf1f4b660",
            "rel:urllib3-2.6.2", "2.6.2",
        ),
        _unprovable(
            "case:anyio-capacity-inf", "repo:anyio", "agronholm/anyio",
            "anyio", "4.14.1", "4.14.2",
            "issue:anyio-1189",
            "https://github.com/agronholm/anyio/issues/1189",
            "Fix CapacityLimiter(math.inf) raising TypeError outside an event loop",
            "fix:anyio-26ab19ba",
            "26ab19baf7dc5f7ce39cbcd6ce2d1058fc6d2796",
            "rel:anyio-4.14.2", "4.14.2",
        ),
        _unprovable(
            "case:packaging-prefix-zero", "repo:packaging", "pypa/packaging",
            "packaging", "23.0", "23.1",
            "issue:packaging-674",
            "https://github.com/pypa/packaging/issues/674",
            "Handle prefix match with zeros at end of prefix correctly",
            "fix:packaging-a6c9bc4d",
            "a6c9bc4dce968f7bfc05e4a93137f65ce4564be9",
            "rel:packaging-23.1", "23.1",
        ),
        _unprovable(
            "case:packaging-epoch-specifier", "repo:packaging", "pypa/packaging",
            "packaging", "23.2", "24.0",
            "issue:packaging-712",
            "https://github.com/pypa/packaging/issues/712",
            "Fix specifier matching when it is long and has an epoch",
            "fix:packaging-c52d2b30",
            "c52d2b30465ace6d11f54c01b6ea30419a94b5ef",
            "rel:packaging-24.0", "24.0",
        ),
    ]
    for case in [*measured, *unprovable]:
        dataset = dataset.add_case(case)
    return dataset


__all__ = ["build_v1"]
