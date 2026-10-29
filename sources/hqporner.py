from core.common import *


# ──────────────── HQPORNER EXTRACTOR ────────────────

def extract_hqporner_meta(file_path):
    """
    HQporner cuma halaman aggregator berisi iframe embed ke player
    mydaddy.cc. Fungsi ini ambil judul + URL iframe tersebut.
    """
    with open(
        file_path,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:
        content = f.read()

    content = html.unescape(content)

    # ───────── TITLE ─────────
    title = "hqporner_video"

    title_match = re.search(
        r"<title[^>]*>(.*?)</title>",
        content,
        re.DOTALL | re.IGNORECASE
    )

    if title_match:
        raw_title = re.sub(r"<.*?>", "", title_match.group(1))
        raw_title = re.sub(
            r"\s*-\s*HQporner\.com\s*$",
            "",
            raw_title,
            flags=re.IGNORECASE
        )
        title = safe_filename(raw_title)

    # ───────── IFRAME PLAYER (mydaddy.cc) ─────────
    iframe_match = re.search(
        r'<iframe[^>]+src="(//[^"]*mydaddy\.cc/video/[^"]+)"',
        content,
        re.IGNORECASE
    )

    iframe_url = None

    if iframe_match:
        iframe_url = "https:" + iframe_match.group(1)

    return title, iframe_url


def extract_hqporner_qualities(file_path):
    """
    Parse halaman player mydaddy.cc untuk ambil semua link mp4
    (360/720/1080) yang ditulis di dalam fungsi JS do_pl().
    """
    with open(
        file_path,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:
        content = f.read()

    content = html.unescape(content)
    content = content.replace("\\/", "/")

    # Pola longgar: semua URL mp4 yang berakhiran /<angka>.mp4 (360.mp4, 1080.mp4, dst)
    pattern = r'((?:https?:)?//[^\s"\'<>]+?/(\d{3,4})\.mp4)'

    qualities = {}

    for m in re.finditer(pattern, content, re.IGNORECASE):
        full_url = m.group(1)
        height = int(m.group(2))

        if full_url.startswith("//"):
            full_url = "https:" + full_url

        qualities[height] = full_url

    if not qualities:
        mp4_count = content.lower().count(".mp4")
        print(f"[DEBUG] player HTML size: {len(content)} chars, jumlah '.mp4': {mp4_count}")
        print(f"[DEBUG] potongan awal: {content[:300]!r}")

    return qualities


# ──────────────── PROCESS HQPORNER ────────────────

def process_hqporner(url):
    section("Fetching HQporner")

    try:
        hq_headers = build_dynamic_headers(url)

        html_file = save_html(
            url,
            "hqporner.html",
            hq_headers
        )

        title, iframe_url = extract_hqporner_meta(html_file)

        if not iframe_url:
            error("No embedded player found")
            return False

        info("Title", title)
        info("Player", iframe_url)

        section("Fetching Player (mydaddy.cc)")

        player_headers = build_dynamic_headers(iframe_url)

        player_file = save_html(
            iframe_url,
            "hqporner_player.html",
            player_headers
        )

        qualities = extract_hqporner_qualities(player_file)

        if not qualities:
            error("No video quality links found")
            return False

        best_height = max(qualities)
        mp4_url = qualities[best_height]
        quality_label = f"{best_height}p"

        info("Quality", quality_label)

        output_path = os.path.join(
            get_output_dir("hqporner"),
            f"{title}.mp4"
        )

        console.print(
            make_panel(
                f"""
[bold white]Title[/bold white]   : [bold {THEME_ACCENT}]{title}[/bold {THEME_ACCENT}]
[bold white]Quality[/bold white] : [bold {THEME_GREEN}]{quality_label}[/bold {THEME_GREEN}]
[bold white]Output[/bold white]  : [bold {THEME_WARN}]{output_path}[/bold {THEME_WARN}]
""".strip(),
                title="[bold italic white] HQPORNER READY [/bold italic white]",
                border_style=THEME_ORANGE
            )
        )

        success = download_direct_file(
            mp4_url,
            output_path,
            player_headers
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
        error(f"HQporner request error: {exc}")
        return False

    except KeyboardInterrupt:
        error("Download dibatalkan")
        return False

    except Exception as exc:
        error(f"HQporner error: {exc}")
        return False
