
import os
import re
import sys
import html
import uuid
import time
import threading
import shutil
import requests
import subprocess
import signal
import contextlib
import json

try:
    import termios
    import tty
    import select
except ImportError:
    termios = None
    tty = None
    select = None

from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

# ──────────────── AUTO INSTALL RICH ────────────────
try:
    from rich.console import Console
    from rich.text import Text
    from rich.panel import Panel
    from rich.align import Align
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

DOWNLOAD_DIR = "/sdcard/Zxx"
TEMP_DIR = "/sdcard/Zxx/.temp"
HTML_DIR = os.path.join(DOWNLOAD_DIR, "Html")

# True = tampilan bersih (kotak di tengah, info teknis disembunyikan). False = tampilan lengkap.
CLEAN_UI = True
MAX_WORKERS = 16

# Session bersama untuk segment HLS (reuse TCP → lebih kencang di Termux)
_SEGMENT_SESSION = None
_SEGMENT_SESSION_LOCK = threading.Lock()


def get_segment_session():
    global _SEGMENT_SESSION
    with _SEGMENT_SESSION_LOCK:
        if _SEGMENT_SESSION is None:
            from requests.adapters import HTTPAdapter
            s = requests.Session()
            adapter = HTTPAdapter(
                pool_connections=32,
                pool_maxsize=32,
                max_retries=0,
            )
            s.mount("http://", adapter)
            s.mount("https://", adapter)
            _SEGMENT_SESSION = s
        return _SEGMENT_SESSION


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

# Proses anak (aria2c/ffmpeg) yang sedang berjalan, dimatikan saat Ctrl+C
ACTIVE_PROCESSES = []


# ──────────────── PAUSE / RESUME (Ctrl+P / Ctrl+R) ────────────────

PAUSE_EVENT = threading.Event()
CURRENT_SOURCE = {"url": ""}
TERMINAL_STATE = {"fd": None, "attrs": None}
TEMP_META_NAME = "meta.json"


def wait_if_paused():
    while PAUSE_EVENT.is_set():
        time.sleep(0.5)


def pause_downloads():
    PAUSE_EVENT.set()
    for proc in ACTIVE_PROCESSES:
        if proc.poll() is None:
            try:
                os.kill(proc.pid, signal.SIGSTOP)
            except OSError:
                pass
    console.print(f"[bold {THEME_WARN}]⏸ PAUSED  (Ctrl+R untuk lanjut)[/bold {THEME_WARN}]")


def resume_downloads():
    PAUSE_EVENT.clear()
    for proc in ACTIVE_PROCESSES:
        if proc.poll() is None:
            try:
                os.kill(proc.pid, signal.SIGCONT)
            except OSError:
                pass
    console.print(f"[bold {THEME_GREEN}]▶ RESUMED[/bold {THEME_GREEN}]")


def restore_terminal():
    """Kembalikan mode terminal (dipanggil juga saat Ctrl+C), supaya echo keyboard tidak mati."""
    fd = TERMINAL_STATE["fd"]
    attrs = TERMINAL_STATE["attrs"]
    if fd is not None and attrs is not None and termios is not None:
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, attrs)
        except OSError:
            pass
    TERMINAL_STATE["fd"] = None
    TERMINAL_STATE["attrs"] = None


@contextlib.contextmanager
def keyboard_control():
    """Dengar Ctrl+P dan Ctrl+R selama download. Hanya aktif kalau stdin adalah terminal."""
    if termios is None or not sys.stdin.isatty():
        yield
        return

    fd = sys.stdin.fileno()
    TERMINAL_STATE["fd"] = fd
    TERMINAL_STATE["attrs"] = termios.tcgetattr(fd)
    stop = threading.Event()

    def watch():
        while not stop.is_set():
            ready, _, _ = select.select([fd], [], [], 0.2)
            if not ready:
                continue
            ch = os.read(fd, 1)
            if ch == b"\x10":
                pause_downloads()
            elif ch == b"\x12":
                resume_downloads()

    tty.setcbreak(fd)
    watcher = threading.Thread(target=watch, daemon=True)
    watcher.start()
    try:
        yield
    finally:
        stop.set()
        watcher.join(timeout=1)
        restore_terminal()


