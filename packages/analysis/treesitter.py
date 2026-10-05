"""Tree-sitter integration point (Phase 2).

Justification (``where justified``): the bundled ``tree-sitter`` package
is not installed in this offline environment, and Python's stdlib ``ast``
fully covers the Phase 2 Python-only detector surface. Rather than vendor
a half-working binding, this module defines the backend protocol detectors
will consume, plus an availability probe. When ``tree_sitter`` and a Python
grammar become available, implement ``TreeSitterBackend`` here and pass it
to the detectors -- no detector logic changes required.
"""

from __future__ import annotations

from typing import Protocol


class TreeSitterBackend(Protocol):
    """Structural parsing backend for future multi-language detectors."""

    language: str

    def parse(self, source: str) -> object:
        """Parse source into an opaque syntax tree."""
        ...

    def find_nodes(self, tree: object, query: str) -> list[tuple[int, int, str]]:
        """Return ``(start_line, end_line, text)`` for a query dialect."""
        ...


def is_available() -> bool:
    """True iff an installed ``tree_sitter`` package can be imported."""
    try:
        import tree_sitter  # noqa: F401
    except ImportError:
        return False
    return True


def active_backend_name() -> str:
    """Name of the backend detectors actually use in this environment."""
    return "tree-sitter" if is_available() else "ast"


__all__ = ["TreeSitterBackend", "active_backend_name", "is_available"]
