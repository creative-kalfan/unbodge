"""Root conftest: make packages/* importable without an install (offline-friendly)."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_PKGDIR = os.path.join(_HERE, "packages")
if _PKGDIR not in sys.path:
    sys.path.insert(0, _PKGDIR)
