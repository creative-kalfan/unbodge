"""Deterministic analysis: signals, five detectors, scanner, tree-sitter probe."""

from pathlib import Path

from analysis.detectors import (
    CompatibilityBranchDetector,
    DetectorFinding,
    ExceptionWorkaroundDetector,
    MonkeyPatchDetector,
    UpstreamReferenceDetector,
    VersionCheckDetector,
    run_detectors,
)
from analysis.scanner import scan_tree, to_candidate
from analysis.signals import extract_signals
from analysis.treesitter import active_backend_name, is_available

SAMPLES = Path(__file__).parent / "fixtures" / "detector_samples"


def _signals(name: str):
    source = (SAMPLES / name).read_text(encoding="utf-8")
    signals, parsed = extract_signals(source, name)
    assert parsed, f"{name} should parse"
    import ast

    return signals, ast.parse(source)


def _detectors_for(name: str) -> set[str]:
    signals, tree = _signals(name)
    return {f.detector for f in run_detectors(name, signals, tree)}


def test_each_sample_fires_its_detector():
    assert _detectors_for("version_check.py") == {"VersionCheckDetector"}
    assert _detectors_for("monkeypatch.py") == {"MonkeyPatchDetector"}
    assert _detectors_for("compat_branch.py") == {"CompatibilityBranchDetector"}
    assert _detectors_for("exception_workaround.py") == {"ExceptionWorkaroundDetector"}
    assert _detectors_for("upstream_ref.py") == {
        "ExceptionWorkaroundDetector",
        "UpstreamReferenceDetector",
    }


def test_clean_sample_fires_nothing():
    assert _detectors_for("clean.py") == set()


def test_unparseable_source_still_yields_line_signals():
    signals, parsed = extract_signals("# TODO fix this\ndef broken(:\n", "broken.py")
    assert parsed is False
    assert any(s.kind == "todo" for s in signals)


def test_individual_detectors_reject_empty_signals():
    import ast

    tree = ast.parse("x = 1\n")
    for detector in (
        VersionCheckDetector(),
        MonkeyPatchDetector(),
        CompatibilityBranchDetector(),
        ExceptionWorkaroundDetector(),
        UpstreamReferenceDetector(),
    ):
        assert detector.detect("f.py", [], tree) == []


def test_exception_detector_requires_pairing():
    import ast

    src = "try:\n    risky()\nexcept ValueError:\n    fallback()\n"
    signals, _ = extract_signals(src, "f.py")
    kinds = {s.kind for s in signals}
    assert "exception_fallback" in kinds
    assert ExceptionWorkaroundDetector().detect("f.py", signals, ast.parse(src)) == []


def test_distant_signals_form_separate_findings():
    from analysis.signals import Signal

    near = [
        Signal("exception_fallback", "f.py", 10, "except KeyError"),
        Signal("workaround_keyword", "f.py", 12, "workaround for bug"),
    ]
    assert len(ExceptionWorkaroundDetector().detect("f.py", near, None)) == 1
    far = [
        Signal("exception_fallback", "f.py", 10, "except KeyError"),
        Signal("workaround_keyword", "f.py", 500, "workaround elsewhere"),
    ]
    assert ExceptionWorkaroundDetector().detect("f.py", far, None) == []
    two_pairs = [
        Signal("exception_fallback", "f.py", 10, "except A"),
        Signal("workaround_keyword", "f.py", 12, "workaround one"),
        Signal("exception_fallback", "f.py", 500, "except B"),
        Signal("todo", "f.py", 502, "TODO two"),
    ]
    assert len(ExceptionWorkaroundDetector().detect("f.py", two_pairs, None)) == 2


def test_scanner_maps_samples_to_candidates():
    candidates = scan_tree(SAMPLES, "repo:downstream")
    by_detector = {c.detector for c in candidates}
    assert {
        "VersionCheckDetector",
        "MonkeyPatchDetector",
        "CompatibilityBranchDetector",
        "ExceptionWorkaroundDetector",
        "UpstreamReferenceDetector",
    } <= by_detector
    workaround = [c for c in candidates if c.detector == "ExceptionWorkaroundDetector"]
    assert workaround and all(c.file_path.endswith(".py") for c in workaround)
    assert workaround[0].start_line >= 1
    again = scan_tree(SAMPLES, "repo:downstream")
    assert [c.id for c in again] == [c.id for c in candidates]


def test_scanner_bounds_and_errors(tmp_path):
    assert scan_tree(tmp_path, "repo:x", max_files=0) == []
    (tmp_path / "notes.txt").write_text("TODO workaround\n")
    assert scan_tree(tmp_path, "repo:x") == []
    try:
        scan_tree(tmp_path / "missing", "repo:x")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for missing root")


def test_to_candidate_deterministic_id():
    candidates = scan_tree(SAMPLES, "repo:downstream")
    first = to_candidate(
        DetectorFinding(
            detector="ExceptionWorkaroundDetector",
            file="exception_workaround.py",
            start_line=5,
            end_line=9,
            description="d",
            signals=("exception_fallback",),
        ),
        "repo:downstream",
    )
    assert first.id.startswith("cand-")
    assert any(c.file_path == "exception_workaround.py" for c in candidates)


def test_treesitter_probe_documents_ast_backend():
    assert is_available() is False
    assert active_backend_name() == "ast"
