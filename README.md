# Ultimate Video Downloader (Termux)

Downloader CLI untuk Android/Termux. Otomatis mendeteksi sumber dari URL, lalu menyimpan video ke `/sdcard/JAV`.

## Sumber yang didukung

| Mode      | Deteksi                          | Folder output          |
|-----------|----------------------------------|------------------------|
| NJAVTV    | `njavtv.com`                     | `/sdcard/JAV/NJAV`     |
| PHUB      | `pornhub.com`                    | `/sdcard/JAV/PHUB`     |
| Hamster   | domain yang mengandung `xhamster`| `/sdcard/JAV/XHAMSTER` |
| Xvideos   | domain yang mengandung `xvideos` | `/sdcard/JAV/XVIDEOS`  |
| Eporner   | domain yang mengandung `eporner` | `/sdcard/JAV/EPORNER`  |
| HQporner  | domain yang mengandung `hqporner`| `/sdcard/JAV/HQPORNER` |
| Manual    | link lain (m3u8 atau file mp4)   | `/sdcard/JAV/MANUAL`   |

Link yang tidak dikenali otomatis masuk ke **mode manual**. Di mode ini script mengecek isi link:
- Kalau playlist HLS (`#EXTM3U`), diunduh sebagai m3u8.
- Kalau file biasa (mp4 dan sejenisnya), diunduh langsung.

## Instalasi di Termux

```bash
pkg update && pkg upgrade
pkg install python ffmpeg
termux-setup-storage        # izinkan akses penyimpanan, wajib untuk /sdcard
cd JAV-Downloader
pip install -r requirements.txt
```

## Cara pakai

```bash
python main.py
```

Di prompt `URL`, tempel satu atau beberapa link (dipisah spasi atau baris baru), lalu tekan Enter.

Perintah di prompt:
- `speedtest` : cek kecepatan internet (butuh `speedtest-cli`)
- `exit` atau `quit` : keluar

Untuk link yang masuk mode manual, script akan meminta judul video. Judul ini dipakai sebagai nama file.

## Struktur proyek

```
JAV-Downloader/
├── main.py              # entry point, menu dan loop utama
├── requirements.txt
├── README.md
├── core/
│   ├── common.py        # config, UI, helper HTTP, download HLS dan file langsung
│   └── detect.py        # deteksi sumber dari URL
└── sources/
    ├── njav.py
    ├── phub.py
    ├── hamster.py
    ├── xvideos.py
    ├── eporner.py
    ├── hqporner.py
    └── manual.py
```

Untuk menambah sumber baru:
1. Buat file baru di `sources/`, misalnya `sources/namasumber.py`, dengan fungsi `process_namasumber(url)` yang mengembalikan `True` jika berhasil.
2. Tambahkan folder di `SOURCE_FOLDERS` pada `core/common.py`.
3. Tambahkan aturan deteksi di `detect_source()` pada `core/detect.py`.
4. Import fungsi itu di `main.py` dan tambahkan cabang `elif` di loop.

## Catatan

- Link dari situs video biasanya punya token dengan masa berlaku (`expiry`). Jalankan segera setelah link didapat.
- Beberapa situs mengubah struktur halamannya, sehingga extractor bisa berhenti bekerja. Kalau itu terjadi, mode manual tetap bisa dipakai.
- Program ini hanya untuk konten yang kamu punya hak untuk mengunduhnya. Patuhi ketentuan layanan masing-masing situs.

## Lisensi

Proyek ini dilisensikan di bawah [MIT License](LICENSE).
