"""Deterministic Python AST analysis + workaround detectors (Phase 2)."""

from analysis.detectors import (
    DEFAULT_DETECTORS,
    WORKAROUND_CONTEXT,
    CompatibilityBranchDetector,
    Detector,
    DetectorFinding,
    ExceptionWorkaroundDetector,
    MonkeyPatchDetector,
    UpstreamReferenceDetector,
    VersionCheckDetector,
    run_detectors,
)
from analysis.scanner import (
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_VISITED_ENTRIES,
    SKIP_DIRS,
    scan_tree,
    to_candidate,
)
from analysis.signals import KEYWORD_PATTERNS, UPSTREAM_REF_RE, Signal, extract_signals
from analysis.treesitter import TreeSitterBackend, active_backend_name, is_available

__all__ = [
    "DEFAULT_DETECTORS",
    "KEYWORD_PATTERNS",
    "MAX_FILE_BYTES",
    "MAX_FILES",
    "MAX_VISITED_ENTRIES",
    "SKIP_DIRS",
    "UPSTREAM_REF_RE",
    "WORKAROUND_CONTEXT",
    "CompatibilityBranchDetector",
    "Detector",
    "DetectorFinding",
    "ExceptionWorkaroundDetector",
    "MonkeyPatchDetector",
    "Signal",
    "TreeSitterBackend",
    "UpstreamReferenceDetector",
    "VersionCheckDetector",
    "active_backend_name",
    "extract_signals",
    "is_available",
    "run_detectors",
    "scan_tree",
    "to_candidate",
]
