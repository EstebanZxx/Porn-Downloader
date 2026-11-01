from core.common import *
from sources.vidara import download_stream
from urllib.parse import urlparse
import json

VIXEN_ORIGIN = "https://virtuavixen.com"


# ──────────────── VIRTUAVIXEN EXTRACTOR ────────────────

def find_vixen_sources(content):
    """
    Sumber video ada di atribut data-item (JSON yang di-escape HTML).
    Return daftar URL stream-loader yang sudah bertanda tangan (signature + expire).
    """
    sources = []
    for match in re.finditer(r'data-item="([^"]+)"', content):
        raw = html.unescape(match.group(1))
        try:
            data = json.loads(raw)
        except ValueError:
            continue
        for src in data.get("sources", []):
            url = src.get("src")
            if url and url not in sources:
                sources.append(url)
    return sources


def pick_best_source(sources):
    """pl=2 adalah 480p, pl=1 adalah 240p, jadi pl terbesar = kualitas tertinggi."""
    if not sources:
        return None

    def pl_value(url):
        match = re.search(r"[?&]pl=(\d+)", url)
        return int(match.group(1)) if match else 0

    return max(sources, key=pl_value)


def find_vixen_title(content):
    """
    <title>Kevin The Gigolo Eps 4: ... &#8211; VirtuaVixen &#8211; AI Porn</title>
      -> "Kevin The Gigolo Eps 4: ..."
    """
    match = re.search(r"<title[^>]*>(.*?)</title>", content, re.DOTALL | re.IGNORECASE)
    title = html.unescape(match.group(1)).strip() if match else "vixen_video"
    title = re.split(r"\s+[-–—]\s+VirtuaVixen", title, flags=re.IGNORECASE)[0]
    return safe_filename(title.strip()) or "vixen_video"


# ──────────────── PROCESS VIRTUAVIXEN ────────────────

def process_vixen(url):
    section("Fetching VirtuaVixen")

    try:
        # Link stream-loader langsung (misalnya 480 atau 240 yang didapat dari browser)
        if "stream-loader" in url:
            raw_title = Prompt.ask(
                "[bold white]Judul video[/bold white]",
                default="vixen_video"
            ).strip()
            title = safe_filename(raw_title) or "vixen_video"
            return download_stream(title, url, VIXEN_ORIGIN, "vixen") is True

        page_headers = build_dynamic_headers(url)
        r = requests.get(url, headers=page_headers, timeout=30)

        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} dari halaman VirtuaVixen")

        content = r.text
        best = pick_best_source(find_vixen_sources(content))

        if not best:
            raise RuntimeError("Sumber video tidak ditemukan di halaman. Tempel link stream-loader langsung.")

        title = find_vixen_title(content)
        info("Title", title)
        return download_stream(title, best, VIXEN_ORIGIN, "vixen") is True

    except RuntimeError as exc:
        error(str(exc))
        return False

    except requests.RequestException as exc:
        error(f"VirtuaVixen request error: {exc}")
        return False

    except KeyboardInterrupt:
        raise

    except Exception as exc:
        error(f"VirtuaVixen error: {exc}")
        return False
