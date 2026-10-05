"""Workaround detectors (Phase 2).

Each detector consumes extracted signals (plus the AST for structural
confirmation) and returns structured findings -- evidence inputs, never
truth. No LLM involved. Pairing rules are documented per detector.
"""

from __future__ import annotations

import ast
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from analysis.signals import Signal

#: Signal kinds that mark workaround-ish context for pairing rules.
WORKAROUND_CONTEXT = frozenset(
    {"workaround_keyword", "temporary", "todo", "fixme", "upstream_ref", "compat"}
)


@dataclass(frozen=True)
class DetectorFinding:
    detector: str
    file: str
    start_line: int
    end_line: int
    description: str
    signals: tuple[str, ...] = field(default_factory=tuple)
    excerpts: tuple[str, ...] = field(default_factory=tuple)

    def candidate_id(self, repository_id: str) -> str:
        digest = hashlib.sha256(
            f"{repository_id}:{self.file}:{self.start_line}:{self.end_line}:{self.detector}".encode()
        ).hexdigest()[:12]
        return f"cand-{digest}"


class Detector(ABC):
    name: str = "BaseDetector"

    @abstractmethod
    def detect(
        self, path: str, signals: list[Signal], tree: ast.Module | None
    ) -> list[DetectorFinding]: ...

    def _paired(
        self,
        path: str,
        signals: list[Signal],
        required: set[str],
        context: set[str],
        description: str,
    ) -> list[DetectorFinding]:
        """One finding per line-cluster containing both a required signal
        and a context signal (no cross-file-distance pairing)."""
        wanted = required | context
        lines = sorted(s.line for s in signals if s.kind in wanted)
        findings: list[DetectorFinding] = []
        for start, end in _clusters(lines):
            kinds = {s.kind for s in signals if s.kind in wanted and start <= s.line <= end}
            if not (kinds & required and kinds & context):
                continue
            excerpts = tuple(
                dict.fromkeys(
                    s.text for s in signals if s.kind in wanted and start <= s.line <= end
                )
            )[:5]
            findings.append(
                DetectorFinding(
                    detector=self.name,
                    file=path,
                    start_line=start,
                    end_line=end,
                    description=description,
                    signals=tuple(sorted(kinds)),
                    excerpts=excerpts,
                )
            )
        return findings

    def _grouped(
        self, path: str, signals: list[Signal], kinds: set[str], description: str
    ) -> list[DetectorFinding]:
        return [
            DetectorFinding(
                detector=self.name,
                file=path,
                start_line=cluster[0],
                end_line=cluster[1],
                description=description,
                signals=tuple(sorted(kinds & {s.kind for s in signals})),
                excerpts=tuple(
                    dict.fromkeys(s.text for s in signals if s.kind in kinds)
                )[:5],
            )
            for cluster in _clusters(
                sorted(s.line for s in signals if s.kind in kinds)
            )
        ]


CLUSTER_GAP_LINES = 40


def _clusters(lines: list[int]) -> list[tuple[int, int]]:
    """Group sorted line numbers into clusters split by large gaps."""
    clusters: list[tuple[int, int]] = []
    start = prev = None
    for line in lines:
        if start is None:
            start = prev = line
        elif line - prev > CLUSTER_GAP_LINES:
            clusters.append((max(1, start), max(prev, start)))
            start = prev = line
        else:
            prev = line
    if start is not None and prev is not None:
        clusters.append((max(1, start), max(prev, start)))
    return clusters


class VersionCheckDetector(Detector):
    """Dependency/library version comparisons (``sys.version_info``,
    ``importlib.metadata.version(...)``, ``*.VERSION`` ...)."""

    name = "VersionCheckDetector"

    def detect(self, path, signals, tree):
        return self._grouped(
            path, signals, {"version_check"}, "dependency/library version check"
        )


class MonkeyPatchDetector(Detector):
    """Attribute assignment / ``setattr`` on an imported module object."""

    name = "MonkeyPatchDetector"

    def detect(self, path, signals, tree):
        return self._grouped(
            path, signals, {"monkey_patch"}, "monkey patch on imported module"
        )


class CompatibilityBranchDetector(Detector):
    """Platform/interpreter branches (``sys.version_info`` in ``if``,
    ``platform.*`` conditions) plus compat/shim keywords."""

    name = "CompatibilityBranchDetector"

    def detect(self, path, signals, tree):
        kinds = {"compat_branch"}
        if any(s.kind == "compat" for s in signals):
            kinds.add("compat")
        findings = self._grouped(
            path, signals, kinds, "compatibility branch for platform/version"
        )
        return [f for f in findings if "compat_branch" in f.signals]


class ExceptionWorkaroundDetector(Detector):
    """``try/except`` fallback paired with workaround context
    (workaround keyword, temporary, TODO/FIXME, upstream ref, compat)."""

    name = "ExceptionWorkaroundDetector"

    def detect(self, path, signals, tree):
        return self._paired(
            path,
            signals,
            {"exception_fallback"},
            set(WORKAROUND_CONTEXT),
            "exception fallback compensating for an upstream problem",
        )


class UpstreamReferenceDetector(Detector):
    """Upstream issue/PR reference paired with workaround context."""

    name = "UpstreamReferenceDetector"

    def detect(self, path, signals, tree):
        return self._paired(
            path,
            signals,
            {"upstream_ref"},
            (set(WORKAROUND_CONTEXT) - {"upstream_ref"}) | {"exception_fallback"},
            "code references an upstream issue in a workaround context",
        )


DEFAULT_DETECTORS: tuple[Detector, ...] = (
    VersionCheckDetector(),
    MonkeyPatchDetector(),
    CompatibilityBranchDetector(),
    ExceptionWorkaroundDetector(),
    UpstreamReferenceDetector(),
)


def run_detectors(
    path: str,
    signals: list[Signal],
    tree: ast.Module | None,
    detectors: tuple[Detector, ...] = DEFAULT_DETECTORS,
) -> list[DetectorFinding]:
    findings: list[DetectorFinding] = []
    for detector in detectors:
        findings.extend(detector.detect(path, signals, tree))
    findings.sort(key=lambda f: (f.file, f.start_line, f.detector))
    return findings


__all__ = [
    "DEFAULT_DETECTORS",
    "WORKAROUND_CONTEXT",
    "CompatibilityBranchDetector",
    "Detector",
    "DetectorFinding",
    "ExceptionWorkaroundDetector",
    "MonkeyPatchDetector",
    "UpstreamReferenceDetector",
    "VersionCheckDetector",
    "run_detectors",
]
