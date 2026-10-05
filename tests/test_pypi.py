"""PyPI adapter: deterministic metadata, versions, releases."""

import pytest

from pypi.base import (
    FixturePyPIClient,
    PackageNotFoundError,
    ReleaseMetadata,
    sort_versions,
)


def _index() -> FixturePyPIClient:
    return FixturePyPIClient(
        {
            "fake-dep": {
                "1.0": ReleaseMetadata(name="fake-dep", version="1.0"),
                "1.1": ReleaseMetadata(name="fake-dep", version="1.1"),
                "2.0rc1": ReleaseMetadata(name="fake-dep", version="2.0rc1"),
            }
        }
    )


def test_versions_sorted_deterministically():
    assert sort_versions(["2.0rc1", "1.1", "1.0"]) == ["1.0", "1.1", "2.0rc1"]
    assert sort_versions(["1.0", "1.0"]) == ["1.0", "1.0"]
    assert _index().list_versions("fake-dep") == ["1.0", "1.1", "2.0rc1"]


def test_name_normalization():
    assert _index().list_versions("Fake_Dep") == ["1.0", "1.1", "2.0rc1"]


def test_package_and_release_metadata():
    client = _index()
    package = client.get_package("fake-dep")
    assert package.latest_version == "2.0rc1"
    assert package.versions == ["1.0", "1.1", "2.0rc1"]
    release = client.get_release("fake-dep", "1.1")
    assert release.version == "1.1" and release.yanked is False
    assert client.latest_version("fake-dep") == "2.0rc1"


def test_unknown_package_and_release_raise():
    client = _index()
    with pytest.raises(PackageNotFoundError):
        client.get_package("nonexistent-pkg")
    with pytest.raises(PackageNotFoundError):
        client.get_release("fake-dep", "9.9")
    with pytest.raises(PackageNotFoundError):
        client.latest_version("empty-pkg")
    empty = FixturePyPIClient({"empty-pkg": {}})
    with pytest.raises(PackageNotFoundError):
        empty.latest_version("empty-pkg")
    with pytest.raises(PackageNotFoundError):
        empty.get_package("empty-pkg")
