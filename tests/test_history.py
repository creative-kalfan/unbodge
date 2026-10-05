"""Historical reconstruction against a controlled fixture repository."""

import pytest

from github.git import GitRepo
from history.pins import (
    parse_pyproject_dependencies,
    parse_requirements_text,
    parse_setup_cfg,
)
from history.reconstruction import Reconstructor
from history.states import HistoryError
from phase2_support import build_downstream_fixture, init_repo, write
from pypi.base import FixturePyPIClient, ReleaseMetadata


def _pypi():
    return FixturePyPIClient(
        {
            "fake-dep": {
                "1.0": ReleaseMetadata(name="fake-dep", version="1.0"),
                "1.1": ReleaseMetadata(name="fake-dep", version="1.1"),
            }
        }
    )


def test_pin_parsers():
    parsed = parse_requirements_text(
        "# comment\nfake-dep==1.0  # pinned\nloose>=2\n-r other.txt\n", "requirements.txt"
    )
    assert [(p.package, p.version) for p in parsed.pins] == [("fake-dep", "1.0")]
    assert parsed.constraints == ("loose>=2",)
    assert parsed.skipped == ("-r other.txt",)

    pyproject = parse_pyproject_dependencies(
        b'[project]\nname = "x"\ndependencies = ["fake-dep==1.1", "any Tableau"]\n',
        "pyproject.toml",
    )
    assert [(p.package, p.version) for p in pyproject.pins] == [("fake-dep", "1.1")]
    assert parse_pyproject_dependencies(b"not toml [[[", "pyproject.toml").skipped

    cfg = parse_setup_cfg(
        b"[options]\ninstall_requires =\n    fake-dep==1.0\n", "setup.cfg"
    )
    assert [(p.package, p.version) for p in cfg.pins] == [("fake-dep", "1.0")]
    assert parse_setup_cfg(b"[metadata]\nname=x\n", "setup.cfg").pins == ()


def test_reconstruct_old_and_new_states(tmp_path):
    refs = build_downstream_fixture(tmp_path / "downstream")
    recon = Reconstructor(GitRepo(refs["root"]), "repo:downstream")

    old = recon.state_at(refs["old_tag"], tag=refs["old_tag"])
    assert old.git_sha == refs["old_sha"]
    assert old.lock.version_of("fake-dep") == "1.0"
    assert old.lock.source_files == ["requirements.txt"]

    new = recon.state_at("downstream-v2.0", tag="downstream-v2.0")
    assert new.lock.version_of("fake-dep") == "1.1"

    assert recon.state_at(refs["old_sha"]).git_sha == refs["old_sha"]
    with pytest.raises(HistoryError):
        recon.state_at("no-such-tag")


def test_dependency_diff_between_states(tmp_path):
    refs = build_downstream_fixture(tmp_path / "downstream")
    recon = Reconstructor(GitRepo(refs["root"]), "repo:downstream")
    old = recon.state_at(refs["old_tag"])
    new = recon.state_at(refs["new_tag"])
    diff = recon.diff_states(old, new)
    assert diff.changed == {"fake-dep": ("1.0", "1.1")}
    assert diff.added == {} and diff.removed == {}
    assert recon.diff_states(old, old).changed == {}


def test_installability_against_index(tmp_path):
    refs = build_downstream_fixture(tmp_path / "downstream")
    recon = Reconstructor(GitRepo(refs["root"]), "repo:downstream")
    old = recon.state_at(refs["old_tag"])
    report = recon.check_installable(old, _pypi())
    assert report.installable and report.missing == []

    write(refs["root"], "requirements.txt", "ghost-pkg==9.9\n")
    from phase2_support import commit_all

    commit_all(refs["root"], "pin unknown package")
    ghost = recon.state_at("HEAD")
    missing = recon.check_installable(ghost, _pypi())
    assert not missing.installable
    assert missing.missing == ["ghost-pkg==9.9"]


def test_workaround_present_where_committed(tmp_path):
    refs = build_downstream_fixture(tmp_path / "downstream")
    recon = Reconstructor(GitRepo(refs["root"]), "repo:downstream")
    for rev in (refs["old_tag"], refs["new_tag"]):
        found = recon.workaround_at(rev, tmp_path / f"tree-{rev}")
        assert [c for c in found if c.detector == "ExceptionWorkaroundDetector"]
    base = recon.workaround_at(refs["base_sha"], tmp_path / "tree-base")
    assert not [c for c in base if c.detector == "ExceptionWorkaroundDetector"]


def test_state_without_lock_is_not_installable(tmp_path):
    root = init_repo(tmp_path / "empty")
    write(root, "main.py", "print('hi')\n")
    from phase2_support import commit_all

    commit_all(root, "no deps")
    recon = Reconstructor(GitRepo(root), "repo:empty")
    state = recon.state_at("HEAD")
    assert state.lock.packages == {}
    report = recon.check_installable(state, _pypi())
    assert not report.installable
