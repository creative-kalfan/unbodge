"""Deterministic local fixtures for Phase 2 tests (no network).

Helpers only -- no product logic. Builds real local git repositories with
fixed author/committer identity and timestamps so history is reproducible.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

FIXED_DATE = "2026-01-01T00:00:00+00:00"
UPSTREAM_FIX_SHA = "c" * 40


def _git_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "GIT_AUTHOR_NAME": "unbodge-test",
            "GIT_AUTHOR_EMAIL": "test@local",
            "GIT_COMMITTER_NAME": "unbodge-test",
            "GIT_COMMITTER_EMAIL": "test@local",
            "GIT_AUTHOR_DATE": FIXED_DATE,
            "GIT_COMMITTER_DATE": FIXED_DATE,
        }
    )
    return env


def git_cmd(path: str | Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=path,
        env=_git_env(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {completed.stderr[:300]}")
    return completed.stdout


def init_repo(path: str | Path) -> Path:
    root = Path(path)
    root.mkdir(parents=True, exist_ok=True)
    git_cmd(root, "init", "-b", "main")
    git_cmd(root, "config", "user.name", "unbodge-test")
    git_cmd(root, "config", "user.email", "test@local")
    git_cmd(root, "config", "commit.gpgsign", "false")
    return root


def commit_all(path: str | Path, message: str) -> str:
    root = Path(path)
    git_cmd(root, "add", "-A")
    git_cmd(root, "commit", "-m", message)
    return git_cmd(root, "rev-parse", "HEAD").strip()


def tag(path: str | Path, name: str) -> None:
    git_cmd(path, "tag", name)


def write(path: str | Path, rel: str, content: str) -> None:
    target = Path(path) / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")


# -- downstream fixture -------------------------------------------------
# OLD rev: buggy dep (KeyError), no workaround. NEW rev: fixed dep.
# The workaround patch adds workaround.py and rewires app.py through it.

DEP_OLD = 'def get_nickname(profile):\n    return profile["nickname"]\n'
DEP_NEW = 'def get_nickname(profile):\n    return profile.get("nickname", "anonymous")\n'
APP_PLAIN = "from dep import get_nickname\n\n\ndef display_name(profile):\n    return get_nickname(profile)\n"
APP_PATCHED = (
    "from workaround import safe_get_nickname as get_nickname\n"
    "\n\ndef display_name(profile):\n    return get_nickname(profile)\n"
)
WORKAROUND_PY = (
    "def safe_get_nickname(profile):\n"
    '    # workaround for upstream fake-dep#7: fall back to anonymous\n'
    "    try:\n"
    "        from dep import get_nickname\n"
    "        return get_nickname(profile)\n"
    "    except KeyError:\n"
    '        return "anonymous"\n'
)
PROBE_PY = (
    "import sys\n"
    "from app import display_name\n"
    "\n"
    "result = display_name({})\n"
    'assert result == "anonymous", f"unexpected nickname: {result!r}"\n'
    'print("probe: PASS nickname=anonymous")\n'
)
REGRESSION_PY = (
    "from app import display_name\n"
    "\n"
    'cases = [({}, "anonymous"), ({"nickname": "ada"}, "ada"), ({"nickname": ""}, "")]\n'
    "passed, failed = 0, 0\n"
    "for profile, expected in cases:\n"
    "    try:\n"
    "        if display_name(profile) == expected:\n"
    "            passed += 1\n"
    "        else:\n"
    "            failed += 1\n"
    "    except Exception:\n"
    "        failed += 1\n"
    "print(f'regression-probes: passed={passed} failed={failed}')\n"
    "raise SystemExit(1 if failed else 0)\n"
)

WORKAROUND_PATCH = """--- a/app.py
+++ b/app.py
@@ -1,4 +1,4 @@
-from dep import get_nickname
+from workaround import safe_get_nickname as get_nickname
 
 
 def display_name(profile):
--- /dev/null
+++ b/workaround.py
@@ -0,0 +1,7 @@
+def safe_get_nickname(profile):
+    # workaround for upstream fake-dep#7: fall back to anonymous
+    try:
+        from dep import get_nickname
+        return get_nickname(profile)
+    except KeyError:
+        return "anonymous"
"""


def build_downstream_fixture(path: str | Path) -> dict:
    """Create OLD/NEW history plus the workaround patch. Returns refs.

    History: base (buggy dep, plain app) -> +workaround (OLD rev) ->
    fixed dep with workaround still present (NEW rev). The patch is the
    forward diff that introduces the workaround onto the base tree.
    """
    root = init_repo(path)
    write(root, "requirements.txt", "fake-dep==1.0\n")
    write(root, "dep.py", DEP_OLD)
    write(root, "app.py", APP_PLAIN)
    write(root, "probe.py", PROBE_PY)
    write(root, "regression_probe.py", REGRESSION_PY)
    base_sha = commit_all(root, "downstream pins fake-dep 1.0 (buggy nickname lookup)")
    (root / "workaround.patch").write_text(WORKAROUND_PATCH, encoding="utf-8", newline="\n")
    apply_patch_text(root, WORKAROUND_PATCH)
    (root / "workaround.patch").unlink()
    write(root, "requirements.txt", "fake-dep==1.0\n")
    old_sha = commit_all(root, "downstream adds nickname workaround")
    tag(root, "downstream-v1.0")
    write(root, "requirements.txt", "fake-dep==1.1\n")
    write(root, "dep.py", DEP_NEW)
    new_sha = commit_all(root, "downstream pins fake-dep 1.1 (upstream fix)")
    tag(root, "downstream-v2.0")
    return {
        "root": root,
        "base_sha": base_sha,
        "old_sha": old_sha,
        "new_sha": new_sha,
        "old_tag": "downstream-v1.0",
        "new_tag": "downstream-v2.0",
        "patch": WORKAROUND_PATCH,
    }


def apply_patch_text(workdir: str | Path, patch: str, *, reverse: bool = False) -> None:
    args = ["apply", "--whitespace=nowarn"]
    if reverse:
        args.append("-R")
    args.append("-")
    completed = subprocess.run(
        ["git", *args],
        cwd=workdir,
        input=patch.encode("utf-8"),
        env=_git_env(),
        capture_output=True,
        timeout=60,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"git apply failed: {detail}")
