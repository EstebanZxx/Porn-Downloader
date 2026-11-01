from core.common import *
from sources.vidara import download_stream
from urllib.parse import urlparse
import base64
import json

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
except ImportError:
    AESGCM = None


YSTREAM_API = "https://ystream.id"
YSTREAM_HOSTS = ("ystream.id", "n1mwq.org")


def _b64url_decode(data: str) -> bytes:
    s = data.replace("-", "+").replace("_", "/")
    pad = (4 - len(s) % 4) % 4
    return base64.b64decode(s + ("=" * pad))


def decrypt_ystream_playback(playback: dict) -> dict:
    """
    Dekripsi field playback dari /api/videos/{code}/
    (AES-256-GCM, key dari key_parts + version).
    """
    if AESGCM is None:
        raise RuntimeError(
            "Paket cryptography belum terpasang. "
            "Jalankan: pip install cryptography"
        )

    key_parts = playback.get("key_parts") or []
    version = str(playback.get("version") or "").strip()
    iv_b64 = playback.get("iv") or ""
    payload_b64 = playback.get("payload") or ""

    if not key_parts or not iv_b64 or not payload_b64:
        raise RuntimeError("playback ystream tidak lengkap")

    # Qa(version) -> indeks 1-based [n, 31-n]
    selected = key_parts
    if version.isdigit():
        n = int(version)
        a, b = n, 31 - n
        if 1 <= a <= len(key_parts) and 1 <= b <= len(key_parts):
            selected = [key_parts[a - 1], key_parts[b - 1]]

    key = b"".join(_b64url_decode(p) for p in selected if p)
    iv = _b64url_decode(iv_b64)
    payload = _b64url_decode(payload_b64)

    if len(key) not in (16, 24, 32):
        raise RuntimeError(f"panjang key AES tidak valid: {len(key)}")

    plain = AESGCM(key).decrypt(iv, payload, None)
    return json.loads(plain.decode("utf-8"))


def find_avpinay_title(content: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", content, re.DOTALL | re.IGNORECASE)
    title = html.unescape(match.group(1)).strip() if match else "avpinay_video"
    title = re.split(r"\s*[-–]\s*AVPinay\s*$", title, flags=re.IGNORECASE)[0]
    title = re.sub(r"\s+", " ", title).strip()
    return safe_filename(title) or "avpinay_video"


def find_ystream_code(content: str) -> str | None:
    """Ambil kode embed ystream dari iframe / URL di halaman."""
    patterns = [
        r'https?://(?:ystream\.id|n1mwq\.org)/e/([A-Za-z0-9_\-]+)',
        r'https?://(?:ystream\.id|n1mwq\.org)/[a-z0-9]+/([A-Za-z0-9_\-]+)',
        r'src=["\']https?://ystream\.id/e/([A-Za-z0-9_\-]+)',
    ]
    for pat in patterns:
        m = re.search(pat, content, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def fetch_ystream_stream(code: str, page_url: str):
    """
    Ambil metadata + m3u8 dari API ystream.
    Return (title, stream_url, origin).
    """
    api_headers = {
        **headers,
        "Referer": f"{YSTREAM_API}/e/{code}/",
        "Origin": YSTREAM_API,
        "Accept": "application/json",
    }

    r = requests.get(
        f"{YSTREAM_API}/api/videos/{code}/",
        headers=api_headers,
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ystream API HTTP {r.status_code}")

    data = r.json()
    title = data.get("title") or code
    playback = data.get("playback")
    if not playback:
        raise RuntimeError("field playback kosong di respons ystream")

    decoded = decrypt_ystream_playback(playback)
    sources = decoded.get("sources") or []
    if not sources:
        raise RuntimeError("sources kosong setelah dekripsi playback")

    # pilih kualitas tertinggi (height)
    sources = sorted(
        sources,
        key=lambda s: int(s.get("height") or 0),
        reverse=True,
    )
    best = sources[0]
    stream = best.get("url")
    if not stream:
        raise RuntimeError("URL stream tidak ada di sources")

    label = best.get("label") or best.get("quality") or ""
    info("Quality", label)
    return safe_filename(title), stream, YSTREAM_API


def process_avpinay(url: str):
    section("Fetching AVPinay")

    try:
        page_headers = build_dynamic_headers(url)
        r = requests.get(url, headers=page_headers, timeout=30)

        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} dari halaman AVPinay")

        content = r.text
        title = find_avpinay_title(content)
        code = find_ystream_code(content)

        if not code:
            # mungkin user langsung paste link ystream
            parsed = urlparse(url)
            host = (parsed.hostname or "").lower()
            if "ystream" in host or "n1mwq" in host:
                m = re.search(r"/e/([A-Za-z0-9_\-]+)", parsed.path)
                if not m:
                    m = re.search(r"/([A-Za-z0-9_\-]{6,})$", parsed.path)
                code = m.group(1) if m else None
                title = title if title != "avpinay_video" else (code or "ystream_video")

        if not code:
            raise RuntimeError(
                "Embed ystream tidak ditemukan. "
                "Paste link m3u8 di mode manual."
            )

        info("Title", title)
        info("Ystream", code)

        stream_title, stream, origin = fetch_ystream_stream(code, url)
        # pakai judul halaman AVPinay kalau lebih bersih
        final_title = title if title and title != "avpinay_video" else stream_title

        return download_stream(final_title, stream, origin, "avpinay")

    except RuntimeError as exc:
        error(str(exc))
        return False

    except requests.RequestException as exc:
        error(f"AVPinay request error: {exc}")
        return False

    except KeyboardInterrupt:
        error("Download dibatalkan")
        return False

    except Exception as exc:
        error(f"AVPinay error: {exc}")
        return False
