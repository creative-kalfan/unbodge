"""Dependency pin parsing (Phase 2).

Reads dependency declarations as they appear at a historical revision:
``requirements*.txt`` (``pkg==ver`` pins), ``pyproject.toml``
(PEP 508 ``[project] dependencies``), and ``setup.cfg``. Only exact
``==`` pins are reproducible pins; ranges are recorded as constraints.
"""

from __future__ import annotations

import re
import tomllib
from configparser import ConfigParser, Error as ConfigError
from dataclasses import dataclass, field

from pypi.base import normalize_name

_PIN_RE = re.compile(r"^\s*([A-Za-z0-9_.\-]+)\s*==\s*([^\s;#]+)\s*(?:[#;].*)?$")
_REQ_LIKE_RE = re.compile(
    r"^[A-Za-z0-9_.\-]+(\[[^\]]*\])?\s*(==|>=|<=|~=|!=|>|<|===|;|$)"
)


@dataclass(frozen=True)
class DependencyPin:
    package: str
    version: str
    source_file: str


@dataclass(frozen=True)
class ParsedRequirements:
    pins: tuple[DependencyPin, ...] = ()
    constraints: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()


def parse_requirements_text(text: str, source_file: str) -> ParsedRequirements:
    pins: list[DependencyPin] = []
    constraints: list[str] = []
    skipped: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("-"):
            if stripped.startswith("-"):
                skipped.append(stripped)
            continue
        base = re.sub(r"\[[^\]]*\]", "", stripped)
        match = _PIN_RE.match(base)
        if match:
            pins.append(
                DependencyPin(
                    normalize_name(match.group(1)), match.group(2), source_file
                )
            )
        elif _REQ_LIKE_RE.match(base):
            constraints.append(stripped)
        else:
            skipped.append(stripped)
    return ParsedRequirements(tuple(pins), tuple(constraints), tuple(skipped))


def parse_pyproject_dependencies(data: bytes, source_file: str) -> ParsedRequirements:
    try:
        parsed = tomllib.loads(data.decode("utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError, ValueError):
        return ParsedRequirements(skipped=(source_file,))
    project = parsed.get("project")
    if not isinstance(project, dict):
        return ParsedRequirements()
    deps = project.get("dependencies", [])
    if not isinstance(deps, list):
        return ParsedRequirements(skipped=(source_file,))
    text = "\n".join(str(dep) for dep in deps)
    return parse_requirements_text(text, source_file)


def parse_setup_cfg(data: bytes, source_file: str) -> ParsedRequirements:
    parser = ConfigParser()
    try:
        parser.read_string(data.decode("utf-8"))
    except (UnicodeDecodeError, ConfigError, ValueError):
        return ParsedRequirements(skipped=(source_file,))
    if not parser.has_section("options") or not parser.has_option("options", "install_requires"):
        return ParsedRequirements()
    raw = parser.get("options", "install_requires")
    return parse_requirements_text(raw, source_file)


__all__ = [
    "DependencyPin",
    "ParsedRequirements",
    "parse_pyproject_dependencies",
    "parse_requirements_text",
    "parse_setup_cfg",
]
