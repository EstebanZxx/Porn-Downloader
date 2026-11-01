from core.common import *
from urllib.parse import urlparse

PODJAV_STREAM = "https://play.podjav.tv/file/movie-podjav/{code}/720p/720p.m3u8"


# ──────────────── JAVBOS EXTRACTOR ────────────────

def find_javbos_code(url, content=""):
    """Kode video dari slug URL, misalnya /jur-815-sub-indo-... -> JUR-815."""
    slug = urlparse(url).path.strip("/").split("/")[-1]
    match = re.match(r"([a-z]{2,6}-\d{2,5})", slug, re.IGNORECASE)
    if match:
        return match.group(1).upper()

    match = re.search(r"<title[^>]*>\s*([A-Z]{2,6}-\d{2,5})", content, re.IGNORECASE)
    if match:
        return match.group(1).upper()

    return None


def find_javbos_title(content):
    """
    <title>JUR-815 Sub Indo : Pada Hari Ketujuh ... - JavBos</title>
      -> "JUR-815 Pada Hari Ketujuh ..."
    """
    match = re.search(r"<title[^>]*>(.*?)</title>", content, re.DOTALL | re.IGNORECASE)
    title = html.unescape(match.group(1)).strip() if match else "javbos_video"
    title = re.sub(r"\s*-\s*JavBos\s*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s+Sub\s+Indo\s*:\s*", " ", title, flags=re.IGNORECASE)
    return safe_filename(title.strip()) or "javbos_video"


def subtitle_page_url(url):
    """Link subtitle untuk ditampilkan ke user (TIDAK diakses oleh script)."""
    p = urlparse(url)
    slug = p.path.strip("/").split("/")[-1]
    return f"{p.scheme}://{p.hostname}/api/subtitle/{slug}"


# ──────────────── SUBTITLE MUX ────────────────

def mux_subtitle(video_path, sub_path):
    """Pasang subtitle .srt/.vtt ke MP4 sebagai track mov_text (tanpa re-encode video)."""
    if not shutil.which("ffmpeg"):
        error("ffmpeg tidak ditemukan. Install dengan: pkg install ffmpeg")
        return False

    tmp_path = video_path + ".sub.mp4"
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", video_path,
        "-i", sub_path,
        "-map", "0", "-map", "1",
        "-c", "copy", "-c:s", "mov_text",
        tmp_path,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0 or not os.path.exists(tmp_path):
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        error(f"Gagal memasang subtitle: {result.stderr.strip()[:200]}")
        return False

    os.replace(tmp_path, video_path)
    ok(f"Subtitle dipasang ke {video_path}")
    return True


def ask_subtitle_path():
    """Tanya path file subtitle. Kosong = lewati."""
    raw = Prompt.ask(
        "[bold white]Path file subtitle (.srt/.vtt), kosongkan untuk lewati[/bold white]",
        default=""
    ).strip().strip("'\"")
    return raw


# ──────────────── PROCESS JAVBOS ────────────────

def process_javbos(url):
    section("Fetching JAVBOS")

    try:
        page_headers = build_dynamic_headers(url)
        r = requests.get(url, headers=page_headers, timeout=30)

        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} dari halaman JAVBOS")

        content = r.text
        code = find_javbos_code(url, content)
        if not code:
            raise RuntimeError("Kode video tidak ditemukan dari link ini")

        title = find_javbos_title(content)
        stream = PODJAV_STREAM.format(code=code)

        info("Title", title)
        info("Code", code)
        info("Stream", stream)
        warn(f"Subtitle: {subtitle_page_url(url)} (buka dan unduh manual)")

        output_path = os.path.join(get_output_dir("javbos"), f"{title}.mp4")

        console.print(
            make_panel(
                f"""
[bold white]Title[/bold white]   : [bold {THEME_ACCENT}]{title}[/bold {THEME_ACCENT}]
[bold white]Output[/bold white]  : [bold {THEME_WARN}]{output_path}[/bold {THEME_WARN}]
""".strip(),
                title="[bold italic white] JAVBOS READY [/bold italic white]",
                border_style=THEME_ACCENT
            )
        )

        stream_headers = {**headers, "Referer": "https://play.podjav.tv/", "Origin": "https://play.podjav.tv"}
        if not download_video(stream, output_path, stream_headers) is True:
            error("Download video gagal")
            return False

        sub_path = ask_subtitle_path()
        if sub_path:
            if not os.path.exists(sub_path):
                warn(f"File subtitle tidak ditemukan: {sub_path}. Video tetap tersimpan tanpa subtitle.")
            else:
                mux_subtitle(output_path, sub_path)

        return True

    except RuntimeError as exc:
        error(str(exc))
        return False

    except requests.RequestException as exc:
        error(f"JAVBOS request error: {exc}")
        return False

    except KeyboardInterrupt:
        raise

    except Exception as exc:
        error(f"JAVBOS error: {exc}")
        return False
