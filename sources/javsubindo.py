from core.common import *
from sources.vidara import fetch_vidara_stream, download_stream
from sources.javstory import fetch_streamtape_video
from urllib.parse import urlparse, urljoin
from sources.avtube import unpack_packer


# ──────────────── NEKOVID ────────────────

def fetch_nekovid_stream(embed_url, page_url):
    """
    Halaman embed Nekovid memuat JS packer yang berisi var links={"hls4":"/stream/...master.m3u8"}.
    Path-nya relatif, jadi digabung dengan domain embed. Return URL m3u8.
    """
    embed_headers = {**build_dynamic_headers(embed_url), "Referer": page_url}

    r = requests.get(embed_url, headers=embed_headers, timeout=30)

    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} dari halaman embed Nekovid")

    search_text = (unpack_packer(r.text) + "\n" + r.text).replace("\\/", "/")

    match = re.search(r'"hls4"\s*:\s*"([^"]+)"', search_text)
    if match:
        return urljoin(embed_url, match.group(1))

    match = re.search(r'"hls2"\s*:\s*"([^"]+)"', search_text)
    if match:
        return urljoin(embed_url, match.group(1))

    raise RuntimeError("link m3u8 Nekovid tidak ditemukan di halaman embed")


# ──────────────── JAVSUBINDO EXTRACTOR ────────────────

def find_javsubindo_title(content):
    """
    Ambil judul bersih dari <title>:
    "Nonton & Download DASS-366 Tukang Urut ... Temukan JAV Subtitle ... di JAVSUBIN.COM"
      -> "DASS-366 Tukang Urut ..."
    "JUQ-050 Janda ... Kinoshita - JAVSubindo" -> "JUQ-050 Janda ... Kinoshita"
    """
    match = re.search(r"<title[^>]*>(.*?)</title>", content, re.DOTALL | re.IGNORECASE)
    title = html.unescape(match.group(1)).strip() if match else "javsubindo_video"

    title = re.sub(r"^\s*Nonton\s*&\s*Download\s+", "", title, flags=re.IGNORECASE)
    title = re.split(r"\s+Temukan\s+JAV\s+Subtitle", title, flags=re.IGNORECASE)[0]
    title = re.sub(r"\s*-\s*JAVSubindo\s*$", "", title, flags=re.IGNORECASE)

    return safe_filename(title.strip()) or "javsubindo_video"


def find_direct_iframes(content):
    """
    Halaman yang tidak punya WVMS_DATA: player langsung di iframe.
    Pakai data-litespeed-src kalau src-nya about:blank.
    """
    urls = []
    for tag in re.findall(r"<iframe[^>]*>", content, re.IGNORECASE):
        src = re.search(r'\bsrc="([^"]+)"', tag)
        lazy = re.search(r'data-litespeed-src="([^"]+)"', tag)
        candidate = None
        if lazy:
            candidate = lazy.group(1)
        elif src and src.group(1).startswith("http"):
            candidate = src.group(1)
        if candidate and candidate.startswith("http") and candidate not in urls:
            urls.append(candidate)
    return urls


def find_javsubindo_servers(content):
    """
    Ambil URL iframe semua server dari variabel WVMS_DATA, sesuai urutan di halaman.
    Isinya di-escape (\\" dan \\u003C), jadi cukup cari src="https://..." di dalam blok itu.
    """
    i = content.find("WVMS_DATA=")
    if i < 0:
        return find_direct_iframes(content)

    end = content.find("</script>", i)
    segment = content[i:end] if end > 0 else content[i:]

    urls = []
    for m in re.finditer(r'src=\\*"(https?://[^"\\\s]+)', segment):
        url = m.group(1)
        if url not in urls:
            urls.append(url)
    return urls


# ──────────────── PROCESS JAVSUBINDO ────────────────

def process_javsubindo(url):
    section("Fetching JAVSubindo")

    try:
        page_headers = build_dynamic_headers(url)

        r = requests.get(url, headers=page_headers, timeout=30)

        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} dari halaman JAVSubindo")

        content = r.text
        title = find_javsubindo_title(content)
        servers = find_javsubindo_servers(content)

        if not servers:
            raise RuntimeError("Daftar server tidak ditemukan di halaman. Pakai mode manual.")

        info("Title", title)
        info("Servers", ", ".join(urlparse(s).hostname or s for s in servers))

        # Vidara dicoba duluan (lebih stabil), sisanya ikut urutan halaman
        servers = sorted(servers, key=lambda u: 0 if "vidara" in (urlparse(u).hostname or "") else 1)

        for server in servers:
            host = urlparse(server).hostname or ""
            scheme = urlparse(server).scheme

            try:
                if "vidara" in host:
                    info("Trying", server)
                    _, stream, origin = fetch_vidara_stream(server)
                    if download_stream(title, stream, origin, "javsubindo"):
                        return True

                elif "streamtape" in host:
                    info("Trying", server)
                    video = fetch_streamtape_video(server, url)
                    if download_stream(title, video, f"{scheme}://{host}", "javsubindo"):
                        return True

                elif "nekovid" in host:
                    info("Trying", server)
                    stream = fetch_nekovid_stream(server, url)
                    if download_stream(title, stream, f"{scheme}://{host}", "javsubindo"):
                        return True

                else:
                    warn(f"Skip {host}: player ini belum didukung otomatis, pakai mode manual")

            except RuntimeError as exc:
                warn(f"{host} gagal: {exc}")

            except requests.RequestException as exc:
                warn(f"{host} request error: {exc}")

        error("Semua server otomatis gagal. Pakai mode manual dengan link m3u8 dari sniffer.")
        return False

    except RuntimeError as exc:
        error(str(exc))
        return False

    except requests.RequestException as exc:
        error(f"JAVSubindo request error: {exc}")
        return False

    except KeyboardInterrupt:
        error("Download dibatalkan")
        return False

    except Exception as exc:
        error(f"JAVSubindo error: {exc}")
        return False
