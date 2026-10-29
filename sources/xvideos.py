from core.common import *


# ──────────────── XVIDEOS EXTRACTOR ────────────────

def extract_xvideos_title(file_path):
    with open(
        file_path,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:
        content = f.read()

    match = re.search(
        r"html5player\.setVideoTitle\('((?:\\.|[^'\\])*)'\)",
        content
    )

    if match:
        title = match.group(1).replace(r"\'", "'")
        return safe_filename(html.unescape(title))

    # Fallback ke extractor title generik, buang suffix " - XVIDEOS.COM"
    title = extract_title(file_path)
    title = re.sub(
        r"\s*-\s*XVIDEOS\.COM\s*$",
        "",
        title,
        flags=re.IGNORECASE
    )

    return safe_filename(title)


def extract_xvideos_hls(file_path):
    with open(
        file_path,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:
        content = f.read()

    match = re.search(
        r"html5player\.setVideoHLS\('([^']+)'\)",
        content
    )

    if match:
        return match.group(1).replace(r"\/", "/")

    return None


# ──────────────── PROCESS XVIDEOS ────────────────

def process_xvideos(url):
    section("Fetching Xvideos")

    try:
        xv_headers = build_dynamic_headers(url)

        html_file = save_html(
            url,
            "xvideos.html",
            xv_headers
        )

        title = extract_xvideos_title(html_file)
        master_m3u8 = extract_xvideos_hls(html_file)

        if not master_m3u8:
            error("No HLS stream found")
            return False

        real_m3u8 = resolve_master_m3u8(master_m3u8, xv_headers)

        if not real_m3u8:
            error("Failed resolving master m3u8")
            return False

        quality_match = re.search(r"hls-(\d+p)", real_m3u8)
        selected_quality = (
            quality_match.group(1) if quality_match else "auto"
        )

        info("Title", title)
        info("Quality", selected_quality)

        output_path = os.path.join(
            get_output_dir("xvideos"),
            f"{title}.mp4"
        )

        console.print(
            make_panel(
                f"""
[bold white]Title[/bold white]   : [bold {THEME_ACCENT}]{title}[/bold {THEME_ACCENT}]
[bold white]Quality[/bold white] : [bold {THEME_GREEN}]{selected_quality}[/bold {THEME_GREEN}]
[bold white]Output[/bold white]  : [bold {THEME_WARN}]{output_path}[/bold {THEME_WARN}]
""".strip(),
                title="[bold italic white] XVIDEOS READY [/bold italic white]",
                border_style=THEME_ORANGE
            )
        )

        return download_video(
            real_m3u8,
            output_path,
            xv_headers
        ) is True

    except requests.RequestException as exc:
        error(f"Xvideos request error: {exc}")
        return False

    except KeyboardInterrupt:
        error("Download dibatalkan")
        return False

    except Exception as exc:
        error(f"Xvideos error: {exc}")
        return False
