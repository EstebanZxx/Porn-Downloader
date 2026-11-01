# Ultimate Video Downloader (Termux)

Downloader CLI untuk Android/Termux. Otomatis mendeteksi sumber dari URL, lalu menyimpan video ke `/sdcard/Zxx`.

## Sumber yang didukung

| Mode      | Deteksi                          | Folder output          |
|-----------|----------------------------------|------------------------|
| NJAVTV    | `njavtv.com`                     | `/sdcard/Zxx/NJAV`     |
| PHUB      | `pornhub.com`                    | `/sdcard/Zxx/PHUB`     |
| Hamster   | domain yang mengandung `xhamster`| `/sdcard/Zxx/XHAMSTER` |
| Xvideos   | domain yang mengandung `xvideos` | `/sdcard/Zxx/XVIDEOS`  |
| Eporner   | domain yang mengandung `eporner` | `/sdcard/Zxx/EPORNER`  |
| HQporner  | domain yang mengandung `hqporner`| `/sdcard/Zxx/HQPORNER` |
| Vidara    | domain yang mengandung `vidara`  | `/sdcard/Zxx/VIDARA`   |
| AvTube    | `avtub...` atau `66.29.129.113`  | `/sdcard/Zxx/AVTUBE`   |
| JAVStory1 | domain yang mengandung `javstory`| `/sdcard/Zxx/JAVSTORY` |
| JAVSubindo| domain yang mengandung `javsubindo`| `/sdcard/Zxx/JAVSUBINDO` |
| JAVBOS    | domain yang mengandung `javbos`  | `/sdcard/Zxx/JAVBOS`   |
| RumahPerjaka | domain yang mengandung `rumahperjaka` | `/sdcard/Zxx/RUMAHPERJAKA` |
| KingBokep | domain yang mengandung `kingbokep` | `/sdcard/Zxx/KINGBOKEP` |
|           | player Vidara dan vstream        |                        |
| Manual    | link lain (m3u8 atau file mp4)   | `/sdcard/Zxx/MANUAL`   |

Link yang tidak dikenali otomatis masuk ke **mode manual**. Di mode ini script mengecek isi link:
- Kalau playlist HLS (`#EXTM3U`), diunduh sebagai m3u8.
- Kalau file biasa (mp4 dan sejenisnya), diunduh langsung.

Halaman HTML hasil fetch (untuk debugging extractor) disimpan di `/sdcard/Zxx/Html/`.

## Tampilan

Secara default, tampilan dibuat bersih: kotak di tengah, dan info teknis seperti URL, stream, dan jumlah segmen disembunyikan.

Kotak banner juga menampilkan total ukuran folder `Zxx` dan folder `.temp`.

Untuk tampilan lengkap, ubah `CLEAN_UI = True` menjadi `CLEAN_UI = False` di `core/common.py`.

## Pause dan resume

- **Ctrl+P**: pause download segmen HLS (dan proses aria2c atau ffmpeg yang sedang berjalan).
- **Ctrl+R**: lanjutkan.
- Ketik **`resume`** di prompt URL untuk melihat daftar download yang belum selesai, lalu pilih nomornya.

Folder sementara di `.temp` dinamai sesuai judul video dan menyimpan `meta.json`. Segmen yang sudah selesai dilewati saat dilanjutkan. Link sumber disimpan, jadi token yang sudah kedaluwarsa dibuat ulang dari link asal.

Perintah `clear` juga menghapus progres resume.

## Instalasi di Termux

```bash
pkg update && pkg upgrade
pkg install python ffmpeg aria2   # aria2 opsional tapi disarankan, lebih cepat
termux-setup-storage        # izinkan akses penyimpanan, wajib untuk /sdcard
cd Lapendoz
pip install -r requirements.txt
```

## Cara pakai

```bash
python main.py
```

Di prompt `URL`, tempel satu atau beberapa link (dipisah spasi atau baris baru), lalu tekan Enter.

Perintah di prompt:
- `speedtest` : cek kecepatan internet (butuh `speedtest-cli`)
- `clear` : hapus semua isi folder `/sdcard/Zxx/.temp` (folder-nya tetap ada)
- `exit` atau `quit` : keluar

Untuk link yang masuk mode manual, script akan meminta judul video. Judul ini dipakai sebagai nama file.

## Struktur proyek

```
Lapendoz/
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
    ├── vidara.py
    ├── avtube.py
    ├── javstory.py
    ├── javsubindo.py
    ├── javbos.py
    ├── rumahperjaka.py
    ├── kingbokep.py
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
