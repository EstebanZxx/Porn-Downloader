from core.common import *


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
        first_bytes = next(r.iter_content(chunk_size=16), b"")

    finally:
        r.close()

    if first_bytes.lstrip().startswith(b"#EXTM3U"):
        return "hls", None

    return "direct", content_type


# ──────────────── PROCESS MANUAL M3U8 ────────────────

def process_manual(url):
    section("Manual M3U8 Mode")

    try:
        info("URL", url)

        raw_title = Prompt.ask(
            "[bold white]Masukkan judul video[/bold white]"
        ).strip()

        title = safe_filename(raw_title) if raw_title else "video"

        output_path = os.path.join(
            get_output_dir("manual"),
            f"{title}.mp4"
        )

        console.print(
            make_panel(
                f"""
[bold white]Title[/bold white]   : [bold {THEME_ACCENT}]{title}[/bold {THEME_ACCENT}]
[bold white]Mode[/bold white]    : [bold {THEME_WARN}]Manual M3U8[/bold {THEME_WARN}]
[bold white]Output[/bold white]  : [bold {THEME_WARN}]{output_path}[/bold {THEME_WARN}]
""".strip(),
                title="[bold italic white] MANUAL READY [/bold italic white]",
                border_style=THEME_WARN
            )
        )

        link_type, content_type = detect_manual_link_type(url, headers)

        if link_type == "hls":
            info("Type", "HLS (m3u8)")
            return download_video(
                url,
                output_path,
                headers
            ) is True

        info("Type", f"Direct file ({content_type or 'unknown'})")

        success = download_direct_file(
            url,
            output_path,
            headers
        )

        if not success:
            error("Download gagal")
            return False

        size_mb = os.path.getsize(output_path) / 1024 / 1024
        ok(f"Saved {output_path} ({size_mb:.2f} MB)")
        return True

    except RuntimeError as exc:
        error(str(exc))
        return False

    except requests.RequestException as exc:
        error(f"Manual mode request error: {exc}")
        return False

    except KeyboardInterrupt:
        error("Download dibatalkan")
        return False

    except Exception as exc:
        error(f"Manual mode error: {exc}")
        return False
