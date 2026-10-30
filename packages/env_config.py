"""Safe environment loading for UNBODGE.

Loads variables from .env if present into os.environ.
Existing process environment variables ALWAYS take precedence (never overwritten).
"""

from __future__ import annotations

import os
from pathlib import Path


def load_env(env_path: str | Path | None = None) -> dict[str, str]:
    """Load variables from a .env file into os.environ without overwriting existing vars.

    Returns a dict of newly populated variables (keys and values).
    """
    if env_path is None:
        # Search from current working directory or upward towards repo root
        cwd = Path.cwd().resolve()
        candidate = cwd / ".env"
        if not candidate.is_file():
            # Check parent directory
            if (cwd.parent / ".env").is_file():
                candidate = cwd.parent / ".env"
        env_file = candidate
    else:
        env_file = Path(env_path).resolve()

    if not env_file.is_file():
        return {}

    loaded: dict[str, str] = {}
    try:
        with open(env_file, "r", encoding="utf-8", errors="replace") as f:
            for raw_line in f:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # Strip matching surrounding single or double quotes
                if len(value) >= 2 and (
                    (value.startswith('"') and value.endswith('"'))
                    or (value.startswith("'") and value.endswith("'"))
                ):
                    value = value[1:-1]

                # Process environment variables take strict precedence
                if key and key not in os.environ:
                    os.environ[key] = value
                    loaded[key] = value
    except Exception:
        # Fail closed/safe: environment load error must not crash the process
        pass

    return loaded
