"""Sample: monkey patch on an imported module (fires MonkeyPatchDetector)."""
import requests

requests.adapters.DEFAULT_TIMEOUT = 30
