"""Sample: platform branch (fires CompatibilityBranchDetector)."""
import platform

if platform.system() == "Windows":
    SEP = "\\"
else:
    SEP = "/"
