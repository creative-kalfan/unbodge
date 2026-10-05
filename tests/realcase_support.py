"""Real-case fixtures: packaging PEP 685 x pip workaround (Phase 3).

Vendors REAL upstream bytes (SHA-verified sdists, see PROVENANCE.md) and
builds a downstream git history around them. The downstream probe scripts
are harness vehicles (like Phase 2); every byte they execute from the
dependency and the workaround shim is real.
"""

from __future__ import annotations

import shutil
import tarfile
from pathlib import Path

from phase2_support import commit_all, git_cmd, init_repo, tag, write

FIXTURES = Path(__file__).parent / "fixtures" / "real_case"

TARBALLS = {
    "21.3": FIXTURES / "packaging-21.3.tar.gz",
    "22.0": FIXTURES / "packaging-22.0.tar.gz",
    "pyparsing": FIXTURES / "pyparsing-3.0.9.tar.gz",
}

# -- verified real-world references (see PROVENANCE.md) ------------------
UPSTREAM_ISSUE_ID = "issue:packaging-545"
UPSTREAM_ISSUE_URL = "https://github.com/pypa/packaging/issues/545"
UPSTREAM_ISSUE_TITLE = "Adhere to PEP 685 when evaluating markers with extras"
FIX_COMMIT_ID = "fix:packaging-53dbb25"
FIX_COMMIT_SHA = "53dbb257e5fef150d32ef85c7427133d71651989"
FIX_COMMIT_MESSAGE = "Adhere to PEP 685 when evaluating markers with extras (#545)"
RELEASE_ID = "rel:packaging-22.0"
RELEASE_TAG = "22.0"
OLD_VERSION = "21.3"
NEW_VERSION = "22.0"
DOWNSTREAM_SYMPTOM_URL = "https://github.com/pypa/pip/issues/11924"
WORKAROUND_PR_URL = "https://github.com/pypa/pip/pull/12095"
REMOVAL_COMMIT = "4d70566c687d83cd8e0c0c41040b9beaca41492c"

MARKER_TEXT = "extra == 'foo-bar'"
CANONICAL_EXTRA = "foo_bar"

CHECK_PLAIN = """import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

from packaging.markers import Marker

MARKER_TEXT = os.environ.get("MARKER_TEXT", "extra == 'foo-bar'")
EXTRA = os.environ.get("MARKER_EXTRA", "foo_bar")

result = Marker(MARKER_TEXT).evaluate({"extra": EXTRA})
print(f"plain evaluate: {result}")
raise SystemExit(0 if result else 1)
"""

PIP_COMPAT_PY = '''"""Downstream compatibility shim for PEP 685 markers.

Workaround for https://github.com/pypa/packaging/issues/545: evaluate
requirement markers three ways until the installed packaging normalizes
extras itself. Mirrors pip 23.3 InstallRequirement.match_markers.
"""
import re
from typing import NewType, cast

NormalizedExtra = NewType("NormalizedExtra", str)


def safe_extra(extra: str) -> NormalizedExtra:
    """Convert an arbitrary string to a standard 'extra' name

    Any runs of non-alphanumeric characters are replaced with a single '_',
    and the result is always lowercased.

    This function is duplicated from ``pkg_resources``. Note that this is not
    the same to either ``canonicalize_name`` or ``_egg_link_name``.
    """
    return cast(NormalizedExtra, re.sub("[^A-Za-z0-9.-]+", "_", extra).lower())


def compensated_evaluate(marker, extra, canonicalize_name):
    """Mirror of pip's 3-way match_markers evaluation (pip 23.3)."""
    return (
        marker.evaluate({"extra": extra})
        or marker.evaluate({"extra": safe_extra(extra)})
        or marker.evaluate({"extra": canonicalize_name(extra)})
    )
'''

CHECK_PATCHED = """import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

from packaging.markers import Marker
from packaging.utils import canonicalize_name
from pip_compat import compensated_evaluate

MARKER_TEXT = os.environ.get("MARKER_TEXT", "extra == 'foo-bar'")
EXTRA = os.environ.get("MARKER_EXTRA", "foo_bar")

result = compensated_evaluate(Marker(MARKER_TEXT), EXTRA, canonicalize_name)
print(f"compensated evaluate: {result}")
raise SystemExit(0 if result else 1)
"""

