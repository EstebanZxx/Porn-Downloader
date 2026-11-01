from core.common import *
from sources.vidara import download_stream
from urllib.parse import urlparse, urljoin
import base64
import json


def make_session():
    """
    Session terbaik yang tersedia:
    1) curl_cffi (impersonate Chrome) — paling sering lolos CF
    2) cloudscraper
    3) requests biasa
    """
    try:
        from curl_cffi import requests as cfi
        s = cfi.Session(impersonate="chrome131")
        s._lapendoz_kind = "curl_cffi"
        return s
    except Exception:
        pass
    try:
        import cloudscraper
        s = cloudscraper.create_scraper(
            browser={"browser": "chrome", "platform": "android", "mobile": True}
        )
        s._lapendoz_kind = "cloudscraper"
        return s
    except Exception:
        pass
    s = requests.Session()
    s._lapendoz_kind = "requests"
    return s


SEXTB_UA = (
    "Mozilla/5.0 (Linux; Android 13; SM-S918B) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Mobile Safari/537.36"
)


def xor_decrypt(encoded: str, key: str) -> str:
    if not encoded or not key:
        return ""
    raw = base64.b64decode(encoded)
    out = bytearray()
    for i, b in enumerate(raw):
        out.append(b ^ ord(key[i % len(key)]))
    return out.decode("utf-8", errors="ignore")


