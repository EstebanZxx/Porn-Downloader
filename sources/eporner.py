from core.common import *


# ──────────────── EPORNER EXTRACTOR ────────────────

def extract_eporner_data(file_path):
    with open(
        file_path,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:
        content = f.read()

    content = html.unescape(content)

    # ───────── TITLE ─────────
    title = "eporner_video"

    title_match = re.search(
        r"<title[^>]*>(.*?)</title>",
        content,
        re.DOTALL | re.IGNORECASE
    )

    if title_match:
        raw_title = re.sub(r"<.*?>", "", title_match.group(1))
        raw_title = re.sub(
            r"\s*-\s*EPORNER\s*$",
            "",
            raw_title,
            flags=re.IGNORECASE
        )
        title = safe_filename(raw_title)

    # ───────── DOWNLOAD LINKS (MP4 LANGSUNG) ─────────
    qualities = {}

    pattern = r'href="(/dload/[^"]+?-(\d+)p(-av1)?\.mp4)"'

    for m in re.finditer(pattern, content):
        path = m.group(1)
        quality_height = int(m.group(2))
        codec = "av1" if m.group(3) else "h264"

        full_url = urljoin("https://www.eporner.com", path)

        qualities.setdefault(quality_height, {})[codec] = full_url

    if not qualities:
        return title, None, None, None

    best_height = max(qualities)
    codecs = qualities[best_height]

    # Prioritaskan h264 (lebih kompatibel), fallback ke AV1
    codec_used = "h264" if "h264" in codecs else "av1"
    best_url = codecs[codec_used]

    return title, best_url, best_height, codec_used


# ──────────────── PROCESS EPORNER ────────────────

def process_eporner(url):
    section("Fetching Eporner")

    try:
        ep_headers = build_dynamic_headers(url)

        html_file = save_html(
            url,
            "eporner.html",
            ep_headers
        )

        title, mp4_url, quality_height, codec_used = (
            extract_eporner_data(html_file)
        )

        if not mp4_url:
            error("No download link found")
            return False

        quality_label = f"{quality_height}p ({codec_used})"

        info("Title", title)
        info("Quality", quality_label)

        output_path = os.path.join(
            get_output_dir("eporner"),
            f"{title}.mp4"
        )

        console.print(
            make_panel(
                f"""
[bold white]Title[/bold white]   : [bold {THEME_ACCENT}]{title}[/bold {THEME_ACCENT}]
[bold white]Quality[/bold white] : [bold {THEME_GREEN}]{quality_label}[/bold {THEME_GREEN}]
[bold white]Output[/bold white]  : [bold {THEME_WARN}]{output_path}[/bold {THEME_WARN}]
""".strip(),
                title="[bold italic white] EPORNER READY [/bold italic white]",
                border_style=THEME_WARN
            )
        )

        success = download_direct_file(
            mp4_url,
            output_path,
            ep_headers
        )

        if not success:
            error("Download gagal")
            return False

        size_mb = os.path.getsize(output_path) / 1024 / 1024

        result = make_table(
            title="[bold italic white]DOWNLOAD COMPLETED[/bold italic white]"
        )

        result.add_column("Item", ratio=2)
        result.add_column("Value", ratio=6)

        result.add_row("Saved", output_path)
        result.add_row("Size", f"{size_mb:.2f} MB")

        console.print(result)

        return True

    except requests.RequestException as exc:
        error(f"Eporner request error: {exc}")
        return False

    except KeyboardInterrupt:
        error("Download dibatalkan")
        return False

    except Exception as exc:
        error(f"Eporner error: {exc}")
        return False
