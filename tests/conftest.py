"""Keep the repository root importable for pytest without installation."""

import socket
import sys
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _blocked(*args, **kwargs):
    raise AssertionError("live network access is forbidden in tests")


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    """Prove the suite is offline: all provider tests inject transports."""
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(urllib.request, "urlopen", _blocked)
    yield
