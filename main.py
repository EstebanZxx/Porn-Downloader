"""Entry point: python main.py"""

from core.common import *
from core.detect import detect_source

from sources.njav import process_njav
from sources.phub import process_phub
from sources.hamster import process_hamster
from sources.xvideos import process_xvideos
from sources.eporner import process_eporner
from sources.hqporner import process_hqporner
from sources.manual import process_manual


# ──────────────── MAIN ────────────────

def run_speedtest_mode():
    run_speedtest()
    input("\nTekan ENTER untuk kembali...")

def main():
    clear()

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)

    banner()

    console.print(
        f"[bold {THEME_ACCENT}]AUTO DETECT LINK MODE[/bold {THEME_ACCENT}]"
    )
    console.print(
        "[bold white]Paste link PHUB atau NJAVTV[/bold white]"
    )
    console.print(
        f"[bold {THEME_WARN}]Bisa satu link atau banyak link, pisahkan dengan spasi/newline[/bold {THEME_WARN}]"
    )
    console.print()


    while True:
        raw = Prompt.ask(
            "[bold white]URL[/bold white]"
        ).strip()

        if raw.lower() == "speedtest":
            run_speedtest_mode()
            clear()
            banner()
            continue

        if raw.lower() in ("exit", "quit"):
            info("Keluar dari downloader")
            return

        if raw:
            break

    links = raw.split()


    if not links:
        error("No URL provided")
        return

    success = 0
    failed = 0

    for idx, url in enumerate(links, start=1):
        clear()
        banner()

        section(f"Processing {idx}/{len(links)}")
        info("URL", url)

        source = detect_source(url)

        if source == "phub":
            ok("Detected source: PHUB")
            result = process_phub(url)

        elif source == "njav":
            ok("Detected source: NJAVTV")
            result = process_njav(url)

        elif source == "hamster":
            ok("Detected source: Hamster")
            result = process_hamster(url)

        elif source == "xvideos":
            ok("Detected source: Xvideos")
            result = process_xvideos(url)

        elif source == "eporner":
            ok("Detected source: Eporner")
            result = process_eporner(url)

        elif source == "hqporner":
            ok("Detected source: HQporner")
            result = process_hqporner(url)

        else:
            warn("Source tidak terdeteksi, menggunakan mode manual M3U8")
            result = process_manual(url)

        if result is True:
            success += 1
            ok("Download completed")
        else:
            failed += 1
            error("Download failed")

        if idx < len(links):
            try:
                input("\nENTER untuk lanjut...")
            except KeyboardInterrupt:
                error("Dibatalkan user")
                break

    section("Finished")

    summary = make_table(
        title="[bold italic white]DOWNLOAD SUMMARY[/bold italic white]",
        border_style=THEME_BORDER
    )

    summary.add_column("Status", ratio=2)
    summary.add_column("Total", ratio=2)

    summary.add_row(
        f"[bold {THEME_GREEN}]Success[/bold {THEME_GREEN}]",
        str(success)
    )
    summary.add_row(
        f"[bold {THEME_RED}]Failed[/bold {THEME_RED}]",
        str(failed)
    )

    console.print(summary)


if __name__ == "__main__":
    main()
