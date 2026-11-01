from core.common import *
from sources.vidara import fetch_vidara_stream, download_stream
from urllib.parse import urlparse, urljoin


# ──────────────── AVTUBE EXTRACTOR ────────────────

def find_avtube_title(content):
    """Ambil judul dari og:title, lalu <title>. Buang suffix nama situs (" - KingBokep")."""
    match = re.search(
        r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
        content, re.IGNORECASE
    )
    if match:
        title = match.group(1)
    else:
        match = re.search(r"<title[^>]*>(.*?)</title>", content, re.DOTALL | re.IGNORECASE)
        title = match.group(1) if match else "avtube_video"

    title = html.unescape(title).strip()
    title = re.sub(r"\s+[-|]\s+[^-|]+$", "", title)
    return safe_filename(title) or "avtube_video"


def find_vidara_iframe(content, base_url):
    """Cari iframe yang mengarah ke vidara, return URL absolut atau None."""
    for src in re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', content, re.IGNORECASE):
        full = urljoin(base_url, src)
        if "vidara" in (urlparse(full).hostname or ""):
            return full
    return None


def find_direct_stream(content):
    """Fallback: link m3u8 atau mp4 yang ada langsung di HTML halaman."""
    text = html.unescape(content.replace("\\/", "/"))
    match = re.search(r'https?://[^\s"\'<>\\]+?\.(?:m3u8|mp4)[^\s"\'<>\\]*', text, re.IGNORECASE)
    return match.group(0) if match else None


# ──────────────── VSTREAM ────────────────

VSTREAM_FAMILY = ("vstream", "ystream")


def find_vstream_iframe(content, base_url):
    """Cari iframe player vstream/ystream (keluarga player yang sama), return URL absolut atau None."""
    for src in re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', content, re.IGNORECASE):
        full = urljoin(base_url, src)
        host = urlparse(full).hostname or ""
        if any(key in host for key in VSTREAM_FAMILY):
            return full
    return None


def _packer_enc(c, base):
    pre = "" if c < base else _packer_enc(c // base, base)
    rem = c % base
    ch = chr(rem + 29) if rem > 35 else "0123456789abcdefghijklmnopqrstuvwxyz"[rem]
    return pre + ch


def unpack_packer(text):
    """
    Buka semua blok JS packer: eval(function(p,a,c,k,e,d){...}('payload',base,count,'kata|...'.split('|'),0,{}))
    Return gabungan hasil bukaannya sebagai satu string.
    """
    results = []
    pos = 0

    while True:
        i = text.find("eval(function(p,a,c,k,e,d)", pos)
        if i < 0:
            break

        k = text.find("}('", i)
        if k < 0:
            break
        k += 3

        m = re.search(r"',(\d+),(\d+),'", text[k:])
        if not m:
            break

        payload = text[k:k + m.start()]
        base, count = int(m.group(1)), int(m.group(2))

        dict_start = k + m.end()
        dict_end = text.find("'.split('|')", dict_start)
        if dict_end < 0:
            break

        words = text[dict_start:dict_end].split("|")

        payload = payload.replace("\\\\", "\\").replace("\\'", "'").replace('\\"', '"')

        lookup = {}
        for c in range(count - 1, -1, -1):
            word = words[c] if c < len(words) else ""
            lookup[_packer_enc(c, base)] = word or _packer_enc(c, base)

        results.append(re.sub(r"\b\w+\b", lambda mm: lookup.get(mm.group(0), mm.group(0)), payload))
        pos = dict_end

    return "\n".join(results)


def find_hls_in_text(raw):
    """Cari link HLS di teks HTML/JS: kunci "hls2" lebih dulu, lalu URL .m3u8 apa pun."""
    unpacked = unpack_packer(raw)
    search_text = (unpacked + "\n" + raw).replace("\\/", "/")

    match = re.search(r'"hls2"\s*:\s*"([^"]+)"', search_text)
    if match:
        return match.group(1)

    match = re.search(r'https?://[^\s"\'<>\\]+?\.m3u8[^\s"\'<>\\]*', search_text)
    if match:
        return match.group(0)

    return None


def fetch_vstream_stream(embed_url, page_url):
    """
    Ambil halaman embed vstream, buka JS packer-nya, lalu ambil link HLS (kunci "hls2").
    Return URL m3u8.
    """
    embed_headers = {**build_dynamic_headers(embed_url), "Referer": page_url}

    r = requests.get(embed_url, headers=embed_headers, timeout=30)

    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code} dari halaman embed vstream")

    raw = r.text

    found = find_hls_in_text(raw)
    if found:
        return found

    # Player Byse membungkus player sebenarnya di iframe lagi: ikuti satu tingkat
    nested = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', raw, re.IGNORECASE)
    if nested:
        nested_url = urljoin(embed_url, nested.group(1))
        nested_headers = {**build_dynamic_headers(nested_url), "Referer": embed_url}
        r2 = requests.get(nested_url, headers=nested_headers, timeout=30)
        if r2.status_code == 200:
            found = find_hls_in_text(r2.text)
            if found:
                return found
        diag = f"iframe {nested_url} (HTTP {r2.status_code})"
    else:
        diag = f"tanpa iframe (HTML {len(raw)} karakter, awal: {raw[:80]!r})"

    raise RuntimeError(f"link m3u8 tidak ditemukan di halaman embed; {diag}")


# ──────────────── PROCESS AVTUBE ────────────────

def process_avtube(url):
    section("Fetching AvTube")

    try:
        page_headers = build_dynamic_headers(url)

        html_file = save_html(url, "avtube.html", page_headers)

        with open(html_file, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        title = find_avtube_title(content)

        vidara_url = find_vidara_iframe(content, url)

        if vidara_url:
            info("Player", vidara_url)
            vidara_title, stream, origin = fetch_vidara_stream(vidara_url)
            # Judul dari halaman lebih rapi (tanpa nama situs), jadi itu yang dipakai
            return download_stream(title or vidara_title, stream, origin, "avtube")

        vstream_url = find_vstream_iframe(content, url)

        if vstream_url:
            info("Player", vstream_url)
            stream = fetch_vstream_stream(vstream_url, url)
            vs = urlparse(vstream_url)
            return download_stream(title, stream, f"{vs.scheme}://{vs.hostname}", "avtube")

        stream = find_direct_stream(content)

        if stream:
            origin = f"{urlparse(url).scheme}://{urlparse(url).hostname}"
            return download_stream(title, stream, origin, "avtube")

        error("Player vidara atau link video tidak ditemukan di halaman. Pakai mode manual.")
        return False

    except RuntimeError as exc:
        error(str(exc))
        return False

    except requests.RequestException as exc:
        error(f"AvTube request error: {exc}")
        return False

    except KeyboardInterrupt:
        error("Download dibatalkan")
        return False

    except Exception as exc:
        error(f"AvTube error: {exc}")
        return False
