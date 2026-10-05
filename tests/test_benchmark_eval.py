"""Benchmark schema + human-evaluation interfaces (optional-only backends)."""

import json

import pytest
from pydantic import ValidationError

from benchmark import (
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
from evaluation import (
    EvaluationNotEnabledError,
    HumanJudgment,
    ReviewPacket,
    TendemAdapter,
    TolokaAdapter,
)


def _case(case_id="case:packaging-pep685", label=BenchmarkLabel.OBSOLETE):
    return BenchmarkCase(
        id=case_id,
        repository=BenchmarkRepository(id="repo:pip", full_name="pypa/pip"),
        dependency=BenchmarkDependency(name="packaging", old_version="21.3", new_version="22.0"),
        upstream=BenchmarkUpstream(
            issue_id="issue:545", issue_url="https://github.com/pypa/packaging/issues/545",
            fix_commit_id="fix:53dbb25", fix_commit_sha="53dbb257" + "0" * 32,
            release_id="rel:22.0", release_tag="22.0",
        ),
        workaround=BenchmarkWorkaround(
            candidate_id="cand:1", file_path="src/pip/_internal/req/req_install.py",
            description="safe_extra/canonicalize_name fallbacks",
        ),
        history=BenchmarkHistory(old_sha="a" * 40, new_sha="b" * 40),
        expected_outcome=DecisionOutcome.PROPOSE_REMOVAL,
        evidence_refs=["ev:1"],
        label=label,
        provenance=BenchmarkProvenance(
            sources=["https://github.com/pypa/packaging/pull/545"],
            method="hand-verified",
        ),
    )


def test_benchmark_schema_round_trips():
    case = _case()
    assert case.label == BenchmarkLabel.OBSOLETE
    assert case.expected_outcome == DecisionOutcome.PROPOSE_REMOVAL
    restored = BenchmarkCase.model_validate_json(case.model_dump_json())
    assert restored == case
    assert json.loads(case.model_dump_json())["provenance"]["method"] == "hand-verified"


def test_dataset_rejects_duplicates_and_bad_labels():
    dataset = BenchmarkDataset().add_case(_case())
    assert dataset.name == "unbodge-history-v1"
    assert len(dataset.cases) == 1
    with pytest.raises(ValueError):
        dataset.add_case(_case())
    with pytest.raises(ValidationError):
        BenchmarkCase(
            id="x",
            repository=BenchmarkRepository(id="r", full_name="a/b"),
            dependency=BenchmarkDependency(name="d", old_version="1", new_version="2"),
            upstream=BenchmarkUpstream(
                issue_id="i", fix_commit_id="f", fix_commit_sha="c" * 40,
                release_id="r", release_tag="t",
            ),
            workaround=BenchmarkWorkaround(candidate_id="c", file_path="f.py"),
            label="MADE_UP",
        )


def test_all_four_labels_exist():
    assert {label.value for label in BenchmarkLabel} == {
        "OBSOLETE", "NOT_OBSOLETE", "AMBIGUOUS", "UNPROVABLE",
    }


def test_human_judgment_and_review_packet():
    judgment = HumanJudgment(case_id="case:1", reviewer="alice", label=BenchmarkLabel.OBSOLETE)
    assert judgment.label == BenchmarkLabel.OBSOLETE
    packet = ReviewPacket(
        case_id="case:1", hypothesis_claim="c", matrix={"A": "PASS"},
        regression="PASS", evidence_ids=["ev:1"],
        upstream_refs=["https://github.com/pypa/packaging/issues/545"],
    )
    assert "model verdict" not in packet.model_dump_json().lower()
    assert set(ReviewPacket.model_fields) == {
        "case_id", "hypothesis_claim", "matrix", "regression",
        "evidence_ids", "upstream_refs",
    }
    assert packet.matrix == {"A": "PASS"}


def test_toloka_tendem_disabled_by_default():
    assert not TolokaAdapter().enabled
    assert not TendemAdapter().enabled
    with pytest.raises(EvaluationNotEnabledError):
        TolokaAdapter().submit(ReviewPacket(case_id="c"))
    with pytest.raises(EvaluationNotEnabledError):
        TendemAdapter().escalate(ReviewPacket(case_id="c"), reason="abstained")
    with pytest.raises(EvaluationNotEnabledError):
        TolokaAdapter(enabled=False).submit(ReviewPacket(case_id="c"))


def test_enabled_adapters_report_missing_transport():
    with pytest.raises(NotImplementedError):
        TolokaAdapter(enabled=True).submit(ReviewPacket(case_id="c"))
    with pytest.raises(NotImplementedError):
        TendemAdapter(enabled=True).escalate(ReviewPacket(case_id="c"))
