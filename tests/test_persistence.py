"""Persistence + transient coordination: contracts always, backends when live."""

import copy

import pytest

from persistence import MemoryStore, PostgresStore, StoreError, StoreUnavailableError, check_entity


def _contract_suite(store, label: str):
    store.put("repositories", "repo:1", {"id": "repo:1", "full_name": "a/b"})
    assert store.get("repositories", "repo:1") == {"id": "repo:1", "full_name": "a/b"}
    assert store.get("repositories", "missing") is None
    store.put("repositories", "repo:1", {"id": "repo:1", "v": 2})
    assert store.get("repositories", "repo:1")["v"] == 2
    assert len(store.list("repositories")) == 1
    assert store.delete("repositories", "repo:1") is True
    assert store.delete("repositories", "repo:1") is False
    with pytest.raises(StoreError):
        store.put("nope", "x", {})
    with pytest.raises(StoreError):
        store.get("nope", "x")
    with pytest.raises(ValueError):
        store.put("repositories", "", {})
    with pytest.raises(ValueError):
        store.list("repositories", limit=0)
    assert label in ("memory", "postgres")


def test_memory_store_contract():
    _contract_suite(MemoryStore(), "memory")


def test_memory_store_isolated_copies():
    store = MemoryStore()
    record = {"nested": {"a": [1]}}
    store.put("evidence", "ev:1", record)
    record["nested"]["a"].append(999)
    assert store.get("evidence", "ev:1") == {"nested": {"a": [1]}}
    listed = store.list("evidence")
    listed[0]["nested"]["a"].append(999)
    assert store.get("evidence", "ev:1") == {"nested": {"a": [1]}}


def _postgres_dsn() -> str | None:
    import os

    return os.environ.get("UNBODGE_TEST_POSTGRES_DSN")


def test_postgres_store_contract_or_skip():
    dsn = _postgres_dsn()
    if not dsn:
        pytest.skip("UNBODGE_TEST_POSTGRES_DSN not set")
    try:
        store = PostgresStore(dsn)
    except StoreUnavailableError as exc:
        pytest.skip(f"postgres unavailable: {exc}")
    try:
        _contract_suite(store, "postgres")
    finally:
        store.close()


def test_postgres_bad_dsn_fails_closed():
    with pytest.raises(StoreUnavailableError):
        PostgresStore("dbname=unbodge_nope_xyz host=127.0.0.1 port=1 connect_timeout=2")


def test_check_entity_lists_all_phase4_tables():
    from persistence import ENTITIES

    assert set(ENTITIES) >= {
        "repositories", "upstream_events", "issues", "fixes", "releases",
        "workaround_candidates", "causal_hypotheses", "reproduction_plans",
        "experiments", "experiment_runs", "evidence", "evidence_links",
        "regression_results", "decisions", "pr_results", "human_reviews",
        "benchmark_cases",
    }
