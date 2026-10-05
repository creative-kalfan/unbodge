"""Sample: exception fallback with workaround comment (fires ExceptionWorkaroundDetector)."""


def get_nickname(profile):
    # workaround for missing nicknames
    try:
        return profile["nickname"]
    except KeyError:
        return "anonymous"
