from core.common import *


# ──────────────── HAMSTER EXTRACTOR ────────────────

def extract_hamster_template(file_path):
    with open(
        file_path,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:
        content = f.read()

    content = html.unescape(content)

    # Cari link preload HLS yang mengandung placeholder _TPL_
    pattern = r'href="([^"]*media=hls4[^"]*_TPL_[^"]*\.m3u8)"'

    match = re.search(pattern, content, re.IGNORECASE)

    if not match:
        return None

    return match.group(1)


def extract_hamster_qualities(template_url):
    """
    Parse segmen 'multi=WIDTHxHEIGHT:LABEL:,...' pada template_url,
    lalu hasilkan dict {height: (label, resolved_url)} dengan
    _TPL_ diganti oleh LABEL masing-masing kualitas.
    """
    match = re.search(r'multi=([^/]+)/', template_url)

    if not match:
        return {}

    multi_segment = match.group(1)
    qualities = {}

    for entry in multi_segment.split(","):
        entry = entry.strip()

        if not entry:
            continue

        parts = entry.split(":")

        if len(parts) < 2:
            continue

        resolution = parts[0]
        label = parts[1]

        res_match = re.match(r"(\d+)x(\d+)", resolution)

        if not res_match or not label:
            continue

        height = int(res_match.group(2))
        resolved_url = template_url.replace("_TPL_", label)

        qualities[height] = (label, resolved_url)

    return qualities


# ──────────────── PROCESS HAMSTER ────────────────

def process_hamster(url):
    section("Fetching Hamster")

    try:
        hamster_headers = build_dynamic_headers(url)

        html_file = save_html(
            url,
            "hamster.html",
            hamster_headers
        )

        title = extract_title(html_file)
        template_url = extract_hamster_template(html_file)

        if not template_url:
            error("No HLS template URL found")
            return False

        qualities = extract_hamster_qualities(template_url)

        if not qualities:
            error("No valid video qualities found")
            return False

        best_height = max(qualities)
        selected_label, m3u8 = qualities[best_height]

        info("Title", title)
        info("Quality", selected_label)

        output_path = os.path.join(
            get_output_dir("hamster"),
            f"{title}.mp4"
        )

        console.print(
            make_panel(
                f"""
[bold white]Title[/bold white]   : [bold {THEME_ACCENT}]{title}[/bold {THEME_ACCENT}]
[bold white]Quality[/bold white] : [bold {THEME_GREEN}]{selected_label}[/bold {THEME_GREEN}]
[bold white]Output[/bold white]  : [bold {THEME_WARN}]{output_path}[/bold {THEME_WARN}]
""".strip(),
                title="[bold italic white] HAMSTER READY [/bold italic white]",
                border_style=THEME_ACCENT
            )
        )

        return download_video(
            m3u8,
            output_path,
            hamster_headers
        ) is True

    except requests.RequestException as exc:
        error(f"Hamster request error: {exc}")
        return False

    except KeyboardInterrupt:
        error("Download dibatalkan")
        return False

    except Exception as exc:
        error(f"Hamster error: {exc}")
        return False
