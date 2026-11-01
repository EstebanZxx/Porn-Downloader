from core.common import *
from urllib.parse import urlparse, parse_qsl, urlencode


# ──────────────── VIDARA API ────────────────

def get_vidara_filecode(url):
    """filecode = segmen terakhir path, misalnya /e/rLx5dw28rrBf -> rLx5dw28rrBf"""
    path = urlparse(url).path.rstrip("/")
    return path.split("/")[-1] if path else ""


def fetch_vidara_stream(url):
    """
    Meniru request yang dikirim player vidara di browser:
    POST /api/stream dengan body {filecode, device, codecs}.
    Return (title, streaming_url, origin).
    """
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.hostname}"

    filecode = get_vidara_filecode(url)
    if not filecode:
        raise RuntimeError("filecode tidak ditemukan di link vidara")

    # Query string dari link, tanpa parameter filecode (sama seperti player)
    query = [(k, v) for k, v in parse_qsl(parsed.query) if k != "filecode"]
    api_url = f"{origin}/api/stream" + (f"?{urlencode(query)}" if query else "")

    api_headers = {
        **headers,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Referer": url,
        "Origin": origin,
    }

    body = {
        "filecode": filecode,
        "device": "android",
        "codecs": [],
    }

    r = requests.post(api_url, json=body, headers=api_headers, timeout=30)

    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} dari /api/stream")

    data = r.json()
    stream = data.get("streaming_url")

    if not stream:
        raise RuntimeError("streaming_url kosong di respons vidara")

    title = data.get("title") or filecode
    return title, stream, origin


# ──────────────── DOWNLOAD STREAM (dipakai vidara & avtube) ────────────────

def download_stream(title, stream, origin, source_key):
    """Download stream vidara: HLS lewat download_video, file biasa lewat download_direct_file."""
    title = safe_filename(title)

    stream_headers = {
        **headers,
        "Referer": origin + "/",
        "Origin": origin,
    }

    info("Title", title)
    info("Stream", stream)

    output_path = os.path.join(get_output_dir(source_key), f"{title}.mp4")

    console.print(
        make_panel(
            f"""
[bold white]Title[/bold white]   : [bold {THEME_ACCENT}]{title}[/bold {THEME_ACCENT}]
[bold white]Output[/bold white]  : [bold {THEME_WARN}]{output_path}[/bold {THEME_WARN}]
""".strip(),
            title=f"[bold italic white] {source_key.upper()} READY [/bold italic white]",
            border_style=THEME_ACCENT
        )
    )

    link_type, _ = detect_manual_link_type(stream, stream_headers)

    if link_type == "hls":
        # F4/CDN sering lebih kencang dengan worker lebih banyak
        host = (urlparse(stream).hostname or "").lower()
        extra = 24 if any(h in host for h in ("f4scdn", "f4stream", "ystream", "owphbf", "sprintcdn")) else None
        return download_video(stream, output_path, stream_headers, workers=extra) is True

    if not download_direct_file(stream, output_path, stream_headers):
        error("Download gagal")
        return False

    size_mb = os.path.getsize(output_path) / 1024 / 1024
    ok(f"Saved {output_path} ({size_mb:.2f} MB)")
    return True


# ──────────────── PROCESS VIDARA ────────────────

def process_vidara(url):
    section("Fetching Vidara")

    try:
        title, stream, origin = fetch_vidara_stream(url)
        return download_stream(title, stream, origin, "vidara")

    except RuntimeError as exc:
        error(str(exc))
        return False

    except requests.RequestException as exc:
        error(f"Vidara request error: {exc}")
        return False

    except KeyboardInterrupt:
        error("Download dibatalkan")
        return False

    except Exception as exc:
        error(f"Vidara error: {exc}")
        return False
