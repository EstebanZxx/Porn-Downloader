
import os
import re
import sys
import html
import uuid
import time
import shutil
import requests
import subprocess

from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

# ──────────────── AUTO INSTALL RICH ────────────────
try:
    from rich.console import Console
    from rich.text import Text
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
        DownloadColumn,
        TransferSpeedColumn
    )
    from rich.prompt import Prompt
    from rich import box as rich_box

except ImportError:
    print("Installing rich...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "rich"]
    )

    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.progress import (
        Progress,
        SpinnerColumn,
        BarColumn,
        TextColumn,
        TimeElapsedColumn,
        TimeRemainingColumn,
        DownloadColumn,
        TransferSpeedColumn
    )
    from rich.prompt import Prompt
    from rich import box as rich_box


# ──────────────── CONFIG ────────────────

console = Console()

DOWNLOAD_DIR = "/sdcard/JAV"
TEMP_DIR = "/sdcard/JAV/.temp"
MAX_WORKERS = 10

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 10; Mobile) "
        "AppleWebKit/537.36 Chrome/120 Safari/537.36"
    ),
    "Accept": "*/*",
    "Connection": "keep-alive"
}

# Header khusus NJAVTV
NJAV_HEADERS = {
    **headers,
    "Referer": "https://njavtv.com/",
    "Origin": "https://njavtv.com"
}

# Header khusus PHUB
PHUB_HEADERS = {
    **headers,
    "Referer": "https://www.pornhub.com/",
    "Origin": "https://www.pornhub.com"
}