# Cases 1-4 mirror pip tests/unit/test_req.py::TestInstallRequirement
# test_markers_match_from_line / test_markers_match (pip 24.0).
# Cases 5-8 are verbatim from packaging tests/test_markers.py as added by
# fix commit 53dbb25 (packaging 22.0).
REGRESSION_MARKERS = """import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "vendor"))

import sys as _sys
from packaging.markers import Marker

CASES = [
    ('python_version >= "1.0"', None, True),
    ('python_version >= "5.0"', None, False),
    (f"sys_platform == {_sys.platform!r}", None, True),
    (f"sys_platform != {_sys.platform!r}", None, False),
    ("extra == 'SECURITY'", "security", True),
    ("extra == 'security'", "SECURITY", True),
    ("extra == 'pep-685-norm'", "PEP_685...norm", True),
    (
        "extra == 'Different.punctuation..is...equal'",
        "different__punctuation_is_EQUAL",
        True,
    ),
]

passed = failed = 0
for marker_text, extra, expected in CASES:
    env = {"extra": ""} if extra is None else {"extra": extra}
    try:
        got = Marker(marker_text).evaluate(env)
    except Exception as exc:
        got = f"ERROR: {exc}"
    if got == expected:
        passed += 1
    else:
        failed += 1
        print(f"MISMATCH {marker_text!r} with {env}: got {got!r}, want {expected!r}")

print(f"regression-markers: passed={passed} failed={failed}")
raise SystemExit(1 if failed else 0)
"""


def stage_vendor(
    tarball: Path, dest: Path, top: str, keep: tuple[str, ...] = ("packaging/", "pyparsing/")
) -> None:
    """Extract an sdist subset into ``dest`` with traversal guards."""
    dest.mkdir(parents=True, exist_ok=True)
    members = 0
    total = 0
    with tarfile.open(tarball) as tar:
        entries = tar.getmembers()
        for member in entries:
            name = member.name
            if not name.startswith(top + "/"):
                continue
            rel = name[len(top) + 1:]
            if not rel:
                continue
            if rel.startswith("/") or "\\" in rel or ":" in rel.split("/")[0]:
                raise ValueError(f"unsafe sdist member: {name!r}")
            if ".." in Path(rel).parts:
                raise ValueError(f"unsafe sdist member: {name!r}")
            if member.issym() or member.islnk():
                raise ValueError(f"sdist symlinks refused: {name!r}")
        for member in entries:
            name = member.name
            if not name.startswith(top + "/"):
                continue
            rel = name[len(top) + 1:]
            if not rel or not any(rel == k.rstrip("/") or rel.startswith(k) for k in keep):
                continue
            members += 1
            if members > 5000:
                raise ValueError("sdist exceeds member cap")
            if member.isfile():
                total += member.size
                if total > 50 * 1024 * 1024:
                    raise ValueError("sdist exceeds byte cap")
            member.name = rel
            tar.extract(member, path=dest, filter="data")


def stage_tree(root: Path, version: str) -> None:
    """Stage requirements + vendored dependency bytes + probes."""
    write(root, "requirements.txt", f"packaging=={version}\n")
    vendor = root / "vendor"
    if version == OLD_VERSION:
        stage_vendor(TARBALLS["21.3"], vendor, "packaging-21.3")
        stage_vendor(TARBALLS["pyparsing"], vendor, "pyparsing-3.0.9")
    else:
        stage_vendor(TARBALLS["22.0"], vendor, "packaging-22.0")
    write(root, "check.py", CHECK_PLAIN)
    write(root, "regression_markers.py", REGRESSION_MARKERS)


def build_real_repo(path) -> dict:
    """Build OLD/NEW history with a committed workaround. Returns refs."""
    root = init_repo(path)
    stage_tree(root, OLD_VERSION)
    base_sha = commit_all(root, "base: plain marker evaluation against packaging 21.3")
    write(root, "pip_compat.py", PIP_COMPAT_PY)
    write(root, "check.py", CHECK_PATCHED)
    old_sha = commit_all(root, "downstream workaround for PEP 685 markers (pip#12095 pattern)")
    tag(root, "real-old")
    for stale in ("vendor/packaging", "vendor/pyparsing"):
        shutil.rmtree(root / stale, ignore_errors=True)
    stage_tree(root, NEW_VERSION)
    write(root, "pip_compat.py", PIP_COMPAT_PY)
    write(root, "check.py", CHECK_PATCHED)
    new_sha = commit_all(root, "packaging 22.0: upstream PEP 685 fix")
    tag(root, "real-new")
    patch = git_cmd(root, "diff", f"{base_sha}..{old_sha}", "--")
    return {
        "root": root,
        "base_sha": base_sha,
        "old_sha": old_sha,
        "new_sha": new_sha,
        "old_tag": "real-old",
        "new_tag": "real-new",
        "patch": patch,
    }
