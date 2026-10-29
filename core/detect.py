from core.common import *


# ──────────────── SOURCE DETECTION ────────────────

def detect_source(url):
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower()

        if host == "pornhub.com" or host.endswith(".pornhub.com"):
            return "phub"

        if host == "njavtv.com" or host.endswith(".njavtv.com"):
            return "njav"

        if "xhamster" in host:
            return "hamster"

        if "xvideos" in host:
            return "xvideos"

        if "eporner" in host:
            return "eporner"

        if "hqporner" in host:
            return "hqporner"

    except ValueError:
        pass

    return None
