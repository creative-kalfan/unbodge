"""Deterministic signal extraction (Phase 2).

Two layers, no LLM:
1. line scan -- keywords, upstream references (works on any text, even
   unparseable files);
2. AST walk -- structural signals for parseable Python (version checks,
   retries, shims, monkey patches, compat branches, exception fallbacks).
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field

KEYWORD_PATTERNS: dict[str, re.Pattern[str]] = {
    "todo": re.compile(r"\bTODO\b", re.IGNORECASE),
    "fixme": re.compile(r"\bFIXME\b", re.IGNORECASE),
    "workaround_keyword": re.compile(r"\bwork[-_ ]?around\b", re.IGNORECASE),
    "temporary": re.compile(r"\btemporar\w*\b|\btemp fix\b|\bstopgap\b", re.IGNORECASE),
    "compat": re.compile(r"\bcompat\w*\b|\bshim\w*\b", re.IGNORECASE),
    "retry": re.compile(r"\bretries\b|\bretry\b", re.IGNORECASE),
}

UPSTREAM_REF_RE = re.compile(
    r"https?://[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+/(?:issues|pull|discussions)/\d+"
    r"|(?:^|\W)(?:upstream\s+)?issue\s*#?\d+",
    re.IGNORECASE,
)

_VERSION_CALLS = {"version", "get_distribution", "distribution", "version_info"}
_RETRY_DECORATORS = {"retry", "retries", "retrying", "backoff", "tenacity"}


@dataclass(frozen=True)
class Signal:
    kind: str
    file: str
    line: int
    text: str
    extra: tuple[tuple[str, str], ...] = field(default_factory=tuple)


def scan_lines(source: str, path: str) -> list[Signal]:
    signals: list[Signal] = []
    for lineno, line in enumerate(source.splitlines(), start=1):
        for kind, pattern in KEYWORD_PATTERNS.items():
            if pattern.search(line):
                signals.append(Signal(kind, path, lineno, line.strip()[:200]))
        if UPSTREAM_REF_RE.search(line):
            signals.append(Signal("upstream_ref", path, lineno, line.strip()[:200]))
    return signals


def _is_version_check(node: ast.AST) -> bool:
    if isinstance(node, ast.Compare):
        for child in ast.walk(node):
            if isinstance(child, ast.Attribute) and child.attr in (
                "version_info",
                "version",
                "VERSION",
            ):
                return True
            if isinstance(child, ast.Call):
                func = child.func
                name = ""
                if isinstance(func, ast.Name):
                    name = func.id
                elif isinstance(func, ast.Attribute):
                    name = func.attr
                if name in _VERSION_CALLS or "version" in name.lower():
                    return True
    return False


def _is_retry_loop(node: ast.For | ast.While) -> bool:
    """A loop whose body retries via try/except + continue."""
    for child in ast.walk(node):
        if isinstance(child, ast.Try) and child.handlers:
            for sub in ast.walk(child):
                if isinstance(sub, ast.Continue):
                    return True
    return False


def _retry_decorators(tree: ast.Module, path: str) -> list[Signal]:
    signals: list[Signal] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for decorator in node.decorator_list:
                text = ast.dump(decorator)
                if "retry" in text or "backoff" in text or "tenacity" in text:
                    signals.append(
                        Signal("retry", path, node.lineno, f"retry decorator: {text[:120]}")
                    )
    return signals


def _has_import(stmts: list[ast.stmt]) -> bool:
    return any(
        isinstance(child, (ast.Import, ast.ImportFrom))
        for stmt in stmts
        for child in ast.walk(stmt)
    )


def _has_import_fallback(node: ast.Try) -> bool:
    imports_body = _has_import(node.body)
    imports_handler = any(_has_import(handler.body) for handler in node.handlers)
    return imports_body and imports_handler


def _is_monkey_patch(node: ast.AST, imported: set[str]) -> str | None:
    target: ast.expr | None = None
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target = node.targets[0]
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
        target = node.target
    if isinstance(target, ast.Attribute):
        node_value: ast.expr = target.value
        while isinstance(node_value, ast.Attribute):
            node_value = node_value.value
        if isinstance(node_value, ast.Name) and node_value.id in imported:
            return node_value.id
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
        func = node.value.func
        if isinstance(func, ast.Name) and func.id == "setattr" and node.value.args:
            first = node.value.args[0]
            if isinstance(first, ast.Name) and first.id in imported:
                return first.id
    return None


def walk_ast(tree: ast.Module, path: str) -> list[Signal]:
    signals: list[Signal] = []
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported.add(alias.asname or alias.name.split(".")[0])
            if node.module:
                imported.add(node.module.split(".")[0])
    for node in ast.walk(tree):
        lineno = getattr(node, "lineno", 0) or 0
        if isinstance(node, ast.If) and _is_version_check(node.test):
            signals.append(Signal("version_check", path, lineno, ast.dump(node.test)[:200]))
            continue
        if isinstance(node, ast.Compare) and _is_version_check(node):
            signals.append(Signal("version_check", path, lineno, ast.dump(node)[:200]))
        elif isinstance(node, (ast.For, ast.While)) and _is_retry_loop(node):
            signals.append(Signal("retry", path, lineno, f"{type(node).__name__} with try/except"))
        elif isinstance(node, ast.Try):
            if _has_import_fallback(node):
                signals.append(Signal("shim", path, lineno, "import fallback"))
            elif node.handlers and not node.finalbody:
                handler_kinds = [
                    getattr(exc, "id", getattr(exc, "attr", "?"))
                    for handler in node.handlers
                    if handler.type is not None
                    for exc in (
                        handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
                    )
                ]
                signals.append(
                    Signal(
                        "exception_fallback",
                        path,
                        lineno,
                        f"except {','.join(handler_kinds)}",
                    )
                )
        elif isinstance(node, ast.If):
            test_src = ast.dump(node.test)
            if "version_info" in test_src or "platform" in test_src or "sys_version" in test_src:
                signals.append(Signal("compat_branch", path, lineno, ast.dump(node.test)[:200]))
        patched = _is_monkey_patch(node, imported)
        if patched is not None:
            signals.append(
                Signal("monkey_patch", path, lineno, f"attribute assigned on {patched}")
            )
    return signals


def extract_signals_with_tree(
    source: str, path: str
) -> tuple[list[Signal], bool, ast.Module | None]:
    """Return ``(signals, parsed, tree)``; unparseable/huge files skip AST."""
    line_signals = scan_lines(source, path)
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return sorted(line_signals, key=lambda s: (s.line, s.kind)), False, None
    signals = list(line_signals)
    signals.extend(walk_ast(tree, path))
    signals.extend(_retry_decorators(tree, path))
    return sorted(signals, key=lambda s: (s.line, s.kind)), True, tree


def extract_signals(source: str, path: str) -> tuple[list[Signal], bool]:
    """Return ``(signals, parsed)`` -- AST layer skipped when unparseable."""
    signals, parsed, _ = extract_signals_with_tree(source, path)
    return signals, parsed


__all__ = [
    "KEYWORD_PATTERNS",
    "UPSTREAM_REF_RE",
    "Signal",
    "extract_signals",
    "extract_signals_with_tree",
    "scan_lines",
    "walk_ast",
]
