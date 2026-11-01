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

        if "vidara" in host:
            return "vidara"

        if "avtub" in host or host == "66.29.129.113":
            return "avtube"

        if "javstory" in host:
            return "javstory"

        if "javsubindo" in host:
            return "javsubindo"

        if "javbos" in host:
            return "javbos"

        if "rumah" in host and "perjaka" in host:
            return "rumahperjaka"

        if "kingbokep" in host:
            return "kingbokep"

        if "avpinay" in host:
            return "avpinay"

        if "ystream.id" in host or host.endswith("ystream.id"):
            return "avpinay"

        if "sextb" in host:
            return "sextb"

        if "f4scdn.com" in host or "f4stream.com" in host or "f2stb.com" in host or "f4s.top" in host:
            return "sextb"

        if "virtuavixen" in host:
            return "virtuavixen"

    except ValueError:
        pass

    return None
