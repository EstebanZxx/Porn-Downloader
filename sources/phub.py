from core.common import *


# ──────────────── PHUB EXTRACTOR ────────────────


def extract_phub_data(file_path):
    with open(
        file_path,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:
        content = f.read()

    content = html.unescape(content)

    # ───────── EXTRACT TITLE ─────────
    title = "phub_video"

    title_patterns = [
        r'"video_title"\s*:\s*"((?:\\.|[^"\\])*)"',
        r'<title[^>]*>(.*?)</title>',
        r'property="og:title"\s+content="([^"]+)"'
    ]

    for pattern in title_patterns:
        match = re.search(
            pattern,
            content,
            re.DOTALL | re.IGNORECASE
        )

        if match:
            title = match.group(1)

            title = (
                title
                .replace(r"\/", "/")
                .replace(r"\u0026", "&")
                .replace(r"\"", '"')
            )

            title = safe_filename(
                re.sub(r"<.*?>", "", title)
            )
            break

    # ───────── EXTRACT HLS VIDEO URLS ─────────
    qualities = {}

    # Mendukung URL JSON biasa dan escaped slash:
    # https://example.com/master.m3u8
    # https:\/\/example.com\/master.m3u8
    pattern = (
        r'"videoUrl"\s*:\s*'
        r'"((?:\\.|[^"\\])*)"'
    )

    matches = re.finditer(
        pattern,
        content,
        re.IGNORECASE
    )

    for match in matches:
        raw_url = match.group(1)

        # Normalisasi escaped JSON URL
        url = (
            raw_url
            .replace(r"\/", "/")
            .replace(r"\u0026", "&")
            .replace("&amp;", "&")
        )

        if not url.startswith(("https://", "http://")):
            continue

        if ".m3u8" not in url.lower():
            continue

        # Ambil kualitas dari nama file URL,
        # misalnya 1080P_4000K atau 720P_2000K.
        quality_match = re.search(
            r"_(\d{3,4})P(?:_|/|\.|$)",
            url,
            re.IGNORECASE
        )

        # Fallback jika format URL berbeda.
        if not quality_match:
            quality_match = re.search(
                r"/(\d{3,4})P[_/]",
                url,
                re.IGNORECASE
            )

        if not quality_match:
            continue

        quality = int(quality_match.group(1))
        qualities[quality] = url

    if not qualities:
        return None, None, None

    # Pilih kualitas tertinggi yang ditemukan
    best_quality = max(qualities)

    return (
        title,
        best_quality,
        qualities[best_quality]
    )


# ──────────────── PROCESS PHUB ────────────────

def process_phub(url):
    section("Fetching PHUB")

    try:
        html_file = save_html(
            url,
            "phub.html",
            PHUB_HEADERS
        )

        title, quality, m3u8 = extract_phub_data(html_file)

        if not m3u8:
            error("No PHUB stream found")
            return False

        output_path = os.path.join(
            get_output_dir("phub"),
            f"{title}.mp4"
        )

        console.print(
            make_panel(
                f"""
[bold white]Title[/bold white]   : [bold {THEME_ACCENT}]{title}[/bold {THEME_ACCENT}]
[bold white]Quality[/bold white] : [bold {THEME_GREEN}]{quality}p[/bold {THEME_GREEN}]
[bold white]Output[/bold white]  : [bold {THEME_WARN}]{output_path}[/bold {THEME_WARN}]
""".strip(),
                title="[bold italic white] PHUB READY [/bold italic white]",
                border_style=THEME_ORANGE
            )
        )

        return download_video(
            m3u8,
            output_path,
            PHUB_HEADERS
        ) is True

    except requests.RequestException as exc:
        error(f"PHUB request error: {exc}")
        return False

    except KeyboardInterrupt:
        error("Download dibatalkan")
        return False

    except Exception as exc:
        error(f"PHUB error: {exc}")
        return False
