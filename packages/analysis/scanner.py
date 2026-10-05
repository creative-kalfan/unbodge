"""Repository scanner (Phase 2)."""

from __future__ import annotations

from pathlib import Path

from analysis.detectors import DEFAULT_DETECTORS, Detector, DetectorFinding, run_detectors
from analysis.signals import extract_signals_with_tree
from domain.models import WorkaroundCandidate

MAX_FILES = 1000
MAX_FILE_BYTES = 1_000_000
MAX_VISITED_ENTRIES = 50000
SKIP_DIRS = frozenset({".git", "__pycache__", ".venv", "venv", "node_modules", ".hg"})


def _excluded(rel: str, prefixes: tuple[str, ...]) -> bool:
    for prefix in prefixes:
        clean = prefix.rstrip("/")
        if not clean:
            continue
        if rel == clean or rel.startswith(clean + "/"):
            return True
    return False


def scan_tree(
    root: str | Path,
    repository_id: str,
    detectors: tuple[Detector, ...] = DEFAULT_DETECTORS,
    *,
    max_files: int = MAX_FILES,
    exclude_prefixes: tuple[str, ...] = (),
) -> list[WorkaroundCandidate]:
    base = Path(root)
    if not base.is_dir():
        raise ValueError(f"scan root is not a directory: {root}")
    findings: list[DetectorFinding] = []
    count = 0
    visited = 0
    for path in sorted(base.rglob("*.py")):
        if count >= max_files or visited >= MAX_VISITED_ENTRIES:
            break
        visited += 1
        if path.is_symlink():
            continue
        rel = path.relative_to(base).as_posix()
        if _excluded(rel, exclude_prefixes):
            continue
        if any(part in SKIP_DIRS or part.startswith(".") for part in Path(rel).parts):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
            source = path.read_text(encoding="utf-8")
            if len(source.encode("utf-8")) > MAX_FILE_BYTES:
                continue
        except (OSError, UnicodeDecodeError):
            continue
        count += 1
        signals, _, tree = extract_signals_with_tree(source, rel)
        findings.extend(run_detectors(rel, signals, tree, detectors))
    candidates = [to_candidate(f, repository_id) for f in findings]
    candidates.sort(key=lambda c: (c.file_path, c.start_line, c.detector))
    return candidates


def to_candidate(finding: DetectorFinding, repository_id: str) -> WorkaroundCandidate:
    snippet = " // ".join(finding.excerpts) or "; ".join(finding.signals)
    return WorkaroundCandidate(
        id=finding.candidate_id(repository_id),
        repository_id=repository_id,
        file_path=finding.file,
        start_line=finding.start_line,
        end_line=finding.end_line,
        description=f"{finding.description}: {snippet[:1500]}",
        detector=finding.detector,
    )


__all__ = [
    "MAX_FILE_BYTES",
    "MAX_FILES",
    "MAX_VISITED_ENTRIES",
    "SKIP_DIRS",
    "scan_tree",
    "to_candidate",
]
