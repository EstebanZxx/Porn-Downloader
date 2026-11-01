from core.common import *
from sources.vidara import download_stream
from urllib.parse import urlparse, urljoin, unquote
import json
import html as html_lib


def find_virtuavixen_title(content: str) -> str:
    # fv_title dari player sering lebih pendek & bersih
    for m in re.finditer(r'data-item=(["\'])(.*?)\1', content, re.DOTALL):
        raw = html_lib.unescape(m.group(2))
        try:
            data = json.loads(raw)
            for src in data.get("sources") or []:
                ft = (src.get("fv_title") or "").strip()
                if ft:
                    ft = ft.split("/")[0].strip()
                    if ft:
                        return safe_filename(ft) or "virtuavixen_video"
        except Exception:
            pass

    match = re.search(r"<title[^>]*>(.*?)</title>", content, re.DOTALL | re.IGNORECASE)
    title = html_lib.unescape(match.group(1)).strip() if match else "virtuavixen_video"
    title = re.split(r"\s*[–\-]\s*VirtuaVixen", title, flags=re.IGNORECASE)[0]
    title = re.split(r"\s*[–\-]\s*AI Porn", title, flags=re.IGNORECASE)[0]
    title = re.sub(r"\s+", " ", title).strip()
    if len(title) > 80:
        title = title[:80].rstrip()
    return safe_filename(title) or "virtuavixen_video"



def extract_stream_loader_master(content: str) -> str | None:
    """
    Ambil URL stream-loader master dari data-item JSON / HTML.
    Contoh:
    .../stream-loader.php?stream_loader=10829&expire=...&signature=...
    """
    # 1) data-item='...' atau data-item="..."
    for m in re.finditer(r'data-item=(["\'])(.*?)\1', content, re.DOTALL):
        raw = html_lib.unescape(m.group(2))
        try:
            data = json.loads(raw)
        except Exception:
            # kadang masih ada escape slash
            try:
                data = json.loads(raw.encode().decode('unicode_escape'))
            except Exception:
                continue
        sources = data.get("sources") or []
        for src in sources:
            u = (src.get("src") or "").strip()
            if "stream-loader.php" in u and ".vtt" not in u:
                return u.replace(r"\/", "/")

    # 2) regex fallback
    found = []
    for m in re.finditer(
        r'https?://[^"\'\\\s<>]*stream-loader\.php\?[^"\'\\\s<>]+',
        content,
        re.IGNORECASE,
    ):
        u = m.group(0)
        u = (
            u.replace("\u0026", "&")
            .replace("&amp;", "&")
            .replace(r"\/", "/")
        )
        if ".vtt" in u or "sprite" in u:
            continue
        found.append(u)

    if found:
        found.sort(key=lambda u: (0 if "pl=" not in u else 1, -len(u)))
        return found[0]

    m = re.search(r'"contentUrl"\s*:\s*"(https?://[^"]+\.m3u8)"', content)
    if m:
        return m.group(1)
    return None


def parse_master_variants(m3u8_text: str, base_url: str):
    """
    Parse #EXT-X-STREAM-INF → list {height, bandwidth, url}.
    """
    variants = []
    lines = m3u8_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXT-X-STREAM-INF:"):
            meta = line.split(":", 1)[1]
            height = 0
            bw = 0
            rm = re.search(r"RESOLUTION=\d+x(\d+)", meta, re.I)
            if rm:
                height = int(rm.group(1))
            bm = re.search(r"BANDWIDTH=(\d+)", meta, re.I)
            if bm:
                bw = int(bm.group(1))
            # next non-empty non-comment = url
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith("#")):
                j += 1
            if j < len(lines):
                u = lines[j].strip()
                if not u.startswith("http"):
                    u = urljoin(base_url, u)
                variants.append({"height": height, "bandwidth": bw, "url": u})
                i = j
        i += 1
    return variants


def fetch_best_stream(master_url: str, page_url: str):
    """
    Ambil master playlist tanpa cookie vv_geo=id (biar tidak dipaksa 240/480),
    pilih RESOLUTION tertinggi (pl=3 = 720p, dst).
    """
    session = requests.Session()
    # jangan bawa geo id
    session.cookies.set("vv_geo", "us", domain="virtuavixen.com")
    session.cookies.set("vv_geo_done", "1", domain="virtuavixen.com")

    hdrs = {
        **headers,
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": page_url,
        "Origin": "https://virtuavixen.com",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }

    r = session.get(master_url, headers=hdrs, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"stream-loader HTTP {r.status_code}")

    text = r.text
    if "#EXT" not in text:
        raise RuntimeError("stream-loader tidak mengembalikan m3u8 (mungkin paywall)")

    # media playlist langsung?
    if "#EXT-X-STREAM-INF" not in text and "#EXTINF" in text:
        return master_url, "media"

    variants = parse_master_variants(text, master_url)
    if not variants:
        # coba paksa pl=3..1 dengan signature dari URL master (kadang tidak jalan)
        raise RuntimeError("tidak ada variant di master playlist")

    variants.sort(key=lambda v: (v["height"], v["bandwidth"]), reverse=True)
    best = variants[0]
    info(
        "Qualities",
        ", ".join(f"{v['height']}p" for v in variants),
    )
    info("Selected", f"{best['height']}p")
    return best["url"], f"{best['height']}p"


def process_virtuavixen(url: str):
    section("Fetching VirtuaVixen")

    try:
        # stream-loader / m3u8 langsung
        host = (urlparse(url).hostname or "").lower()
        if "stream-loader.php" in url or url.endswith(".m3u8"):
            info("Mode", "stream langsung")
            stream, label = fetch_best_stream(url, "https://virtuavixen.com/")
            title = safe_filename(f"virtuavixen_{label}") or "virtuavixen_video"
            return download_stream(title, stream, "https://virtuavixen.com", "virtuavixen")

        page_headers = {
            **build_dynamic_headers(url),
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }
        session = requests.Session()
        session.cookies.set("vv_geo", "us", domain="virtuavixen.com")
        session.cookies.set("vv_geo_done", "1", domain="virtuavixen.com")

        r = session.get(url, headers=page_headers, timeout=40)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} dari VirtuaVixen")

        content = r.text
        title = find_virtuavixen_title(content)
        master = extract_stream_loader_master(content)

        info("Title", title)

        if not master:
            raise RuntimeError(
                "stream-loader tidak ditemukan di halaman. "
                "Paste URL stream-loader / m3u8 manual."
            )

        info("Master", master[:90] + ("..." if len(master) > 90 else ""))
        stream, label = fetch_best_stream(master, url)
        return download_stream(title, stream, "https://virtuavixen.com", "virtuavixen")

    except RuntimeError as exc:
        error(str(exc))
        return False

    except requests.RequestException as exc:
        error(f"VirtuaVixen request error: {exc}")
        return False

    except KeyboardInterrupt:
        error("Download dibatalkan")
        return False

    except Exception as exc:
        error(f"VirtuaVixen error: {exc}")
        return False
