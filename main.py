"""Entry point: python main.py"""

import signal

from core.common import *
from core.detect import detect_source

from sources.njav import process_njav
from sources.phub import process_phub
from sources.hamster import process_hamster
from sources.xvideos import process_xvideos
from sources.eporner import process_eporner
from sources.hqporner import process_hqporner
from sources.vidara import process_vidara
from sources.avtube import process_avtube
from sources.javstory import process_javstory
from sources.javsubindo import process_javsubindo
from sources.javbos import process_javbos
from sources.rumahperjaka import process_rumahperjaka
from sources.kingbokep import process_kingbokep
from sources.avpinay import process_avpinay
from sources.sextb import process_sextb
from sources.virtuavixen import process_virtuavixen
from sources.manual import process_manual


# ──────────────── MAIN ────────────────

def run_speedtest_mode():
    run_speedtest()
    input("\nTekan ENTER untuk kembali...")

def force_remove(path):
    """
    Hapus file/folder sampai benar-benar hilang.
    Storage Android kadang menolak shutil, jadi fallback ke `rm -rf` di Termux.
    """
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        else:
            os.remove(path)
    except OSError:
        pass

    if os.path.lexists(path):
        subprocess.run(["rm", "-rf", path], check=False)

    if os.path.lexists(path):
        raise OSError(f"masih ada setelah dicoba dihapus: {path}")


def purge_temp_dir():
    """Hapus semua isi TEMP_DIR (file & folder). Folder .temp sendiri tetap ada."""
    if not os.path.isdir(TEMP_DIR):
        info("Temp", f"{TEMP_DIR} belum ada, tidak ada yang dihapus")
        return 0

    removed = 0
    failed = []

    for name in os.listdir(TEMP_DIR):
        path = os.path.join(TEMP_DIR, name)
        try:
            force_remove(path)
            removed += 1
        except OSError as exc:
            failed.append(name)
            warn(f"Gagal hapus {name}: {exc}")

    if failed:
        warn(f"{len(failed)} item tidak bisa dihapus. Pastikan tidak ada download yang sedang berjalan.")
    ok(f"Temp dibersihkan: {removed} item dihapus dari {TEMP_DIR}")
    return removed


def force_exit_handler(signum, frame):
    """Ctrl+C: matikan semua proses anak (aria2c/ffmpeg) lalu keluar langsung."""
    console.print("\n[bold red]✗ Dibatalkan (Ctrl+C), menghentikan download...[/bold red]")

    for proc in ACTIVE_PROCESSES:
        try:
            proc.kill()
        except Exception:
            pass

    console.print(
        "[bold white]File yang belum selesai mungkin masih ada di folder output "
        "(berakhiran .part atau .aria2).[/bold white]"
    )
    restore_terminal()
    os._exit(130)


def process_link(url):
    CURRENT_SOURCE["url"] = url

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

    elif source == "vidara":
        ok("Detected source: Vidara")
        result = process_vidara(url)

    elif source == "avtube":
        ok("Detected source: AvTube")
        result = process_avtube(url)

    elif source == "javstory":
        ok("Detected source: JAVStory1")
        result = process_javstory(url)

    elif source == "javsubindo":
        ok("Detected source: JAVSubindo")
        result = process_javsubindo(url)

    elif source == "javbos":
        ok("Detected source: JAVBOS")
        result = process_javbos(url)

    elif source == "rumahperjaka":
        ok("Detected source: RumahPerjaka")
        result = process_rumahperjaka(url)

    elif source == "kingbokep":
        ok("Detected source: KingBokep")
        result = process_kingbokep(url)

    elif source == "avpinay":
        ok("Detected source: AVPinay")
        result = process_avpinay(url)

    elif source == "sextb":
        ok("Detected source: SEXTB")
        result = process_sextb(url)

    elif source == "virtuavixen":
        ok("Detected source: VirtuaVixen")
        result = process_virtuavixen(url)

    else:
        warn("Source tidak terdeteksi, menggunakan mode manual M3U8")
        result = process_manual(url)

    return result


def list_resumable():
    items = []
    if not os.path.isdir(TEMP_DIR):
        return items

    for name in sorted(os.listdir(TEMP_DIR)):
        seg_dir = os.path.join(TEMP_DIR, name)
        meta = read_temp_meta(seg_dir) if os.path.isdir(seg_dir) else None
        if not meta:
            continue

        done = sum(
            1 for f in os.listdir(seg_dir)
            if f.endswith(".ts") and os.path.getsize(os.path.join(seg_dir, f)) > 0
        )
        items.append((name, meta, done))
    return items


def resume_menu():
    items = list_resumable()

    if not items:
        warn("Tidak ada download yang bisa dilanjutkan.")
        return

    console.print(f"[bold {THEME_ACCENT}]Pilih download yang mau dilanjutkan:[/bold {THEME_ACCENT}]")
    for i, (name, meta, done) in enumerate(items, start=1):
        size = format_gb(folder_size_bytes(os.path.join(TEMP_DIR, name)))
        total = meta.get("total", "?")
        console.print(
            f"[bold white]{i}.[/bold white] {name}  "
            f"[bold {THEME_WARN}]{done}/{total}[/bold {THEME_WARN}]  {size}"
        )

    choice = Prompt.ask("[bold white]Nomor[/bold white]", default="").strip()

    if not choice.isdigit() or not (1 <= int(choice) <= len(items)):
        warn("Dibatalkan.")
        return

    name, meta, done = items[int(choice) - 1]
    source = meta.get("source", "")

    if not source:
        error("Link sumber tidak tersimpan untuk download ini. Tempel link yang sama lagi.")
        return

    result = process_link(source)

    if result is True:
        ok("Download completed")
    else:
        error("Download failed")


def main():
    signal.signal(signal.SIGINT, force_exit_handler)

    clear()

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)

    banner()

    console.print(
        f"[bold {THEME_ACCENT}]AUTO DETECT LINK MODE[/bold {THEME_ACCENT}]"
    )
    console.print(
        "[bold white]Paste Link Web Yang Tertera / Link M3U8[/bold white]"
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

        if raw.lower() == "clear":
            purge_temp_dir()
            clear()
            banner()
            continue

        if raw.lower() == "resume":
            resume_menu()
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

        result = process_link(url)

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

    if CLEAN_UI:
        console.print(
            f"Selesai: {success} berhasil, {failed} gagal",
            justify="center"
        )
    else:
        console.print(summary)


if __name__ == "__main__":
    main()
