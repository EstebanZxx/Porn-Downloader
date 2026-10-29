from core.common import *


# ──────────────── NJAVTV EXTRACTOR ────────────────

def extract_njav_video_id(file_path):
    with open(
        file_path,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:
        content = f.read()

    patterns = [
        r'https:\\/\\/nineyu\.com\\/([0-9a-fA-F\-]{36})\\/seek\\/_\d+\.jpg',
        r'https://nineyu\.com/([0-9a-fA-F\-]{36})/seek/_\d+\.jpg',
        r'nineyu\.com[\\/]+([0-9a-fA-F\-]{36})',
        r'surrit\.com[\\/]+([0-9a-fA-F\-]{36})'
    ]

    for pattern in patterns:
        match = re.search(pattern, content)

        if match:
            return match.group(1)

    return None


# ──────────────── NJAV QUALITY DETECTION ────────────────

def extract_njav_qualities(video_id):
    available = {}

    table = make_table(
        title="[bold italic white]AVAILABLE QUALITY[/bold italic white]",
        border_style=THEME_ORANGE
    )

    table.add_column("No", ratio=1, justify="center")
    table.add_column("Quality", ratio=3)
    table.add_column("Status", ratio=3)

    with console.status(
        f"[bold {THEME_ACCENT}]Checking available qualities...[/bold {THEME_ACCENT}]"
    ):
        for i, quality in enumerate(POTENTIAL_QUALITY, start=1):
            m3u8_url = (
                f"https://surrit.com/{video_id}/"
                f"{quality}/video.m3u8"
            )

            try:
                text = get_m3u8_text(
                    m3u8_url,
                    request_headers=NJAV_HEADERS
                )

                if text:
                    available[quality] = m3u8_url

                    table.add_row(
                        str(i),
                        quality,
                        f"[bold {THEME_GREEN}]VALID[/bold {THEME_GREEN}]"
                    )
                else:
                    table.add_row(
                        str(i),
                        quality,
                        f"[bold {THEME_RED}]NO[/bold {THEME_RED}]"
                    )

            except Exception as exc:
                table.add_row(
                    str(i),
                    quality,
                    f"[bold {THEME_RED}]ERROR[/bold {THEME_RED}]"
                )

                console.print(
                    f"[dim]{quality}: {exc}[/dim]"
                )

    console.print(table)

    return available


# ──────────────── PROCESS NJAVTV ────────────────

def process_njav(url):
    section("Fetching NJAVTV")

    try:
        html_file = save_html(
            url,
            "njav.html",
            NJAV_HEADERS
        )

        title = extract_title(html_file)
        video_id = extract_njav_video_id(html_file)

        if not video_id:
            error("No video ID found")
            return False

        info("Title", title)
        info("Video ID", video_id)

        section("Quality Detection")

        qualities = extract_njav_qualities(video_id)

        if not qualities:
            error("No valid video qualities found")
            return False

        selected_quality = next(
            (
                q for q in POTENTIAL_QUALITY
                if q in qualities
            ),
            None
        )

        if selected_quality is None:
            error("No quality selected")
            return False

        m3u8 = qualities[selected_quality]

        output_path = os.path.join(
            get_output_dir("njav"),
            f"{title}.mp4"
        )

        console.print(
            make_panel(
                f"""
[bold white]Title[/bold white]   : [bold {THEME_ACCENT}]{title}[/bold {THEME_ACCENT}]
[bold white]Quality[/bold white] : [bold {THEME_GREEN}]{selected_quality}[/bold {THEME_GREEN}]
[bold white]Output[/bold white]  : [bold {THEME_WARN}]{output_path}[/bold {THEME_WARN}]
""".strip(),
                title="[bold italic white] NJAV READY [/bold italic white]"
            )
        )

        return download_video(
            m3u8,
            output_path,
            NJAV_HEADERS
        ) is True

    except requests.RequestException as exc:
        error(f"NJAVTV request error: {exc}")
        return False

    except KeyboardInterrupt:
        error("Download dibatalkan")
        return False

    except Exception as exc:
        error(f"NJAVTV error: {exc}")
        return False