# ──────────────── FOLDER .TEMP BERNAMA JUDUL + META (untuk resume) ────────────────

def stream_key(url):
    return url.split("?")[0]


def read_temp_meta(seg_dir):
    try:
        with open(os.path.join(seg_dir, TEMP_META_NAME), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_temp_meta(seg_dir, data):
    os.makedirs(seg_dir, exist_ok=True)
    with open(os.path.join(seg_dir, TEMP_META_NAME), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def pick_temp_folder(base_name, stream, total):
    """
    Nama folder = judul. Kalau judul sama tapi stream/jumlah segmen beda,
    pakai "<judul> (2)" dst., supaya segmen dari video lain tidak tercampur.
    """
    n = 1
    while True:
        name = base_name if n == 1 else f"{base_name} ({n})"
        seg_dir = os.path.join(TEMP_DIR, name)

        if not os.path.isdir(seg_dir) or not os.listdir(seg_dir):
            return seg_dir

        meta = read_temp_meta(seg_dir)
        if meta and meta.get("stream") == stream and meta.get("total") == total:
            return seg_dir

        n += 1


# Subfolder output per sumber/mode
SOURCE_FOLDERS = {
    "njav": "NJAV",
    "phub": "PHUB",
    "hamster": "XHAMSTER",
    "xvideos": "XVIDEOS",
    "eporner": "EPORNER",
    "hqporner": "HQPORNER",
    "vidara": "VIDARA",
    "avtube": "AVTUBE",
    "javstory": "JAVSTORY",
    "javsubindo": "JAVSUBINDO",
    "javbos": "JAVBOS",
    "rumahperjaka": "RUMAHPERJAKA",
    "kingbokep": "KINGBOKEP",
    "avpinay": "AVPINAY",
    "sextb": "SEXTB",
    "virtuavixen": "VIRTUAVIXEN",
    "manual": "MANUAL"
}


def get_output_dir(source_key):
    folder = SOURCE_FOLDERS.get(source_key, "MANUAL")
    path = os.path.join(DOWNLOAD_DIR, folder)
    os.makedirs(path, exist_ok=True)
    return path


# ──────────────── THEME ────────────────

THEME_BORDER = "aquamarine1"
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
    if not CLEAN_UI:
        return Panel(
            content,
            title=title,
            border_style=border_style,
            box=rich_box.SQUARE,
            width=full_width(),
            padding=(1, 2)
        )

    panel = Panel(
        Text.from_markup(content, justify="center"),
        title=title,
        border_style=border_style,
        box=rich_box.SQUARE,
        width=min(full_width(), 60),
        padding=(0, 2)
    )
    return Align.center(panel)


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


def folder_size_bytes(path):
    """Total ukuran semua file di dalam path (rekursif). Aman kalau folder belum ada."""
    if not os.path.isdir(path):
        return 0

    total = 0
    for dp, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(dp, name))
            except OSError:
                pass
    return total


def format_gb(size_bytes):
    return f"{size_bytes / (1024 ** 3):.2f} GB"


def banner():
    session = str(uuid.uuid4())[:8]
    total_zxx = format_gb(folder_size_bytes(DOWNLOAD_DIR))
    total_temp = format_gb(folder_size_bytes(TEMP_DIR))
    box_inner = max(20, min(full_width(), 60) - 6)
    rule = "─" * box_inner

    text = f"""
[bold italic white]ULTIMATE VIDEO DOWNLOADER[/bold italic white]

[bold {THEME_ACCENT}]NJAVTV • PHUB • HAMSTER • XVIDEOS[/bold {THEME_ACCENT}]
[bold {THEME_ACCENT}]EPORNER • HQPORNER • AVTUBE • JAVSTORY • JAVSUBINDO • JAVBOS • RUMAHPERJAKA[/bold {THEME_ACCENT}]
[bold {THEME_ACCENT}]HLS • MULTI THREAD[/bold {THEME_ACCENT}]

[{THEME_BORDER}]{rule}[/{THEME_BORDER}]

[bold white]Directory[/bold white] : [bold {THEME_GREEN}]{DOWNLOAD_DIR}[/bold {THEME_GREEN}]
[bold white]Total Zxx[/bold white] : [bold {THEME_GREEN}]{total_zxx}[/bold {THEME_GREEN}]  │  [bold white]Total .temp[/bold white] : [bold {THEME_WARN}]{total_temp}[/bold {THEME_WARN}]
[bold white]Workers[/bold white]   : [bold {THEME_GREEN}]{MAX_WORKERS}[/bold {THEME_GREEN}]
[bold white]Session[/bold white]   : [bold {THEME_DIM}]{session}[/bold {THEME_DIM}]
"""

    if CLEAN_UI:
        text = "\n".join(
            line for line in text.split("\n")
            if "Workers" not in line and "Session" not in line
        )

    console.print(
        make_panel(
            text.strip(),
            title="[bold italic white] PREMIUM CLI [/bold italic white]"
        )
    )

    cmd_text = (
        "[bold white]Ctrl+P[/bold white] pause │ [bold white]Ctrl+R[/bold white] resume\n\n"
        "[bold white]clear[/bold white] │ [bold white]speedtest[/bold white] │ [bold white]resume[/bold white]"
    )
    console.print(
        make_panel(
            cmd_text,
            title="[bold italic white] PERINTAH [/bold italic white]",
            border_style=THEME_BORDER
        )
    )


def section(title):
    if CLEAN_UI:
        return
    console.print()
    console.rule(
        f"[bold italic white]{title.upper()}[/bold italic white]",
        style=THEME_DIM
    )


def info(label, value):
    if CLEAN_UI:
        return
    console.print(
        f"[bold white]{label:<12}[/bold white] : "
        f"[bold {THEME_ACCENT}]{value}[/bold {THEME_ACCENT}]"
    )


CLEAN_OK_PREFIXES = ("Saved", "Download completed", "Subtitle")


def ok(text):
    if CLEAN_UI and not str(text).startswith(CLEAN_OK_PREFIXES):
        return
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
    # karakter bermasalah di filesystem / shell / ffmpeg
    name = re.sub(r'[\\/:*?"<>|&=;`$]', "_", name)
    name = re.sub(r"[^\w\s\-\.\'\(\)]+", "_", name, flags=re.UNICODE)
    name = re.sub(r"\s+", " ", name).strip(" ._")
    if len(name) > 80:
        name = name[:80].rstrip(" ._")
    return name if name else "video"


# ──────────────── COMMON / HTTP ────────────────

def save_html(url, filename, request_headers=None):
    r = requests.get(
        url,
        headers=request_headers or headers,
        timeout=30
    )
    r.raise_for_status()

    os.makedirs(HTML_DIR, exist_ok=True)
    path = os.path.join(HTML_DIR, os.path.basename(filename))

    with open(path, "w", encoding="utf-8") as f:
        f.write(r.text)

    return path


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


def parse_hls_key(m3u8_url, m3u8_text, request_headers=None):
    """
    Parse #EXT-X-KEY:METHOD=AES-128,URI="...",IV=0x...
    Return dict {method, key_bytes, iv_explicit} atau None.
    """
    method = None
    key_uri = None
    iv_explicit = None

    for line in m3u8_text.splitlines():
        line = line.strip()
        if not line.startswith("#EXT-X-KEY:"):
            continue
        meta = line.split(":", 1)[1]
        mm = re.search(r"METHOD=([^,\s]+)", meta, re.I)
        if mm:
            method = mm.group(1).strip().upper()
        um = re.search(r'URI="([^"]+)"', meta)
        if um:
            key_uri = urljoin(m3u8_url, um.group(1))
        im = re.search(r"IV=0x([0-9A-Fa-f]+)", meta)
        if im:
            iv_hex = im.group(1)
            if len(iv_hex) % 2:
                iv_hex = "0" + iv_hex
            iv_explicit = bytes.fromhex(iv_hex)

    if not method or method == "NONE":
        return None
    if method != "AES-128":
        warn(f"HLS key method tidak didukung: {method}")
        return None
    if not key_uri:
        return None

    try:
        r = requests.get(
            key_uri,
            headers=request_headers or headers,
            timeout=30,
        )
        body_preview = r.content[:40]
        if r.status_code != 200 or len(r.content) < 16:
            detail = body_preview.decode("utf-8", errors="ignore")
            error(
                f"Gagal unduh HLS key (HTTP {r.status_code}): {detail}"
            )
            return None
        key_bytes = r.content[:16]
        info("HLS", "AES-128 (segment akan didekripsi)")
        return {
            "method": method,
            "key": key_bytes,
            "iv_explicit": iv_explicit,
        }
    except requests.RequestException as exc:
        error(f"HLS key error: {exc}")
        return None


def aes128_decrypt_segment(data: bytes, key: bytes, iv: bytes) -> bytes:
    try:
        from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    except ImportError as exc:
        raise RuntimeError(
            "cryptography belum terpasang (pip install cryptography)"
        ) from exc

    if len(data) % 16 != 0:
        # pad truncation — tetap coba decrypt full blocks
        data = data[: len(data) - (len(data) % 16)]
    decryptor = Cipher(algorithms.AES(key), modes.CBC(iv)).decryptor()
    plain = decryptor.update(data) + decryptor.finalize()
    # PKCS7 unpad jika valid
    if plain:
        pad = plain[-1]
        if 1 <= pad <= 16 and plain.endswith(bytes([pad]) * pad):
            plain = plain[:-pad]
    return plain


def parse_segments(m3u8_url, m3u8_text):
    segments = []
    media_sequence = 0

    for line in m3u8_text.splitlines():
        line = line.strip()

        if not line:
            continue

        if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
            try:
                media_sequence = int(line.split(":", 1)[1].strip())
            except ValueError:
                pass
            continue

        # Dukungan initialization map pada HLS
        if line.startswith("#EXT-X-MAP"):
            match = re.search(r'URI="([^"]+)"', line)

            if match:
                segments.append(
                    {
                        "url": urljoin(m3u8_url, match.group(1)),
                        "seq": media_sequence,
                        "is_map": True,
                    }
                )

            continue

        if line.startswith("#"):
            continue

        segments.append(
            {
                "url": urljoin(m3u8_url, line),
                "seq": media_sequence,
                "is_map": False,
            }
        )
        media_sequence += 1

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

SEGMENT_STATS = {"bytes": 0}
SEGMENT_STATS_LOCK = threading.Lock()


def download_one_segment(
    idx,
    seg_url,
    seg_file,
    request_headers=None,
    retries=5,
    hls_key=None,
    seq=0,
):
    request_headers = request_headers or headers
    tmp_file = seg_file + ".part"

    for attempt in range(1, retries + 1):
        wait_if_paused()
        try:
            sess = get_segment_session()
            with sess.get(
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

                chunks = []
                total = 0
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        wait_if_paused()
                        chunks.append(chunk)
                        total += len(chunk)
                        with SEGMENT_STATS_LOCK:
                            SEGMENT_STATS["bytes"] += len(chunk)

            if total <= 0:
                continue

            data = b"".join(chunks)
            if hls_key and hls_key.get("key"):
                iv = hls_key.get("iv_explicit")
                if iv is None:
                    iv = int(seq).to_bytes(16, "big")
                try:
                    data = aes128_decrypt_segment(
                        data, hls_key["key"], iv
                    )
                except Exception:
                    time.sleep(1)
                    continue

            with open(tmp_file, "wb") as f:
                f.write(data)
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
    request_headers=None,
    workers=None,
):
    request_headers = request_headers or headers
    workers = workers or MAX_WORKERS

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

    # Kompatibilitas: dulu list URL string
    if segments and isinstance(segments[0], str):
        segments = [
            {"url": u, "seq": i, "is_map": False}
            for i, u in enumerate(segments)
        ]

    hls_key = parse_hls_key(real_m3u8, m3u8_text, request_headers)

    # Playlist bilang AES-128 tapi key gagal diunduh → jangan buang waktu unduh segmen
    if "#EXT-X-KEY" in m3u8_text and "METHOD=AES-128" in m3u8_text and not hls_key:
        error(
            "Stream terenkripsi AES-128 tapi kunci tidak bisa diunduh "
            "(sering: login/member required). "
            "Login di browser lalu export cookie, atau pilih source lain."
        )
        return False

    total = len(segments)

    info("Segments", total)
    info("Workers", workers)

    os.makedirs(TEMP_DIR, exist_ok=True)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    base_name = os.path.splitext(os.path.basename(output_path))[0]
    stream = stream_key(real_m3u8)
    seg_dir = pick_temp_folder(base_name, stream, total)
    os.makedirs(seg_dir, exist_ok=True)
    write_temp_meta(seg_dir, {
        "title": base_name,
        "source": CURRENT_SOURCE["url"],
        "output": output_path,
        "stream": stream,
        "total": total,
    })
    PAUSE_EVENT.clear()

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
        TextColumn(
            f"[bold {THEME_GREEN}]{{task.fields[speed_text]}}[/bold {THEME_GREEN}]"
        ),
        console=console,
        expand=True
    )

    failed = 0
    SEGMENT_STATS["bytes"] = 0
    started_at = time.time()

    with keyboard_control(), progress:
        task_id = progress.add_task(
            "Downloading",
            total=total,
            speed_text="0.00 MB/s"
        )

        with ThreadPoolExecutor(
            max_workers=workers
        ) as executor:

            futures = []
            already_done = 0

            for idx, seg in enumerate(
                segments,
                start=1
            ):
                seg_file = os.path.join(
                    seg_dir,
                    f"{idx:05d}.ts"
                )

                if os.path.exists(seg_file) and os.path.getsize(seg_file) > 0:
                    already_done += 1
                    continue

                seg_url = seg["url"] if isinstance(seg, dict) else seg
                seq = seg.get("seq", idx - 1) if isinstance(seg, dict) else idx - 1

                futures.append(
                    executor.submit(
                        download_one_segment,
                        idx,
                        seg_url,
                        seg_file,
                        request_headers,
                        5,
                        hls_key,
                        seq,
                    )
                )

            if already_done:
                progress.update(task_id, advance=already_done)

            for future in as_completed(futures):
                try:
                    if not future.result():
                        failed += 1
                except Exception:
                    failed += 1

                elapsed = max(time.time() - started_at, 0.001)
                mb_per_s = SEGMENT_STATS["bytes"] / elapsed / (1024 ** 2)
                progress.update(
                    task_id,
                    advance=1,
                    speed_text=f"{mb_per_s:.2f} MB/s"
                )

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

    # Validasi header TS (0x47). Kalau bukan → segmen masih terenkripsi / rusak
    try:
        with open(ts_path, "rb") as fh:
            magic = fh.read(1)
        if magic != b"\x47":
            error(
                "File TS tidak valid (bukan sync 0x47). "
                "Segmen kemungkinan masih terenkripsi AES / rusak."
            )
            return False
    except OSError:
        pass

    section("FFMPEG")

    def _run_ffmpeg(cmd):
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        ACTIVE_PROCESSES.append(process)
        last_output = []
        with Progress(
            SpinnerColumn(style=THEME_ACCENT),
            TextColumn(
                f"[bold {THEME_ACCENT}]{{task.description}}[/bold {THEME_ACCENT}]"
            ),
            TimeElapsedColumn(),
            console=console,
            expand=True,
        ) as progress:
            progress.add_task("Converting TS to MP4", total=None)
            for line in process.stdout:
                line = line.strip()
                if line:
                    last_output.append(line)
                    if len(last_output) > 20:
                        last_output.pop(0)
        process.wait()
        return process.returncode, last_output

    # Path pendek untuk output ffmpeg (hindari &, spasi panjang, dll)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    tmp_mp4 = os.path.join(
        TEMP_DIR, f"out_{uuid.uuid4().hex[:10]}.mp4"
    )

    commands = [
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-fflags", "+genpts",
            "-i", ts_path, "-c", "copy",
            "-bsf:a", "aac_adtstoasc", tmp_mp4,
        ],
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-fflags", "+genpts",
            "-i", ts_path, "-c", "copy", tmp_mp4,
        ],
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", ts_path, "-c:v", "copy", "-c:a", "aac",
            "-b:a", "128k", tmp_mp4,
        ],
    ]

    last_output = []
    ok_ff = False
    for command in commands:
        if os.path.exists(tmp_mp4):
            try:
                os.remove(tmp_mp4)
            except OSError:
                pass
        code, last_output = _run_ffmpeg(command)
        if (
            code == 0
            and os.path.exists(tmp_mp4)
            and os.path.getsize(tmp_mp4) > 1024
        ):
            ok_ff = True
            break

    if not ok_ff:
        error("FFmpeg failed")
        for line in last_output:
            console.print(f"[dim]{line}[/dim]")
        return False

    try:
        if os.path.exists(output_path):
            os.remove(output_path)
        shutil.move(tmp_mp4, output_path)
    except OSError as exc:
        error(f"Gagal memindahkan hasil: {exc}")
        return False

    size_mb = os.path.getsize(output_path) / 1024 / 1024

    result = make_table(
        title="[bold italic white]DOWNLOAD COMPLETED[/bold italic white]"
    )

    result.add_column("Item", ratio=2)
    result.add_column("Value", ratio=6)

    result.add_row("Saved", output_path)
    result.add_row("Size", f"{size_mb:.2f} MB")

    if not CLEAN_UI:

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

