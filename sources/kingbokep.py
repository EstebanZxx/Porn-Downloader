from core.common import *
from sources.vidara import download_stream
from urllib.parse import urlparse


# ──────────────── KINGBOKEP EXTRACTOR ────────────────

def find_kingbokep_playlist(content):
    """Link playlist ada di atribut data-playlist pada tag <video>."""
    match = re.search(r'data-playlist="([^"]+\.m3u8[^"]*)"', content)
    if match:
        return html.unescape(match.group(1))

    match = re.search(r'property="og:video"\s+content="([^"]+\.m3u8[^"]*)"', content)
    if match:
        return html.unescape(match.group(1))

    return None


def find_kingbokep_title(content):
    """<title>Video Paling Suka Cewe Pake Hijab Pink | KingBokep</title> -> judul bersih."""
    match = re.search(r"<title[^>]*>(.*?)</title>", content, re.DOTALL | re.IGNORECASE)
    title = html.unescape(match.group(1)).strip() if match else "kingbokep_video"
    title = re.split(r"\s+\|\s+KingBokep", title, flags=re.IGNORECASE)[0]
    title = re.sub(r"^\s*Video\s+", "", title, flags=re.IGNORECASE)
    return safe_filename(title.strip()) or "kingbokep_video"


# ──────────────── PROCESS KINGBOKEP ────────────────

def process_kingbokep(url):
    section("Fetching KingBokep")

    try:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.hostname}"

        # Link playlist langsung (.m3u8): minta judul, lalu unduh
        if url.split("?")[0].lower().endswith(".m3u8"):
            raw_title = Prompt.ask(
                "[bold white]Judul video[/bold white]",
                default="kingbokep_video"
            ).strip()
            title = safe_filename(raw_title) or "kingbokep_video"
            return download_stream(title, url, origin, "kingbokep") is True

        page_headers = build_dynamic_headers(url)
        r = requests.get(url, headers=page_headers, timeout=30)

        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} dari halaman KingBokep")

        content = r.text
        playlist = find_kingbokep_playlist(content)

        if not playlist:
            raise RuntimeError("Link playlist tidak ditemukan di halaman. Tempel link .m3u8 langsung.")

        title = find_kingbokep_title(content)
        info("Title", title)
        return download_stream(title, playlist, origin, "kingbokep") is True

    except RuntimeError as exc:
        error(str(exc))
        return False

    except requests.RequestException as exc:
        error(f"KingBokep request error: {exc}")
        return False

    except KeyboardInterrupt:
        raise

    except Exception as exc:
        error(f"KingBokep error: {exc}")
        return False
