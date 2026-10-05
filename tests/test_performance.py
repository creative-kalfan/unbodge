"""Performance measurements (Phase 4): measure first, optimize never blindly.

Records wall-clock latencies for the hot paths and asserts broad sanity
bounds (not tight thresholds, to avoid flaky gates). Token cost is
structurally zero: no test invokes a metered model or search endpoint.
"""

import time

import pytest
from fastapi.testclient import TestClient

from api import create_app
from evidence.hashing import sha256_hex
from evidence.items import make_evidence
from domain.enums import EvidenceType
from persistence import MemoryStore
from sandbox.docker import docker_available
from tracing import LocalTracer


def _ms(fn, *args, **kwargs):
    started = time.perf_counter()
    result = fn(*args, **kwargs)
    return result, (time.perf_counter() - started) * 1000.0


def test_evidence_hashing_throughput():
    _, ms = _ms(lambda: [sha256_hex(f"payload-{i}") for i in range(1000)])
    assert ms < 5000, f"hashing 1000 items took {ms:.1f}ms"
    print(f"\n[perf] evidence hashing: {ms / 1000:.3f} ms/item")


def test_evidence_validation_latency():
    items = [
        make_evidence(
            id=f"ev:{i}", evidence_type=EvidenceType.CODE_REFERENCE,
            source="s", claim=f"claim {i}",
        )
        for i in range(50)
    ]
    from evidence.validation import validate_item

    _, ms = _ms(lambda: [validate_item(item) for item in items])
    assert ms < 5000, f"validating 50 items took {ms:.1f}ms"
    print(f"\n[perf] evidence validation: {ms / 50:.3f} ms/item")


def test_api_latency():
    client = TestClient(create_app(store=MemoryStore()))
    _, health_ms = _ms(client.get, "/health")
    _, repos_ms = _ms(client.get, "/repositories")
    assert health_ms < 2000 and repos_ms < 2000
    print(f"\n[perf] api GET /health: {health_ms:.2f}ms, /repositories: {repos_ms:.2f}ms")


def test_detector_scan_latency(tmp_path):
    from analysis.scanner import scan_tree

    target = tmp_path / "code"
    target.mkdir()
    for i in range(20):
        (target / f"mod_{i}.py").write_text(
            "import sys\n\nif sys.version_info < (3, 9):\n    X = 1\n"
            "try:\n    risky()\nexcept ValueError:\n    pass  # TODO fix\n"
        )
    _, ms = _ms(scan_tree, target, "repo:perf")
    assert ms < 10000
    print(f"\n[perf] detector scan (20 files): {ms:.1f}ms")


def test_database_round_trip_latency():
    store = MemoryStore()
    _, ms = _ms(
        lambda: [store.put("evidence", f"ev:{i}", {"id": f"ev:{i}"}) or
                 store.get("evidence", f"ev:{i}") for i in range(200)]
    )
    assert ms < 5000
    print(f"\n[perf] memory store put+get: {ms / 200:.3f} ms/op")


def test_token_cost_is_structurally_zero():
    # The offline fixture blocks live sockets/urlopen: any metered call
    # would fail the suite instead of spending credits.
    import socket
    import urllib.request

    with pytest.raises(AssertionError):
        socket.create_connection(("example.com", 80))
    with pytest.raises(AssertionError):
        urllib.request.urlopen("https://example.com")
    print("\n[perf] token cost: $0.00 (live network blocked in suite)")


def test_sandbox_startup_latency():
    if not docker_available():
        import pytest

        pytest.skip("docker unavailable")
    from sandbox.docker import DockerSandbox

    sandbox = DockerSandbox()
    _, ms = _ms(
        sandbox.run_container, {"a.py": "print(1)\n"}, ["python", "a.py"], {}
    )
    assert ms < 120000
    print(f"\n[perf] container cold start + run: {ms:.0f}ms")