def find_sextb_title(content: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", content, re.DOTALL | re.IGNORECASE)
    title = html.unescape(match.group(1)).strip() if match else "sextb_video"
    title = re.split(r"\s*[-–|]\s*SEXTB", title, flags=re.IGNORECASE)[0]
    # potong judul ekstrem panjang
    if len(title) > 120:
        # prefer kode JAV di depan (VENX-385 ...)
        m = re.match(r"^([A-Z]{2,6}-\d+)\b", title)
        if m:
            title = m.group(1)
        else:
            title = title[:100]
    return safe_filename(title.strip()) or "sextb_video"


def extract_tokens(content: str):
    pt = re.search(r'window\.__pt\s*=\s*"([^"]+)"', content)
    pk = re.search(r'window\.__pk\s*=\s*"([^"]+)"', content)
    return (
        pt.group(1) if pt else "",
        pk.group(1) if pk else "",
    )


def extract_episodes(content: str):
    """
    Tombol server: data-source=filmId, data-id=episodeId
    Urutan: F4, SW, DD, FL, US (skip VIP).
    """
    eps = []
    seen = set()
    for m in re.finditer(
        r'class="[^"]*btn-player[^"]*episode[^"]*"[^>]*data-source="(\d+)"[^>]*data-id="(-?\d+)"'
        r'|data-source="(\d+)"[^>]*data-id="(-?\d+)"[^>]*class="[^"]*btn-player[^"]*episode',
        content,
        re.IGNORECASE,
    ):
        film = m.group(1) or m.group(3)
        ep = m.group(2) or m.group(4)
        if not film or not ep:
            continue
        ep_i = int(ep)
        if ep_i < 0:
            continue
        key = (film, ep)
        if key in seen:
            continue
        seen.add(key)
        eps.append({"filmId": int(film), "episode": ep_i})
    return eps


def extract_f4_embed(player_html: str) -> str | None:
    """Cari iframe/src f4scdn|f4stream|f2stb|f4s.top di HTML player."""
    patterns = [
        r'src=["\'](https?://(?:[\w.-]+\.)?(?:f4scdn\.com|f4stream\.com|f2stb\.com|f4s\.top)/e/[^"\']+)["\']',
        r'(https?://(?:[\w.-]+\.)?(?:f4scdn\.com|f4stream\.com|f2stb\.com|f4s\.top)/e/[A-Za-z0-9_\-]+)',
    ]
    for pat in patterns:
        m = re.search(pat, player_html, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def fetch_f4_stream(embed_url: str):
    """
    Buka embed F4 → data-api UUID → GET /api/play/{uuid}?ab=0 → src HLS.
    """
    page_headers = {
        **headers,
        "Referer": "https://sextb.net/",
        "Accept": "text/html,application/xhtml+xml",
    }
    r = requests.get(embed_url, headers=page_headers, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"F4 embed HTTP {r.status_code}")

    content = r.text
    m = re.search(r'data-api=["\']([^"\']+)["\']', content)
    if not m:
        m = re.search(r'data-video-id=["\']([0-9a-fA-F\-]{20,})["\']', content)
        if not m:
            raise RuntimeError("data-api / video-id tidak ditemukan di embed F4")
        api_path = f"/api/play/{m.group(1)}"
    else:
        api_path = m.group(1)

    parsed = urlparse(embed_url)
    origin = f"{parsed.scheme}://{parsed.hostname}"
    api_url = urljoin(origin + "/", api_path.lstrip("/"))
    if "?" in api_url:
        api_url = api_url + "&ab=0"
    else:
        api_url = api_url + "?ab=0"

    api_headers = {
        **headers,
        "Referer": embed_url,
        "Origin": origin,
        "Accept": "application/json",
    }
    r2 = requests.get(api_url, headers=api_headers, timeout=30)
    if r2.status_code != 200:
        raise RuntimeError(f"F4 /api/play HTTP {r2.status_code}: {r2.text[:120]}")

    data = r2.json()
    stream = data.get("src") or data.get("url")
    if not stream:
        raise RuntimeError("F4 play response tanpa src/url")

    # relative /v/token → absolut
    if stream.startswith("/"):
        stream = urljoin(origin + "/", stream.lstrip("/"))

    return stream, origin


def fetch_sextb_player_html(session, page_url, film_id, episode, pt, page_headers):
    """
    POST /ajax/player → decrypt player_enc.
    Return (player_enc, next_pt, next_pk).
    """
    ajax_headers = {
        **page_headers,
        "Referer": page_url,
        "Origin": "https://sextb.net",
        "X-Requested-With": "XMLHttpRequest",
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }

    endpoints = [
        "https://sextb.net/ajax/player",
        "https://www.sextb.net/ajax/player",
    ]
    last_status = None
    last_body = ""
    for endpoint in endpoints:
        r = session.post(
            endpoint,
            headers=ajax_headers,
            data={"episode": episode, "filmId": film_id, "pt": pt},
            timeout=30,
        )
        last_status = r.status_code
        last_body = r.text[:200]
        if r.status_code == 200:
            try:
                item = json.loads(r.text)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"ajax/player bukan JSON: {r.text[:80]}") from exc
            if item.get("error"):
                raise RuntimeError(f"ajax/player error: {item.get('error')}")
            return (
                item.get("player_enc") or "",
                item.get("next_pt") or pt,
                item.get("next_pk") or "",
            )

    raise RuntimeError(
        f"ajax/player HTTP {last_status}. "
        "Cloudflare memblokir. Install: pip install cloudscraper  "
        "atau paste link F4 embed / m3u8 manual."
    )


def process_sextb(url: str):
    section("Fetching SEXTB")

    try:
        session = make_session()
        page_headers = {
            "User-Agent": SEXTB_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }

        host = (urlparse(url).hostname or "").lower()
        path = urlparse(url).path or ""

        # Stream HLS langsung (m3u8 / index.txt / path /u/... di CDN F4)
        if (
            ".m3u8" in url
            or url.rstrip("/").endswith(".txt")
            or "/index.txt" in url
            or ("/u/" in path and "f4scdn.com" in host)
        ):
            info("Mode", "stream langsung")
            origin = f"{urlparse(url).scheme}://{urlparse(url).hostname}"
            return download_stream("sextb_stream", url, origin, "sextb")

        # Embed F4: /e/CODE
        if any(h in host for h in ("f4scdn.com", "f4stream.com", "f2stb.com", "f4s.top")):
            info("Mode", "F4 embed")
            stream, origin = fetch_f4_stream(url)
            title = safe_filename(path.strip("/").replace("/", "_")) or "f4_video"
            return download_stream(title, stream, origin, "sextb")

        kind = getattr(session, "_lapendoz_kind", "requests")
        info("HTTP client", kind)

        r = session.get(url, headers=page_headers, timeout=40)
        if r.status_code != 200:
            raise RuntimeError(
                f"HTTP {r.status_code} dari SEXTB (Cloudflare memblokir IP Termux).\n"
                "  Solusi yang pasti berhasil:\n"
                "  1) Buka link di Chrome HP → Inspect/Network → cari f4scdn.com/e/...\n"
                "     lalu paste link embed F4 ke Lapendoz\n"
                "  2) Atau copy URL m3u8 / index.txt dari Network, paste di mode manual\n"
                "  3) Opsional: pip install curl_cffi cloudscraper (kadang membantu)"
            )

        content = r.text
        if "cf-browser-verification" in content or "Just a moment" in content:
            raise RuntimeError(
                "Cloudflare challenge aktif. "
                "Install cloudscraper (`pip install cloudscraper`) lalu coba lagi, "
                "atau paste link embed F4 / m3u8 manual."
            )

        title = find_sextb_title(content)
        pt, pk = extract_tokens(content)
        episodes = extract_episodes(content)

        info("Title", title)

        if not episodes:
            raise RuntimeError("Tidak ada server episode di halaman")

        if not pt or not pk:
            raise RuntimeError("Token __pt / __pk tidak ditemukan di halaman")

        last_err = None
        for ep in episodes:
            try:
                info("Server", f"film={ep['filmId']} ep={ep['episode']}")
                enc, next_pt, next_pk = fetch_sextb_player_html(
                    session, url, ep["filmId"], ep["episode"], pt, page_headers
                )
                player_html = xor_decrypt(enc, pk)
                if not player_html and next_pk:
                    player_html = xor_decrypt(enc, next_pk)
                if next_pt:
                    pt = next_pt
                if next_pk:
                    pk = next_pk
                if not player_html:
                    raise RuntimeError("gagal decrypt player_enc")

                embed = extract_f4_embed(player_html)
                if not embed:
                    m = re.search(
                        r'https?://[^\s"\'<>]+(?:m3u8|index\.txt)[^\s"\'<>]*',
                        player_html,
                        re.I,
                    )
                    if m:
                        stream = m.group(0)
                        origin = f"{urlparse(stream).scheme}://{urlparse(stream).hostname}"
                        return download_stream(title, stream, origin, "sextb")
                    raise RuntimeError("embed F4 tidak ada di player HTML")

                info("Embed", embed)
                stream, origin = fetch_f4_stream(embed)
                return download_stream(title, stream, origin, "sextb")

            except Exception as exc:
                last_err = exc
                warn(f"Server gagal: {exc}")
                continue

        raise RuntimeError(f"Semua server gagal. Terakhir: {last_err}")

    except RuntimeError as exc:
        error(str(exc))
        return False

    except requests.RequestException as exc:
        error(f"SEXTB request error: {exc}")
        return False

    except KeyboardInterrupt:
        error("Download dibatalkan")
        return False

    except Exception as exc:
        error(f"SEXTB error: {exc}")
        return False
