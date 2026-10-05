"""Real counterfactual execution over fixture history (live containers)."""

import pytest

from domain.enums import TestStatus, UniverseCell
from domain.errors import DomainError
from experiments.contracts import meets_removal_bar
from experiments.real import (
    apply_patch,
    dependency_label_at,
    ensure_workaround_state,
    patch_marker_files,
    prepare_cell_workdir,
    read_workdir_files,
    run_real_suite,
)
from github.git import GitRepo
from phase2_support import build_downstream_fixture
from sandbox.docker import DockerSandbox, docker_available

needs_docker = pytest.mark.skipif(
    not docker_available(), reason="docker daemon or image unavailable"
)


def test_patch_applies_forward_and_reverse(tmp_path):
    refs = build_downstream_fixture(tmp_path / "downstream")
    git = GitRepo(refs["root"])
    assert patch_marker_files(refs["patch"]) == ["workaround.py"]
    assert patch_marker_files("no diff here") == []

    fresh = prepare_cell_workdir(git, refs["base_sha"], tmp_path / "cell-base")
    assert not (fresh / "workaround.py").exists()
    apply_patch(fresh, refs["patch"])
    assert "safe_get_nickname" in (fresh / "app.py").read_text()

    present = prepare_cell_workdir(git, refs["old_sha"], tmp_path / "cell-a")
    assert (present / "workaround.py").exists()
    ensure_workaround_state(present, refs["patch"], present=True)
    assert (present / "workaround.py").exists()
    ensure_workaround_state(present, refs["patch"], present=False)
    assert not (present / "workaround.py").exists()
    assert "from dep import get_nickname" in (present / "app.py").read_text()

    with pytest.raises(DomainError):
        prepare_cell_workdir(
            git, refs["old_sha"], tmp_path / "cell-x", workaround_patch="not a patch"
        )
    with pytest.raises(DomainError):
        ensure_workaround_state(present, "no diff here", present=True)


def test_dependency_labels_from_history(tmp_path):
    refs = build_downstream_fixture(tmp_path / "downstream")
    git = GitRepo(refs["root"])
    assert dependency_label_at(git, refs["old_sha"]) == "fake-dep==1.0"
    assert dependency_label_at(git, refs["new_tag"]) == "fake-dep==1.1"
    assert dependency_label_at(git, refs["old_sha"], package="ghost") == "ghost==unknown"


def test_read_workdir_files_skips_binary_and_caps(tmp_path):
    target = tmp_path / "work"
    (target / "sub").mkdir(parents=True)
    (target / "a.py").write_text("print(1)\n")
    (target / "sub" / "blob.bin").write_bytes(bytes(range(256)))
    staged = read_workdir_files(target)
    assert staged == {"a.py": "print(1)\n"}


@needs_docker
def test_real_suite_proves_canonical_matrix(tmp_path):
    refs = build_downstream_fixture(tmp_path / "downstream")
    git = GitRepo(refs["root"])
    sandbox = DockerSandbox()
    result = run_real_suite(
        git=git,
        repository_id="repo:downstream",
        old_rev=refs["old_tag"],
        new_rev=refs["new_tag"],
        workaround_patch=refs["patch"],
        probe_argv=["python", "probe.py"],
        probe_env={"DEP_VERSION": "OLD"},
        sandbox=sandbox,
        plan_id="real:proof",
    )
    assert result.matrix == {
        UniverseCell.A: TestStatus.PASS,
        UniverseCell.B: TestStatus.FAIL,
        UniverseCell.C: TestStatus.PASS,
        UniverseCell.D: TestStatus.PASS,
    }
    assert result.is_canonical_success
    assert meets_removal_bar(result.matrix)
    run_b = result.runs[UniverseCell.B]
    assert run_b.git_sha == refs["old_sha"]
    assert run_b.dependency_state["fake-dep"] == "fake-dep==1.0"
    assert "DEP_VERSION" in run_b.environment
    assert run_b.artifact_hashes  # container transcripts hashed


@needs_docker
def test_real_suite_requires_patch_for_present_cells(tmp_path):
    refs = build_downstream_fixture(tmp_path / "downstream")
    git = GitRepo(refs["root"])
    with pytest.raises(DomainError):
        run_real_suite(
            git=git,
            repository_id="repo:downstream",
            old_rev=refs["old_tag"],
            new_rev=refs["new_tag"],
            workaround_patch=None,
            probe_argv=["python", "probe.py"],
            sandbox=DockerSandbox(),
        )
