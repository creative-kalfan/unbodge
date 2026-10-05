"""Sample: dependency version check (fires VersionCheckDetector only)."""
import sys

if sys.version_info < (3, 9):
    LEGACY_MODE = True
else:
    LEGACY_MODE = False
