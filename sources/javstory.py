from core.common import *
from urllib.parse import urlparse, urljoin, parse_qsl, urlencode
from sources.vidara import download_stream


# ──────────────── JAVSTORY EXTRACTOR ────────────────

def find_javstory_title(content):
    """Ambil judul dari <title>, buang suffix " - JAVStory1" dan ganti " | " jadi spasi."""
    match = re.search(r"<title[^>]*>(.*?)</title>", content, re.DOTALL | re.IGNORECASE)
    title = html.unescape(match.group(1)).strip() if match else "javstory_video"
    title = re.sub(r"\s*-\s*JAVStory1\s*$", "", title, flags=re.IGNORECASE)
    title = title.replace(" | ", " ")
    return safe_filename(title) or "javstory_video"


def find_server_urls(content):
    """Ambil semua data-stream-url dari tombol server."""
    urls = re.findall(r'data-stream-url=["\']([^"\']+)["\']', content, re.IGNORECASE)
    return [html.unescape(u) for u in urls]


def decode_streamtape_url(content):
    """
    Decode link video Streamtape dari JS:
      document.getElementById('robotlink').innerHTML = '//streamtape.com/get_video?id=...'+('...').substring(n);
    Return URL lengkap (https://...) atau None.
    """
    m = re.search(r"robotlink'\)\.innerHTML\s*=\s*", content)
    if not m:
        return None

    rest = content[m.end():]
    end = rest.find(";")
    expr = rest[:end] if end >= 0 else rest[:500]

    token_re = re.compile(
        r"\(\s*'([^']*)'\s*\)\s*\.substring\(\s*(\d+)\s*\)"
        r"|\(\s*\"([^\"]*)\"\s*\)\s*\.substring\(\s*(\d+)\s*\)"
        r"|'([^']*)'"
        r"|\"([^\"]*)\""
    )

    parts = []
    for t in token_re.finditer(expr):
        if t.group(1) is not None:
            parts.append(t.group(1)[int(t.group(2)):])
        elif t.group(3) is not None:
            parts.append(t.group(3)[int(t.group(4)):])
        elif t.group(5) is not None:
            parts.append(t.group(5))
        elif t.group(6) is not None:
            parts.append(t.group(6))

    url = "".join(parts).strip()
    if not url:
        return None

    if url.startswith("//"):
        url = "https:" + url
    return url


def normalize_streamtape_url(video_url, embed_url):
    """
    Decode JS kadang menghasilkan host/param yang meleset (mis. 'streamtaped.xyz', 'did=').
    Rangkai ulang: host dari halaman embed, id dari path embed, sisanya tetap dari hasil decode.
    """
    embed = urlparse(embed_url)
    parts = [p for p in embed.path.split("/") if p]
    embed_id = parts[-1] if parts else ""
    for marker in ("e", "v"):
        if marker in parts:
            idx = parts.index(marker)
            if idx + 1 < len(parts):
                embed_id = parts[idx + 1]
                break

    decoded = urlparse(video_url)
    params = parse_qsl(decoded.query, keep_blank_values=True)

    fixed = []
    for key, value in params:
        if key in ("did", "id"):
            continue
        fixed.append((key, value))

    fixed.insert(0, ("id", embed_id))

    return f"{embed.scheme}://{embed.hostname}/get_video?{urlencode(fixed)}"


def fetch_streamtape_video(embed_url, page_url):
    """Buka halaman embed Streamtape, decode link get_video-nya."""
    embed_headers = {**build_dynamic_headers(embed_url), "Referer": page_url}

    r = requests.get(embed_url, headers=embed_headers, timeout=30)

    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} dari halaman Streamtape")

    video_url = decode_streamtape_url(r.text)

    if not video_url:
        raise RuntimeError("link video Streamtape tidak ditemukan di halaman embed")

    return normalize_streamtape_url(video_url, embed_url)


# ──────────────── PROCESS JAVSTORY ────────────────

def process_javstory(url):
    section("Fetching JAVStory1")

    try:
        page_headers = build_dynamic_headers(url)

        r = requests.get(url, headers=page_headers, timeout=30)

        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} dari halaman JAVStory1")

        content = r.text
        title = find_javstory_title(content)

        servers = find_server_urls(content)
        streamtape = [s for s in servers if "streamtape" in (urlparse(s).hostname or "")]

        if not streamtape:
            raise RuntimeError("Server Streamtape tidak ditemukan di halaman. Pakai mode manual.")

        embed_url = streamtape[0]
        info("Player", embed_url)

        video_url = fetch_streamtape_video(embed_url, url)
        origin = f"{urlparse(embed_url).scheme}://{urlparse(embed_url).hostname}"

        return download_stream(title, video_url, origin, "javstory")

    except RuntimeError as exc:
        error(str(exc))
        return False

    except requests.RequestException as exc:
        error(f"JAVStory request error: {exc}")
        return False

    except KeyboardInterrupt:
        error("Download dibatalkan")
        return False

    except Exception as exc:
        error(f"JAVStory error: {exc}")
        return False