def build_dynamic_headers(url):
    """
    Header dengan Referer/Origin mengikuti domain dari url itu sendiri.
    Dipakai untuk sumber yang punya banyak domain mirror (mis. Hamster).
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.hostname}"

    return {
        **headers,
        "Referer": origin + "/",
        "Origin": origin
    }


POTENTIAL_QUALITY = [
    "1080p",
    "1280p",
    "1280x720",
    "720p",
    "842x480",
    "480p",
    "360p"
]

# Subfolder output per sumber/mode
SOURCE_FOLDERS = {
    "njav": "NJAV",
    "phub": "PHUB",
    "hamster": "XHAMSTER",
    "xvideos": "XVIDEOS",
    "eporner": "EPORNER",
    "hqporner": "HQPORNER",
    "manual": "MANUAL"
}


def get_output_dir(source_key):
    folder = SOURCE_FOLDERS.get(source_key, "MANUAL")
    path = os.path.join(DOWNLOAD_DIR, folder)
    os.makedirs(path, exist_ok=True)
    return path


# ──────────────── THEME ────────────────

THEME_BORDER = "spring_green2"
THEME_ACCENT = "aquamarine1"
THEME_TEXT = "white"
THEME_DIM = "grey62"
THEME_WARN = "light_goldenrod1"
THEME_ORANGE = "salmon1"
THEME_GREEN = "medium_spring_green"
THEME_RED = "red1"


# ──────────────── UI ────────────────

def term_width():
    return shutil.get_terminal_size((80, 20)).columns


def full_width():
    return max(40, term_width() - 2)


def clear():
    os.system("clear")



def run_speedtest():
    import time

    try:
        import speedtest

        clear()
        banner()

        console.print(
            Panel(
                Text.from_markup(
                    "[bold cyan]⚡ NETWORK PERFORMANCE[/bold cyan]\n"
                    "[dim]INTERNET DIAGNOSTICS • SPEEDTEST[/dim]"
                ),
                border_style="bright_cyan",
                padding=(1, 2),
                expand=True
            )
        )

        with console.status(
            "[bold cyan]Mencari server terbaik...[/bold cyan]",
            spinner="dots"
        ):
            st = speedtest.Speedtest(secure=True)
            server = st.get_best_server()

        with console.status(
            "[bold green]Mengukur kecepatan download...[/bold green]",
            spinner="dots"
        ):
            download_speed = st.download() / 1_000_000

        with console.status(
            "[bold magenta]Mengukur kecepatan upload...[/bold magenta]",
            spinner="dots"
        ):
            upload_speed = st.upload() / 1_000_000

        result = st.results
        client = result.client or {}
        server = result.server or {}

        # ───────── ISP INFORMATION ─────────
        isp = client.get("isp", "Tidak diketahui")
        country = client.get("country", "Tidak diketahui")
        server_name = server.get("name", "Unknown")
        server_sponsor = server.get("sponsor", "Unknown")
        server_country = server.get("country", "Unknown")
        ping = result.ping

        # ───────── CONNECTION DETAILS ─────────
        details = Table.grid(padding=(0, 2))
        details.add_column(style="dim", width=18)
        details.add_column(style="bold white")

        details.add_row("Internet Provider", str(isp))
        details.add_row("Negara koneksi", str(country))
        details.add_row("Test server", str(server_name))
        details.add_row("Server provider", str(server_sponsor))
        details.add_row("Lokasi server", str(server_country))

        console.print()
        console.print(
            Panel(
                details,
                title="[bold cyan]CONNECTION DETAILS[/bold cyan]",
                border_style="cyan",
                padding=(1, 2)
            )
        )

        # ───────── SPEED RESULTS ─────────
        speeds = Table(
            show_header=True,
            header_style="bold white",
            border_style="bright_black",
            expand=True
        )
        speeds.add_column("METRIC", ratio=2)
        speeds.add_column("RESULT", justify="right", ratio=3)

        speeds.add_row(
            "[bold cyan]↓ Download[/bold cyan]",
            f"[bold cyan]{download_speed:,.2f} Mbps[/bold cyan]"
        )
        speeds.add_row(
            "[bold magenta]↑ Upload[/bold magenta]",
            f"[bold magenta]{upload_speed:,.2f} Mbps[/bold magenta]"
        )
        speeds.add_row(
            "[bold yellow]◉ Ping[/bold yellow]",
            f"[bold yellow]{ping:.2f} ms[/bold yellow]"
        )

        console.print(
            Panel(
                speeds,
                title="[bold green]SPEED TEST RESULTS[/bold green]",
                border_style="green",
                padding=(1, 2)
            )
        )

        console.print(
            Panel(
                Text.from_markup(
                    "[bold green]✓ TEST COMPLETED[/bold green]\n"
                    "[dim]Pengujian selesai dengan sukses.[/dim]"
                ),
                border_style="green",
                padding=(0, 2),
                expand=True
            )
        )

    except ImportError:
        error("Module speedtest-cli belum terpasang")
        info("Install dengan: pip install speedtest-cli")

    except Exception as exc:
        error(f"Speed test gagal: {exc}")

    finally:
        console.print()
        console.print(
            "[dim]Tekan ENTER untuk kembali ke menu URL...[/dim]"
        )

        

def make_panel(content, title="", border_style=THEME_BORDER):
    return Panel(
        content,
        title=title,
        border_style=border_style,
        box=rich_box.SQUARE,
        width=full_width(),
        padding=(1, 2)
    )


def make_table(title="", border_style=THEME_BORDER):
    return Table(
        title=title,
        box=rich_box.SQUARE,
        border_style=border_style,
        header_style="bold white",
        title_style="bold italic white",
        expand=True,
        width=full_width()
    )


def banner():
    session = str(uuid.uuid4())[:8]

    text = f"""
[bold italic white]ULTIMATE VIDEO DOWNLOADER[/bold italic white]

[bold {THEME_ACCENT}]NJAVTV • PHUB • HAMSTER • XVIDEOS[/bold {THEME_ACCENT}]
[bold {THEME_ACCENT}]EPORNER • HQPORNER • HLS[/bold {THEME_ACCENT}]

