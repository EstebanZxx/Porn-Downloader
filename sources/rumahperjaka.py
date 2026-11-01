from core.common import *
from sources.vidara import fetch_vidara_stream, download_stream
from sources.javstory import fetch_streamtape_video
from urllib.parse import urlparse


# ──────────────── RUMAHPERJAKA EXTRACTOR ────────────────

def find_rumahperjaka_title(content):
    """
    <title>Jav Sub Indo &#8211; Di Tinggal Pas Lagi Sayang-Sayange &#8211; RumahPerjaka | Bokep ...</title>
      -> "Di Tinggal Pas Lagi Sayang-Sayange"
    """
    match = re.search(r"<title[^>]*>(.*?)</title>", content, re.DOTALL | re.IGNORECASE)
    title = html.unescape(match.group(1)).strip() if match else "rumahperjaka_video"
    title = title.split(" | ")[0]
    title = re.split(r"\s+[-–]\s+RumahPerjaka", title, flags=re.IGNORECASE)[0]
    title = re.sub(r"^\s*Jav\s+Sub\s+Indo\s*[-–]\s*", "", title, flags=re.IGNORECASE)
    return safe_filename(title.strip()) or "rumahperjaka_video"


def find_rumahperjaka_players(content, page_url):
    """
    Kumpulkan URL player dari halaman, urutan: Vidara dulu, lalu Streamtape.
    Mencakup iframe dan URL yang tertulis di script.
    """
    found = []
    for match in re.findall(r'https?://(?:vidara\.to|streamtape\.com|streamtape\.to)/e/[A-Za-z0-9_\-]+', content):
        if match not in found:
            found.append(match)

    found.sort(key=lambda u: 0 if "vidara" in urlparse(u).hostname else 1)
    return found


# ──────────────── PROCESS RUMAHPERJAKA ────────────────

def process_rumahperjaka(url):
    section("Fetching RumahPerjaka")

    try:
        page_headers = build_dynamic_headers(url)
        r = requests.get(url, headers=page_headers, timeout=30)

        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} dari halaman RumahPerjaka")

        content = r.text
        title = find_rumahperjaka_title(content)
        players = find_rumahperjaka_players(content, url)

        if not players:
            raise RuntimeError("Player tidak ditemukan di halaman. Pakai mode manual.")

        info("Title", title)
        info("Players", ", ".join(urlparse(p).hostname for p in players))

        for player in players:
            host = urlparse(player).hostname or ""
            scheme = urlparse(player).scheme

            try:
                if "vidara" in host:
                    info("Trying", player)
                    v_title, stream, origin = fetch_vidara_stream(player)
                    if download_stream(title, stream, origin, "rumahperjaka"):
                        return True

                elif "streamtape" in host:
                    info("Trying", player)
                    video = fetch_streamtape_video(player, url)
                    if download_stream(title, video, f"{scheme}://{host}", "rumahperjaka"):
                        return True

            except RuntimeError as exc:
                warn(f"{host} gagal: {exc}")

            except requests.RequestException as exc:
                warn(f"{host} request error: {exc}")

        error("Semua player otomatis gagal. Pakai mode manual dengan link m3u8 dari sniffer.")
        return False

    except RuntimeError as exc:
        error(str(exc))
        return False

    except requests.RequestException as exc:
        error(f"RumahPerjaka request error: {exc}")
        return False

    except KeyboardInterrupt:
        raise

    except Exception as exc:
        error(f"RumahPerjaka error: {exc}")
        return False
