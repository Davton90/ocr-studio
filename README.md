# OCR Studio

Aplikasi OCR lokal: taruh gambar atau PDF, dapat teks + kotak deteksi. Jalan 100% offline di CPU, tanpa GPU, tanpa cloud.

![status](https://img.shields.io/badge/model-PP--OCRv6-7c9cff) ![runtime](https://img.shields.io/badge/runtime-ONNX%20Runtime-4ade80)

---

## Cara menjalankan

Ada dua bentuk build. Isinya sama persis — bedanya cuma kecepatan start.

| | Portable (folder) | Satu file |
|---|---|---|
| Lokasi | `dist\OCR-Studio-portable\OCR-Studio.exe` | `dist\OCR-Studio.exe` |
| Ukuran | 217 MB (folder) | 90 MB (satu file) |
| Start sampai jendela muncul | **~5 s** | ~12 s |
| Cocok untuk | dipakai sehari-hari | kirim lewat chat / flashdisk |

### 1. Versi portable (disarankan)

```
dist\OCR-Studio-portable\OCR-Studio.exe
```

Belum ada? Bangun sendiri dengan `build-portable.bat` (lihat bagian *Membangun ulang*).

Dobel-klik → jendela aplikasi muncul. File pendukung ada di folder `_internal` di sebelah exe, jadi **folder ini harus disalin utuh** (jangan pisahkan exe-nya).

Bisa ditaruh di flashdisk dan dijalankan di komputer lain tanpa install apa pun.

### 2. Versi satu file

```
dist\OCR-Studio.exe
```

Satu file 90 MB yang mengekstrak dirinya ke folder temp setiap kali dijalankan — itu sebabnya start-nya lebih lambat.

Keduanya:
- Tidak butuh Python, tidak butuh internet (model sudah ikut di dalam)
- Jendela native pakai **WebView2** yang sudah ada di Windows 10/11
- Dobel-klik dua kali tidak bikin dua instance: yang kedua langsung keluar
- Model di-cache di `%LOCALAPPDATA%\OCRStudio\models`, log di `%LOCALAPPDATA%\OCRStudio\app.log`

#### Kenapa UI-nya HTML tapi jendelanya native?

Mesin OCR hidup di ekosistem Python, sedangkan UI paling enak dibangun dengan HTML/CSS. Jadi arsitekturnya:

```
[ Jendela native (WebView2) ]  ← hanya menampilkan
            ↓ HTTP ke 127.0.0.1
[ Proses Python lokal ]        ← semua OCR di sini
            ↓
[ ONNX Runtime + model ]
```

- `127.0.0.1` = alamat loopback, **tidak ada data yang keluar dari komputer**. Bisa dites dengan mematikan Wi-Fi: tetap jalan.
- Browser hanya lapisan tampilan; kalau mau, mode browser juga tersedia (lihat bagian 2).
- Alternatif "native murni" (Qt/Tkinter) akan menambah **60–80 MB** ke exe. WebView2 hanya menambah **2 MB** karena engine-nya sudah bagian dari Windows.

#### Isi di dalam exe (90 MB terkompresi → 215 MB saat diekstrak)

| Komponen | Ukuran | Peran |
|---|---:|---|
| OpenCV (`cv2.pyd`) | 86 MB | resize, konversi warna, warp perspective |
| **ONNX Runtime** | 39 MB | **mesin inferensi** yang menjalankan model |
| NumPy | 28 MB | operasi array/tensor |
| Pillow | 13 MB | decode gambar, EXIF, encode preview |
| PDFium | 7 MB | render halaman PDF |
| **Model OCR** (det + rec + cls) | 6.9 MB | **bobot model PP-OCRv6 tiny** |
| Python interpreter | 6 MB | runtime |
| FastAPI + Uvicorn | 5.5 MB | server lokal |
| Shapely | 4 MB | geometri kotak teks |
| pywebview + pythonnet | 2 MB | jendela native (WebView2) |
| RapidOCR | 0.1 MB | pipeline deteksi → klasifikasi → rekognisi |
| UI web | 0.2 MB | HTML/CSS/JS |

Jadi **mesin OCR-nya sendiri hanya ~46 MB** (ONNX Runtime + model + pipeline). Sisanya pustaka pendukung — OpenCV sendirian 40% dari total.

> `opencv_videoio_ffmpeg` (31 MB) sengaja dibuang dari build karena hanya dipakai untuk membaca file video, sementara aplikasi ini hanya memproses gambar dan PDF.

### 3. Dari source

```
start.bat
```

Jendela aplikasi langsung terbuka. Atau manual:

```bat
.venv\Scripts\python.exe desktop.py     :: jendela native
.venv\Scripts\python.exe server.py      :: mode browser di http://127.0.0.1:8848
```

Kalau port 8848 dipakai, aplikasi pindah sendiri ke 8849/8850.

### Membangun ulang

```
build-portable.bat    :: -> dist\OCR-Studio-portable\   (onedir, start cepat)
build.bat             :: -> dist\OCR-Studio.exe         (onefile, satu file)
```

Butuh `.venv` (dibuat otomatis oleh `start.bat`) dan PyInstaller (dipasang otomatis oleh skrip build).

---

## Model yang dipakai

**PP-OCRv6 (tiny) — deteksi + pengenalan**, dijalankan lewat **RapidOCR 3.10** di atas **ONNX Runtime**.

| Komponen | Ukuran | Peran |
|---|---|---|
| `PP-OCRv6_det_tiny` | ~1.5 MB | cari kotak teks (DB) |
| `PP-OCRv6_rec_tiny` | ~5 MB | ubah kotak jadi teks (CTC) |
| `cls` (LCNet) | 0.6 MB | deteksi teks terbalik 180° |

Total < 10 MB, dan mendukung 100+ bahasa dalam satu model — termasuk **Indonesia, Inggris, Mandarin, Jepang, Arab, Cyrillic**.

### Kenapa ini, bukan yang lain

| Kandidat | Alasan tidak dipakai di mesin ini |
|---|---|
| **PaddleOCR** (asli) | butuh `paddlepaddle` ~500 MB, install ribuan file, sering bentrok di Windows |
| **EasyOCR / Surya / TrOCR** | berbasis PyTorch, ~2 GB dependency, lambat tanpa GPU |
| **Tesseract 5** | paling ringan, tapi akurasi di foto miring/noise jauh di bawah model deep learning |
| **DeepSeek-OCR, PaddleOCR-VL, dots.ocr, olmOCR** | VLM 0.9–3B parameter — butuh GPU, 8–24 GB VRAM. Tidak realistis di CPU |
| **RapidOCR + PP-OCRv6** ✅ | ONNX, ~35 MB total dependency, akurasi setara PaddleOCR, jalan di 2 core |

Catatan: varian `small` (default upstream) ternyata **6–7× lebih lambat** di mesin ini (18 s vs 2.8 s) dengan hasil yang sama pada uji coba. Karena itu `tiny` jadi default — bisa diganti lewat dropdown di pojok kanan atas.

---

## Fitur

- **Drag & drop**, klik pilih file, atau **Ctrl+V** tempel dari clipboard (screenshot langsung)
- **Gambar & PDF** (multi-halaman, dengan navigasi halaman)
- **Overlay kotak deteksi** berwarna sesuai confidence — arahkan kursor untuk lihat teks + skor, klik untuk lompat ke baris
- **Zoom canvas** sampai 800% — scroll untuk zoom di titik kursor, drag untuk menggeser, tombol `− / % / +` di header, atau `+` `-` `0` di keyboard
- Panel hasil: **Teks** (bisa diedit) dan **Baris** (per baris + skor)
- **Ekspor** `.txt`, `.md`, `.json`, `.csv` (CSV memuat koordinat kotak)
- **Salin** ke clipboard sekali klik
- Ganti model **tiny / small / medium** saat runtime, plus toggle **auto-rotate**
- Statistik per halaman: waktu, jumlah baris, akurasi rata-rata, rincian det/cls/rec

---

## Performa terukur (mesin ini: 2 vCPU, tanpa GPU)

| Input | Waktu |
|---|---|
| PNG 900×380 (6 baris) | **2.6–3.2 s** |
| PDF A4 per halaman (1191×1684) | **~4.8 s** |
| Muat model pertama kali | ~3 s |
| Start portable (onedir) sampai jendela muncul | **~5 s** |
| Start satu file (onefile) sampai jendela muncul | ~12 s |

Angka ini akan jauh lebih cepat di mesin dengan core lebih banyak.

> Catatan: `EngineConfig.onnxruntime.enable_cpu_mem_arena` sengaja di-set `True`. Default upstream (`False`) menyebabkan lonjakan latensi sampai 28 detik di CPU 2-core.

---

## Struktur

```
ocr-studio/
├─ dist/
│  ├─ OCR-Studio-portable/  # build onedir (start ~5 s)
│  └─ OCR-Studio.exe        # build onefile 90 MB
├─ build.bat              # build onefile
├─ build-portable.bat     # build onedir
├─ build.spec             # konfigurasi PyInstaller (onefile)
├─ build-portable.spec    # konfigurasi PyInstaller (onedir)
├─ start.bat              # launcher dari source (buat venv otomatis)
├─ desktop.py             # entry point: jendela native (WebView2)
├─ server.py              # FastAPI + manajer engine OCR (juga mode browser)
├─ requirements.txt
├─ assets/
│  ├─ icon.ico
│  └─ models/             # model tiny + cls yang dibundel ke exe
├─ web/
│  ├─ index.html
│  ├─ styles.css
│  └─ app.js
├─ samples/               # gambar & PDF contoh
└─ scripts/
   ├─ smoke_test.py       # uji cepat engine
   ├─ bench_models.py     # bandingkan tiny/small/medium
   ├─ bench_threads.py    # bandingkan konfigurasi thread ONNX
   └─ make_icon.py        # generate ikon aplikasi
```

---

## API

| Endpoint | Keterangan |
|---|---|
| `GET /api/status` | state engine, model aktif, info host |
| `POST /api/config` | `{"variant":"tiny","use_cls":true}` — ganti model |
| `POST /api/ocr` | multipart `file` (+ `pages="1-3,5"` untuk PDF) |
| `GET /api/sample` | gambar contoh |

Contoh:

```bash
curl -X POST http://127.0.0.1:8848/api/ocr -F "file=@dokumen.pdf"
```

Respons per halaman:

```json
{
  "name": "dokumen.pdf",
  "kind": "pdf",
  "pages": [{
    "index": 1, "width": 1191, "height": 1684,
    "elapsed_ms": 4881,
    "stages_ms": {"det": 3510, "cls": 50, "rec": 1265},
    "text": "Halaman 1 - Kontrak\n...",
    "lines": [{"text": "...", "score": 0.98, "box": [[x,y],[x,y],[x,y],[x,y]]}],
    "image": "data:image/jpeg;base64,..."
  }]
}
```

---

## Offline / pindah mesin

**Versi `.exe` sudah sepenuhnya offline** — model `tiny` + `cls` (6.6 MB) ikut di dalam file. Cukup salin `dist\OCR-Studio.exe` ke mesin lain, dobel-klik, selesai. Tidak perlu Python, tidak perlu internet.

Model di-cache ke `%LOCALAPPDATA%\OCRStudio\models` pada peluncuran pertama (sekadar menyalin dari dalam exe). Kalau kamu memilih varian **Small/Medium**, model itu belum ikut dibundel sehingga akan diunduh sekali ke folder yang sama (butuh internet saat itu saja).

Untuk versi source, model tersimpan di `.venv\Lib\site-packages\rapidocr\models\`; salin seluruh folder `ocr-studio/` beserta `.venv` bila ingin memindahkannya.

---

## Troubleshooting

| Masalah | Solusi |
|---|---|
| `start.bat` langsung tertutup | jalankan `start.bat` dari Command Prompt untuk lihat error |
| Exe terasa lama terbuka | normal 6–10 s (ekstrak 215 MB). Pakai `start.bat` kalau ingin start instan |
| Jendela tidak muncul | WebView2 butuh Windows 10/11 terbaru; kalau gagal, aplikasi otomatis membuka browser. Log: `%LOCALAPPDATA%\OCRStudio\app.log` |
| Exe tidak mau jalan / langsung hilang | cek `%LOCALAPPDATA%\OCRStudio\app.log` |
| Windows Defender memblokir exe | umum untuk PyInstaller tanpa code signing — pilih "More info → Run anyway", atau jalankan dari source |
| Hasil lambat | pastikan model `Tiny`; tutup aplikasi berat lain (mesin ini hanya 2 core) |
| Model medium terasa hang | normal — varian medium 3–5× lebih berat; pakai `Tiny` |
| Teks miring tidak terbaca | aktifkan **Auto-rotate** |
| Ingin ganti bahasa | tidak perlu — model PP-OCRv6 multilingual sudah mencakup 100+ bahasa |