[bold white]Directory[/bold white] : [bold {THEME_GREEN}]{DOWNLOAD_DIR}[/bold {THEME_GREEN}]
[bold white]Workers[/bold white]   : [bold {THEME_GREEN}]{MAX_WORKERS}[/bold {THEME_GREEN}]
[bold white]Session[/bold white]   : [bold {THEME_DIM}]{session}[/bold {THEME_DIM}]
"""

    console.print(
        make_panel(
            text.strip(),
            title="[bold italic white] PREMIUM CLI [/bold italic white]"
        )
    )


def section(title):
    console.print()
    console.rule(
        f"[bold italic white]{title.upper()}[/bold italic white]",
        style=THEME_DIM
    )


def info(label, value):
    console.print(
        f"[bold white]{label:<12}[/bold white] : "
        f"[bold {THEME_ACCENT}]{value}[/bold {THEME_ACCENT}]"
    )


def ok(text):
    console.print(
        f"[bold {THEME_GREEN}]✓[/bold {THEME_GREEN}] "
        f"[bold white]{text}[/bold white]"
    )


def warn(text):
    console.print(
        f"[bold {THEME_WARN}]![/bold {THEME_WARN}] "
        f"[bold {THEME_WARN}]{text}[/bold {THEME_WARN}]"
    )


def error(text):
    console.print(
        f"[bold {THEME_RED}]✗[/bold {THEME_RED}] "
        f"[bold {THEME_RED}]{text}[/bold {THEME_RED}]"
    )


def safe_filename(name):
    name = str(name)
    name = name.encode("utf-8", "ignore").decode("utf-8", "ignore")
    name = re.sub(r'[\ud800-\udfff]', '', name)
    name = re.sub(r'[\\/:*?"<>|]', "_", name)
    name = re.sub(r"\s+", " ", name).strip()

    return name if name else "video"


# ──────────────── COMMON / HTTP ────────────────

def save_html(url, filename, request_headers=None):
    r = requests.get(
        url,
        headers=request_headers or headers,
        timeout=30
    )
    r.raise_for_status()

    with open(filename, "w", encoding="utf-8") as f:
        f.write(r.text)

    return filename


def get_m3u8_text(url, request_headers=None):
    try:
        r = requests.get(
            url,
            headers=request_headers or headers,
            timeout=30
        )

        if r.status_code != 200:
            return None

        text = r.text.lstrip("\ufeff").strip()

        if not text.startswith("#EXTM3U"):
            return None

        return text

    except requests.RequestException:
        return None


def resolve_master_m3u8(m3u8_url, request_headers=None):
    text = get_m3u8_text(m3u8_url, request_headers)

    if not text:
        return None

    if "#EXT-X-STREAM-INF" not in text:
        return m3u8_url

    lines = text.splitlines()
    variants = []

    for i, line in enumerate(lines):
        line = line.strip()

        if not line.startswith("#EXT-X-STREAM-INF"):
            continue

        res_match = re.search(
            r"RESOLUTION=\d+x(\d+)",
            line
        )
        bandwidth_match = re.search(
            r"BANDWIDTH=(\d+)",
            line
        )

        height = int(res_match.group(1)) if res_match else 0
        bandwidth = (
            int(bandwidth_match.group(1))
            if bandwidth_match else 0
        )

        for next_line in lines[i + 1:]:
            next_line = next_line.strip()

            if not next_line:
                continue

            if next_line.startswith("#"):
                continue

            variant_url = urljoin(m3u8_url, next_line)
            variants.append((height, bandwidth, variant_url))
            break

    if not variants:
        return m3u8_url

    variants.sort(
        key=lambda item: (item[0], item[1]),
        reverse=True
    )

    return variants[0][2]


def parse_segments(m3u8_url, m3u8_text):
    segments = []

    for line in m3u8_text.splitlines():
        line = line.strip()

        if not line:
            continue

        # Dukungan initialization map pada HLS
        if line.startswith("#EXT-X-MAP"):
            match = re.search(r'URI="([^"]+)"', line)

            if match:
                segments.append(
                    urljoin(m3u8_url, match.group(1))
                )

            continue

        if line.startswith("#"):
            continue

        segments.append(urljoin(m3u8_url, line))

    return segments


def extract_title(file_path):
    with open(
        file_path,
        "r",
        encoding="utf-8",
        errors="ignore"
    ) as f:
        content = f.read()

    patterns = [
        r'<h1.*?>(.*?)</h1>',
        r"<title>(.*?)</title>",
        r'property="og:title"\s+content="([^"]+)"'
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            content,
            re.DOTALL | re.IGNORECASE
        )

        if match:
            title = html.unescape(match.group(1))
            title = re.sub(r"<.*?>", "", title)
            return safe_filename(title)

    return "video"


# ──────────────── DOWNLOAD WORKER ────────────────

def download_one_segment(
    idx,
    seg_url,
    seg_file,
    request_headers=None,
    retries=5
):
    request_headers = request_headers or headers
    tmp_file = seg_file + ".part"

    for attempt in range(1, retries + 1):
        try:
            with requests.get(
                seg_url,
                headers=request_headers,
                timeout=45,
                stream=True
            ) as r:

                if r.status_code != 200:
                    if r.status_code not in (403, 404, 410, 416):
                        time.sleep(1)
                        continue

                    return False

                total = 0

                with open(tmp_file, "wb") as f:
                    for chunk in r.iter_content(
                        chunk_size=1024 * 256
                    ):
                        if chunk:
                            f.write(chunk)
                            total += len(chunk)

            if total > 0:
                os.replace(tmp_file, seg_file)
                return True

        except requests.RequestException:
            time.sleep(1)

        except OSError:
            time.sleep(1)

        finally:
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except OSError:
                    pass

    return False


# ──────────────── DOWNLOAD VIDEO ────────────────

def download_video(
    m3u8_url,
    output_path,
    request_headers=None
):
    request_headers = request_headers or headers

    real_m3u8 = resolve_master_m3u8(
        m3u8_url,
        request_headers
    )

    if not real_m3u8:
        error("Failed resolving master m3u8")
        return False

    info("Real M3U8", real_m3u8)

    m3u8_text = get_m3u8_text(
        real_m3u8,
        request_headers
    )

    if not m3u8_text:
        error("Failed getting m3u8")
        return False

    segments = parse_segments(real_m3u8, m3u8_text)

    if not segments:
        error("No segments found")
        return False

    total = len(segments)

    info("Segments", total)
    info("Workers", MAX_WORKERS)

    os.makedirs(TEMP_DIR, exist_ok=True)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    seg_dir = os.path.join(
        TEMP_DIR,
        str(uuid.uuid4())
    )

    os.makedirs(seg_dir, exist_ok=True)

    progress = Progress(
        SpinnerColumn(style=THEME_ACCENT),
        TextColumn(
            f"[bold {THEME_ACCENT}]{{task.description}}[/bold {THEME_ACCENT}]"
        ),
        BarColumn(
            complete_style=THEME_ACCENT,
            finished_style=THEME_GREEN,
            pulse_style=THEME_WARN
        ),
        TextColumn(
            "[bold white]{task.percentage:>6.2f}%[/bold white]"
        ),
        TextColumn(
            f"[bold {THEME_WARN}]{{task.completed}}/{{task.total}}[/bold {THEME_WARN}]"
        ),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        expand=True
    )

    failed = 0

    with progress:
        task_id = progress.add_task(
            "Downloading Segments",
            total=total
        )

        with ThreadPoolExecutor(
            max_workers=MAX_WORKERS
        ) as executor:

            futures = []

            for idx, seg_url in enumerate(
                segments,
                start=1
            ):
                seg_file = os.path.join(
                    seg_dir,
                    f"{idx:05d}.ts"
                )

                futures.append(
                    executor.submit(
                        download_one_segment,
                        idx,
                        seg_url,
                        seg_file,
                        request_headers
                    )
                )

            for future in as_completed(futures):
                try:
                    if not future.result():
                        failed += 1
                except Exception:
                    failed += 1

                progress.update(task_id, advance=1)

    if failed:
        error(
            f"{failed} segments failed. "
            "Conversion dibatalkan."
        )
        return False

    section("Merging Segments")

    ts_path = os.path.join(
        TEMP_DIR,
        f"{uuid.uuid4()}.ts"
    )

    try:
        with open(ts_path, "wb") as out:
            for idx in range(1, total + 1):
                seg_file = os.path.join(
                    seg_dir,
                    f"{idx:05d}.ts"
                )

                if not os.path.exists(seg_file):
                    error(f"Segment hilang: {idx}")
                    return False

                with open(seg_file, "rb") as f:
                    shutil.copyfileobj(f, out)

    except OSError as exc:
        error(f"Gagal menggabungkan segmen: {exc}")
        return False

    if os.path.getsize(ts_path) == 0:
        error("Merged TS file kosong")
        return False

    section("FFMPEG")

    command = [
        "ffmpeg",
        "-y",
        "-i", ts_path,
        "-c", "copy",
        "-bsf:a", "aac_adtstoasc",
        output_path
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    last_output = []

    with Progress(
        SpinnerColumn(style=THEME_ACCENT),
        TextColumn(
            f"[bold {THEME_ACCENT}]{{task.description}}[/bold {THEME_ACCENT}]"
        ),
        TimeElapsedColumn(),
        console=console,
        expand=True
    ) as progress:

        progress.add_task(
            "Converting TS to MP4",
            total=None
        )

        for line in process.stdout:
            line = line.strip()

            if line:
                last_output.append(line)

                if len(last_output) > 15:
                    last_output.pop(0)

    process.wait()

    if (
        process.returncode != 0
        or not os.path.exists(output_path)
        or os.path.getsize(output_path) == 0
    ):
        error("FFmpeg failed")

        for line in last_output:
            console.print(f"[dim]{line}[/dim]")

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

    # ───────── CLEANUP TEMP FILES ─────────
    try:
        shutil.rmtree(seg_dir, ignore_errors=True)

        if os.path.exists(ts_path):
            os.remove(ts_path)

        ok("Temporary files cleaned successfully")

    except OSError as exc:
        warn(f"Temporary cleanup failed: {exc}")

    return True


# ──────────────── DIRECT FILE DOWNLOAD (NON-HLS) ────────────────

def download_direct_file(
    url,
    output_path,
    request_headers=None,
    retries=3
):
    request_headers = request_headers or headers
    tmp_file = output_path + ".part"

    for attempt in range(1, retries + 1):
        if os.path.exists(tmp_file):
            try:
                os.remove(tmp_file)
            except OSError:
                pass

        try:
            with requests.get(
                url,
                headers=request_headers,
                timeout=60,
                stream=True
            ) as r:

                if r.status_code != 200:
                    if r.status_code in (403, 404, 410):
                        error(f"HTTP {r.status_code} saat download")
                        return False

                    warn(f"HTTP {r.status_code}, mencoba lagi...")
                    time.sleep(1)
                    continue

                total_size = int(
                    r.headers.get("Content-Length", 0)
                )

                progress = Progress(
                    SpinnerColumn(style=THEME_ACCENT),
                    TextColumn(
                        f"[bold {THEME_ACCENT}]{{task.description}}[/bold {THEME_ACCENT}]"
                    ),
                    BarColumn(
                        complete_style=THEME_ACCENT,
                        finished_style=THEME_GREEN,
                        pulse_style=THEME_WARN
                    ),
                    TextColumn(
                        "[bold white]{task.percentage:>6.2f}%[/bold white]"
                    ),
                    DownloadColumn(),
                    TransferSpeedColumn(),
                    TimeElapsedColumn(),
                    TimeRemainingColumn(),
                    console=console,
                    expand=True
                )

                with progress:
                    task_id = progress.add_task(
                        "Downloading MP4",
                        total=total_size or None
                    )

                    with open(tmp_file, "wb") as f:
                        for chunk in r.iter_content(
                            chunk_size=1024 * 256
                        ):
                            if chunk:
                                f.write(chunk)
                                progress.update(
                                    task_id,
                                    advance=len(chunk)
                                )

            if (
                os.path.exists(tmp_file)
                and os.path.getsize(tmp_file) > 0
            ):
                os.replace(tmp_file, output_path)
                return True

        except requests.RequestException as exc:
            warn(f"Download gagal (percobaan {attempt}): {exc}")
            time.sleep(1)

        except OSError as exc:
            warn(f"Error file (percobaan {attempt}): {exc}")
            time.sleep(1)

    return False
