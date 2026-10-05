"""Sample: upstream reference with temporary shim (fires UpstreamReferenceDetector)."""
# See https://github.com/acme/fake-dep/issues/7 -- temporary shim


def get_nickname(profile):
    try:
        return profile["nickname"]
    except KeyError:
        return "anonymous"