ARIA2_CONNECTIONS = 16
ARIA2_HEADER_KEYS = ("User-Agent", "Referer", "Origin", "Accept", "Accept-Language", "Cookie")


def download_with_aria2(url, output_path, request_headers=None):
    """
    Download file langsung lewat aria2c (lebih cepat dari downloader Python di Termux).
    Return True kalau berhasil, False kalau gagal.
    """
    request_headers = request_headers or headers

    cmd = [
        "aria2c",
        f"-x{ARIA2_CONNECTIONS}",
        f"-s{ARIA2_CONNECTIONS}",
        "-k1M",
        "--file-allocation=none",
        "--allow-overwrite=true",
        "--auto-file-renaming=false",
        "--console-log-level=warn",
        "-d", os.path.dirname(output_path),
        "-o", os.path.basename(output_path),
    ]

    for key in ARIA2_HEADER_KEYS:
        value = request_headers.get(key)
        if value:
            cmd.append(f"--header={key}: {value}")

    cmd.append(url)

    info("Downloader", f"aria2c (-x{ARIA2_CONNECTIONS} -s{ARIA2_CONNECTIONS})")

    try:
        proc = subprocess.Popen(cmd)
        ACTIVE_PROCESSES.append(proc)
        proc.wait()
    except OSError as exc:
        warn(f"aria2c tidak bisa dijalankan: {exc}")
        return False

    if (
        proc.returncode != 0
        or not os.path.exists(output_path)
        or os.path.getsize(output_path) < 102400
    ):
        for leftover in (output_path, output_path + ".aria2"):
            if os.path.exists(leftover):
                os.remove(leftover)
        return False

    return True


