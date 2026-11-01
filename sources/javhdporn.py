from core.common import *
from sources.vidara import download_stream
from urllib.parse import urlparse
import html as html_lib


def find_javhdporn_title(content: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", content, re.DOTALL | re.IGNORECASE)
    title = html_lib.unescape(match.group(1)).strip() if match else "javhdporn_video"
    title = re.split(r"\s*[-–]\s*JAV HD Porn", title, flags=re.IGNORECASE)[0]
    title = re.sub(r"\s+", " ", title).strip()

    # prioritaskan kode JAV di depan (SPRD-1327 ...)
    m = re.match(r"^([A-Z]{2,10}-\d+)\b", title)
    if m and len(title) > 60:
        title = m.group(1)

    if len(title) > 80:
        title = title[:80].rstrip()
    return safe_filename(title) or "javhdporn_video"


def extract_stream_urls(content: str):
    """
    Kumpulkan kandidat stream dari HTML:
    - streamhls.click / m3u8
    - mp4 langsung (1024cdn, dll)
    """
    found = []
    patterns = [
        r'https?://streamhls\.click/[^\s"\'<>]+',
        r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*',
        r'https?://[^\s"\'<>]+\.mp4[^\s"\'<>]*',
        r'https?://[^"\'\s<>]*1024cdn[^"\'\s<>]+\.mp4',
        r'https?://video\.javhdporn\.net/[^"\'\s<>]+',
    ]
    for pat in patterns:
        for m in re.finditer(pat, content, re.IGNORECASE):
            u = m.group(0).rstrip("\\").replace("&amp;", "&")
            # skip ads / banner
            if any(x in u.lower() for x in ("banner", "ads", "tracking", "favicon")):
                continue
            if u not in found:
                found.append(u)

    # prioritaskan m3u8 / streamhls
    def score(u: str) -> int:
        ul = u.lower()
        if "streamhls" in ul and "m3u8" in ul:
            return 0
        if "m3u8" in ul:
            return 1
        if ul.endswith(".mp4"):
            return 2
        return 3

    found.sort(key=score)
    return found


def process_javhdporn(url: str):
    section("Fetching JAVHDPorn")

    try:
        host = (urlparse(url).hostname or "").lower()

        # URL stream langsung
        if (
            "streamhls.click" in host
            or url.rstrip("/").endswith(".m3u8")
            or ".m3u8?" in url
            or url.rstrip("/").endswith(".mp4")
        ):
            info("Mode", "stream langsung")
            origin = f"{urlparse(url).scheme}://{urlparse(url).hostname}"
            title = safe_filename(urlparse(url).path.strip("/").replace("/", "_")[-40:]) or "javhdporn"
            return download_stream(title, url, origin, "javhdporn")

        page_headers = {
            **build_dynamic_headers(url),
            "User-Agent": (
                "Mozilla/5.0 (Linux; Android 13; Pixel 7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Mobile Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        }

        # cloudscraper / curl_cffi jika ada
        session = None
        try:
            from curl_cffi import requests as cfi
            session = cfi.Session(impersonate="chrome131")
        except Exception:
            try:
                import cloudscraper
                session = cloudscraper.create_scraper(
                    browser={"browser": "chrome", "platform": "android", "mobile": True}
                )
            except Exception:
                session = requests.Session()

        r = session.get(url, headers=page_headers, timeout=40)
        if r.status_code != 200:
            raise RuntimeError(
                f"HTTP {r.status_code} dari JAVHDPorn (Cloudflare?). "
                "Paste link m3u8 streamhls.click langsung ke Lapendoz."
            )

        content = r.text
        if "Just a moment" in content or "cf-browser-verification" in content:
            raise RuntimeError(
                "Cloudflare challenge aktif. "
                "Buka di browser → Network → copy URL *.m3u8 / streamhls.click, "
                "lalu paste ke Lapendoz."
            )

        title = find_javhdporn_title(content)
        streams = extract_stream_urls(content)
        info("Title", title)

        if not streams:
            # data-mpu ada tapi terenkripsi di cast.js — tidak diekstrak di sini
            if 'data-mpu="' in content:
                raise RuntimeError(
                    "Player terenkripsi (data-mpu). "
                    "Buka video di browser → tab Network → filter m3u8 → "
                    "copy URL streamhls.click lalu paste ke Lapendoz."
                )
            raise RuntimeError("Tidak ada URL stream di halaman")

        last_err = None
        for stream in streams:
            try:
                info("Stream", stream[:90] + ("..." if len(stream) > 90 else ""))
                origin = f"{urlparse(stream).scheme}://{urlparse(stream).hostname}"
                # streamhls sering butuh Referer situs
                if "streamhls" in origin:
                    # download_stream set Origin dari origin arg
                    origin = "https://www.javhdporn.net"
                if download_stream(title, stream, origin, "javhdporn"):
                    return True
            except Exception as exc:
                last_err = exc
                warn(f"Stream gagal: {exc}")
                continue

        raise RuntimeError(f"Semua stream gagal. Terakhir: {last_err}")

    except RuntimeError as exc:
        error(str(exc))
        return False

    except requests.RequestException as exc:
        error(f"JAVHDPorn request error: {exc}")
        return False

    except KeyboardInterrupt:
        error("Download dibatalkan")
        return False

    except Exception as exc:
        error(f"JAVHDPorn error: {exc}")
        return False
