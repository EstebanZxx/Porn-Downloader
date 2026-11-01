from core.common import *
from sources.vidara import download_stream
from urllib.parse import urlparse, urljoin


# ──────────────── SEBOKEP EXTRACTOR ────────────────

def find_sebokep_player(content, page_url):
    """
    Halaman sebokep memuat player di iframe. Prioritaskan host pemersatu,
    lalu iframe lain yang punya path /e/ (pola embed).
    """
    frames = []
    for src in re.findall(r'<iframe[^>]+src="([^"]+)"', content, re.IGNORECASE):
        full = urljoin(page_url, html.unescape(src))
        if full not in frames:
            frames.append(full)

    for frame in frames:
        if "pemersatu" in (urlparse(frame).hostname or ""):
            return frame

    for frame in frames:
        if "/e/" in urlparse(frame).path:
            return frame

    return None


def find_sebokep_video(content):
    """
    Sumber video: atribut src pada tag <video>, lalu cadangan dari URL .m3u8 di dalam skrip.
    """
    match = re.search(r'<video[^>]*\ssrc="([^"]+\.m3u8[^"]*)"', content, re.IGNORECASE)
    if match:
        return html.unescape(match.group(1))

    text = html.unescape(content.replace("\\/", "/"))
    match = re.search(r'https?://[^\s"\'<>\\]+?\.m3u8[^\s"\'<>\\]*', text)
    if match:
        return match.group(0)

    return None


def find_sebokep_title(content):
    """<title>Gina Hijab Tiktoker Omek Terbaru - SEBOKEP</title> -> judul bersih."""
    match = re.search(r"<title[^>]*>(.*?)</title>", content, re.DOTALL | re.IGNORECASE)
    title = html.unescape(match.group(1)).strip() if match else "sebokep_video"
    title = re.sub(r"\s*-\s*SEBOKEP\s*$", "", title, flags=re.IGNORECASE)
    return safe_filename(title.strip()) or "sebokep_video"


# ──────────────── PROCESS SEBOKEP ────────────────

def process_sebokep(url):
    section("Fetching Sebokep")

    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""

        # Link embed player langsung (pemersatu): minta judul, lalu ambil videonya
        if "pemersatu" in host:
            embed_url = url
            page_url = url
            title = None
        else:
            page_headers = build_dynamic_headers(url)
            r = requests.get(url, headers=page_headers, timeout=30)

            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code} dari halaman Sebokep")

            page_content = r.text
            embed_url = find_sebokep_player(page_content, url)
            page_url = url
            title = find_sebokep_title(page_content)

            if not embed_url:
                raise RuntimeError("Player tidak ditemukan di halaman. Tempel link embed langsung.")

        info("Player", embed_url)

        embed_headers = {**build_dynamic_headers(embed_url), "Referer": page_url}
        er = requests.get(embed_url, headers=embed_headers, timeout=30)

        if er.status_code != 200:
            raise RuntimeError(f"HTTP {er.status_code} dari halaman player")

        stream = find_sebokep_video(er.text)

        if not stream:
            raise RuntimeError(
                f"Link video tidak ditemukan di player {embed_url}. "
                f"Respons {len(er.text)} karakter, ada <video>: {'<video' in er.text}, "
                f"awal: {er.text[:120]!r}. "
                "Video dibuat oleh JS player. Pakai mode manual dengan link .m3u8 dari sniffer."
            )

        if title is None:
            raw_title = Prompt.ask(
                "[bold white]Judul video[/bold white]",
                default="sebokep_video"
            ).strip()
            title = safe_filename(raw_title) or "sebokep_video"

        ep = urlparse(embed_url)
        origin = f"{ep.scheme}://{ep.hostname}"
        return download_stream(title, stream, origin, "sebokep") is True

    except RuntimeError as exc:
        error(str(exc))
        return False

    except requests.RequestException as exc:
        error(f"Sebokep request error: {exc}")
        return False

    except KeyboardInterrupt:
        raise

    except Exception as exc:
        error(f"Sebokep error: {exc}")
        return False