DIRECT_WORKERS = 10


def download_direct_parallel(url, output_path, request_headers=None, workers=None):
    """
    Download file langsung secara paralel memakai HTTP Range.
    Return True (sukses), False (gagal di tengah), None (tidak didukung / file kecil).
    """
    from concurrent.futures import ThreadPoolExecutor

    request_headers = request_headers or headers
    workers = workers or DIRECT_WORKERS

    try:
        probe_headers = {**request_headers, "Range": "bytes=0-0"}
        with requests.get(url, headers=probe_headers, timeout=30, stream=True) as probe:
            if probe.status_code != 206:
                return None
            match = re.search(r"/(\d+)$", probe.headers.get("Content-Range", ""))
            if not match:
                return None
            total = int(match.group(1))
    except requests.RequestException:
        return None

    if total < 2 * 1024 * 1024:
        return None

    chunk_size_bytes = -(-total // workers)
    ranges = [
        (i * chunk_size_bytes, min((i + 1) * chunk_size_bytes, total) - 1)
        for i in range(workers)
        if i * chunk_size_bytes < total
    ]

    tmp_file = output_path + ".part"

    with open(tmp_file, "wb") as f:
        f.truncate(total)

    progress = Progress(
        SpinnerColumn(style=THEME_ACCENT),
        TextColumn(f"[bold {THEME_ACCENT}]{{task.description}}[/bold {THEME_ACCENT}]"),
        BarColumn(complete_style=THEME_ACCENT, finished_style=THEME_GREEN, pulse_style=THEME_WARN),
        TextColumn("[bold white]{task.percentage:>6.2f}%[/bold white]"),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        expand=True
    )

    def fetch_range(start, end, task_id, prog):
        for _ in range(3):
            try:
                range_headers = {**request_headers, "Range": f"bytes={start}-{end}"}
                with requests.get(url, headers=range_headers, timeout=60, stream=True) as r:
                    if r.status_code != 206:
                        raise RuntimeError(f"HTTP {r.status_code}")
                    with open(tmp_file, "r+b") as fh:
                        fh.seek(start)
                        for data in r.iter_content(chunk_size=1024 * 256):
                            if data:
                                fh.write(data)
                                prog.update(task_id, advance=len(data))
                return True
            except (requests.RequestException, RuntimeError, OSError):
                time.sleep(1)
        return False

    with progress as prog:
        task_id = prog.add_task(f"Downloading MP4 ({len(ranges)} workers)", total=total)

        with ThreadPoolExecutor(max_workers=len(ranges)) as pool:
            futures = [pool.submit(fetch_range, s, e, task_id, prog) for s, e in ranges]
            results = [fut.result() for fut in futures]

    if not all(results):
        if os.path.exists(tmp_file):
            os.remove(tmp_file)
        return None

    os.replace(tmp_file, output_path)
    return True


def download_direct_file(
    url,
    output_path,
    request_headers=None,
    retries=3
):
    request_headers = request_headers or headers

    if shutil.which("aria2c"):
        if download_with_aria2(url, output_path, request_headers):
            return True
        warn("aria2 gagal, mencoba downloader Python")

    parallel_result = download_direct_parallel(url, output_path, request_headers)
    if parallel_result:
        return True

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
                if os.path.getsize(tmp_file) < 102400:
                    with open(tmp_file, "rb") as small_f:
                        preview = small_f.read(300)
                    os.remove(tmp_file)
                    error(
                        "File hasil download terlalu kecil (< 100 KB), "
                        "kemungkinan server mengembalikan halaman error, bukan video."
                    )
                    error(f"Isi respons: {preview!r}")
                    return False

                os.replace(tmp_file, output_path)
                return True

        except requests.RequestException as exc:
            warn(f"Download gagal (percobaan {attempt}): {exc}")
            time.sleep(1)

        except OSError as exc:
            warn(f"Error file (percobaan {attempt}): {exc}")
            time.sleep(1)

    return False


# ──────────────── MANUAL: DETEKSI TIPE LINK ────────────────

def detect_manual_link_type(url, request_headers=None):
    """
    Cek 16 byte pertama link.
    Return ("hls", None) kalau playlist m3u8, ("direct", content_type) kalau file biasa.
    Raise RuntimeError kalau server menolak (mis. 403).
    """
    request_headers = request_headers or headers

    r = requests.get(
        url,
        headers=request_headers,
        timeout=30,
        stream=True
    )

    try:
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} saat cek link")

        content_type = (r.headers.get("Content-Type") or "").lower()
        first_bytes = next(r.iter_content(chunk_size=120), b"")

    finally:
        r.close()

    if first_bytes.lstrip().startswith(b"#EXTM3U"):
        return "hls", None

    if url.split("?")[0].lower().endswith(".m3u8"):
        raise RuntimeError(
            "Link m3u8 tidak berisi playlist "
            f"(Content-Type: {content_type or '-'}, awal respons: {first_bytes[:120]!r})"
        )

    return "direct", content_type
