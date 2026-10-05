"""PyPI adapter: deterministic package metadata and version lookup."""

from pypi.base import (
    FixturePyPIClient,
    PackageMetadata,
    PackageNotFoundError,
    PyPIClient,
    ReleaseMetadata,
    normalize_name,
    sort_versions,
)

__all__ = [
    "FixturePyPIClient",
    "PackageMetadata",
    "PackageNotFoundError",
    "PyPIClient",
    "ReleaseMetadata",
    "normalize_name",
    "sort_versions",
]
