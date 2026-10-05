"""PyPI package metadata adapter (Phase 2).

``PyPIClient`` answers package metadata, available versions, release
metadata, and latest release with deterministic version ordering
(``packaging.version``). The fixture implementation serves controlled
offline indexes; a JSON-API transport can implement the same ABC later.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from domain.errors import UnbodgeError
from domain.models import UnbodgeModel, utcnow
from packaging.version import InvalidVersion, Version
from pydantic import Field
from datetime import datetime


class PackageNotFoundError(UnbodgeError):
    """The package (or release) is not known to the index."""


class PackageMetadata(UnbodgeModel):
    name: str = Field(min_length=1)
    latest_version: str = Field(min_length=1)
    summary: str = ""
    home_page: str = ""
    versions: list[str] = Field(default_factory=list)


class ReleaseMetadata(UnbodgeModel):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)
    upload_time: datetime = Field(default_factory=utcnow)
    yanked: bool = False
    requires_python: str = ""


def sort_versions(versions: list[str]) -> list[str]:
    """Deterministic PEP 440 ordering; invalid versions sort last, lexically."""

    def key(value: str) -> tuple[int, object, str]:
        try:
            return (0, Version(value), "")
        except InvalidVersion:
            return (1, value, value)

    return sorted(versions, key=key)


class PyPIClient(ABC):
    """Stable package-index interface."""

    @abstractmethod
    def get_package(self, name: str) -> PackageMetadata: ...
    @abstractmethod
    def list_versions(self, name: str) -> list[str]: ...
    @abstractmethod
    def get_release(self, name: str, version: str) -> ReleaseMetadata: ...
    @abstractmethod
    def latest_version(self, name: str) -> str: ...


class FixturePyPIClient(PyPIClient):
    """In-memory index: ``{normalized_name: {version: ReleaseMetadata}}``."""

    def __init__(self, index: dict[str, dict[str, ReleaseMetadata]] | None = None) -> None:
        normalized: dict[str, dict[str, ReleaseMetadata]] = {}
        for name, releases in (index or {}).items():
            normalized[_normalize(name)] = dict(releases)
        self._index = normalized

    def _releases(self, name: str) -> dict[str, ReleaseMetadata]:
        try:
            return self._index[_normalize(name)]
        except KeyError:
            raise PackageNotFoundError(f"package not in index: {name!r}") from None

    def get_package(self, name: str) -> PackageMetadata:
        releases = self._releases(name)
        versions = sort_versions(list(releases))
        if not versions:
            raise PackageNotFoundError(f"package has no releases: {name!r}")
        return PackageMetadata(
            name=name,
            latest_version=versions[-1],
            summary="",
            versions=versions,
        )

    def list_versions(self, name: str) -> list[str]:
        return sort_versions(list(self._releases(name)))

    def get_release(self, name: str, version: str) -> ReleaseMetadata:
        releases = self._releases(name)
        try:
            return releases[version]
        except KeyError:
            raise PackageNotFoundError(f"release not in index: {name!r}=={version!r}") from None

    def latest_version(self, name: str) -> str:
        versions = self.list_versions(name)
        if not versions:
            raise PackageNotFoundError(f"package has no releases: {name!r}")
        return versions[-1]


def _normalize(name: str) -> str:
    return normalize_name(name)


def normalize_name(name: str) -> str:
    """PEP 503 normalization shared by the index and lock readers."""
    return re.sub(r"[-_.]+", "-", name.strip().lower())


__all__ = [
    "FixturePyPIClient",
    "PackageMetadata",
    "PackageNotFoundError",
    "PyPIClient",
    "ReleaseMetadata",
    "normalize_name",
    "sort_versions",
]
