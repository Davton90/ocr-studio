# OCR Studio

Aplikasi OCR lokal: taruh gambar atau PDF, dapat teks + kotak deteksi. Jalan 100% offline di CPU, tanpa GPU, tanpa cloud.

![status](https://img.shields.io/badge/model-PP--OCRv6-7c9cff) ![runtime](https://img.shields.io/badge/runtime-ONNX%20Runtime-4ade80)

---

## Cara menjalankan

Ada dua bentuk build. Isinya sama persis — bedanya cuma kecepatan start.

| | Portable (folder) | Satu file |
|---|---|---|
| Lokasi | `dist\OCR-Studio-portable\OCR-Studio.exe` | `dist\OCR-Studio.exe` |
| Ukuran | 279 MB (folder) | 116 MB (satu file) |
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

Satu file 116 MB yang mengekstrak dirinya ke folder temp setiap kali dijalankan — itu sebabnya start-nya lebih lambat.

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

#### Isi di dalam exe (116 MB terkompresi → 279 MB saat diekstrak)

| Komponen | Ukuran | Peran |
|---|---:|---|
| OpenCV (`cv2.pyd`) | 86 MB | resize, konversi warna, warp perspective |
| **ONNX Runtime** | 39 MB | **mesin inferensi** yang menjalankan model |
| NumPy | 28 MB | operasi array/tensor |
| Pillow | 13 MB | decode gambar, EXIF, encode preview |
| PDFium | 7 MB | render halaman PDF |
| **Model OCR** (det + rec + cls) | 6.9 MB | **bobot model PP-OCRv6 tiny** |
| **Model Indra** (det, rec, order, orient, script) | 8.8 MB | **bobot engine Indra OCR** |
| Python interpreter | 6 MB | runtime |
| FastAPI + Uvicorn | 5.5 MB | server lokal |
| Shapely | 4 MB | geometri kotak teks |
| pywebview + pythonnet | 2 MB | jendela native (WebView2) |
| pillow-heif + libheif | 3 MB | decode HEIC/HEIF (foto iPhone) |
| pillow-jxl + libjxl | 11 MB | decode JPEG XL |
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

Ada **dua engine** yang bisa dipilih dari dropdown *Model* di pojok kanan atas. Keduanya ONNX Runtime, keduanya offline.

| | **Indra** (default baru) | **PP-OCRv6 tiny** |
|---|---|---|
| Pembuat | Datalab | PaddlePaddle / Baidu |
| Ukuran model | 8.8 MB | 7 MB |
| Waktu OCR (PNG 900×380, 2 core) | **1.55 s** | 3.9 s |
| Akurasi (contoh uji) | **99.1%** | 97.9% |
| Kotak per baris | ✅ | ✅ |
| Heading / layout / reading order | ✅ | ❌ |
| Output Markdown | ✅ | ❌ |
| Auto-rotate | otomatis | lewat model `cls` |
| Lisensi model | OpenRAIL-M (cek dulu untuk komersial) | Apache-2.0 |

> **Indra** = 1M-parameter recognition model dari Datalab, dirancang khusus untuk CPU. Di mesin 2-core ini ia **2,5× lebih cepat** dan sedikit lebih akurat, plus memberi struktur dokumen (heading, list, urutan baca) yang bisa langsung diekspor ke Markdown. Modelnya dari [datalab-to/indra-ocr](https://huggingface.co/datalab-to/indra-ocr), lisensi **OpenRAIL-M** — baca dulu ketentuannya sebelum dipakai komersial.

### PP-OCRv6 (tiny) — deteksi + pengenalan

Dijalankan lewat **RapidOCR 3.10** di atas **ONNX Runtime**.

| Komponen | Ukuran | Peran |
|---|---|---|
| `PP-OCRv6_det_tiny` | ~1.5 MB | cari kotak teks (DB) |
| `PP-OCRv6_rec_tiny` | ~5 MB | ubah kotak jadi teks (CTC) |
| `cls` (LCNet) | 0.6 MB | deteksi teks terbalik 180° |

Total < 10 MB, dan mendukung 100+ bahasa dalam satu model — termasuk **Indonesia, Inggris, Mandarin, Jepang, Arab, Cyrillic**.

### OvisOCR3 (opsional, engine ketiga)

Engine VLM 0,8 B dari ATH-MaaS untuk dokumen sulit — tabel kompleks, KIE, tabel lintas halaman. **Tidak ikut di dalam exe**: bobot dan llama.cpp diunduh sekali ke `%LOCALAPPDATA%\OCRStudio\`.

```bat
.venv\Scripts\python.exe scripts\setup_ovis.py
```

| Bagian | Ukuran |
|---|---:|
| `OvisOCR3.Q4_K_M.gguf` | 529 MB |
| `OvisOCR3.mmproj-Q8_0.gguf` (vision projector) | 116 MB |
| llama.cpp `b12001` (win-cpu-x64) | 25 MB |
| **Total** | **670 MB** |

Butuh **dua file model**: `--model` untuk LLM dan `--mmproj` untuk vision projector. Projector tidak bisa dipinjam dari model lain — dimensinya harus cocok dengan decoder-nya.

**Performa terukur di mesin ini (2 core, RAM 3,8 GB):**

| Tahap | Waktu |
|---|---:|
| llama-server start + muat model | 15 s |
| Vision encoding (1 gambar) | 23,6 s |
| Generasi | ~1,3 token/detik |
| **Total per halaman kecil** | **2,5–3,5 menit** |

Angka itu bukan bug: model 0,8 B harus menulis output token demi token, dan RAM yang tersisa cuma ~0,4 GB sehingga Windows ikut swap. Di mesin 8 core / 16 GB angka ini turun drastis.

Karena itu Indra tetap default; OvisOCR3 dipakai sesekali saat butuh akurasi struktur. Output-nya masuk ke tab **Markdown** dan kotak deteksi tetap tampil (tanpa skor per baris — VLM tidak memberi confidence).

Lisensi model: **Apache 2.0** (boleh komersial).

### Kenapa ini, bukan yang lain

| Kandidat | Alasan tidak dipakai di mesin ini |
|---|---|
| **PaddleOCR** (asli) | butuh `paddlepaddle` ~500 MB, install ribuan file, sering bentrok di Windows |
| **EasyOCR / Surya / TrOCR** | berbasis PyTorch, ~2 GB dependency, lambat tanpa GPU |
| **Tesseract 5** | paling ringan, tapi akurasi di foto miring/noise jauh di bawah model deep learning |
| **DeepSeek-OCR, PaddleOCR-VL, dots.ocr, olmOCR** | VLM 0.9–3B parameter — butuh GPU, 8–24 GB VRAM. Tidak realistis di CPU |
| **RapidOCR + PP-OCRv6** ✅ | ONNX, ~35 MB total dependency, akurasi setara PaddleOCR, jalan di 2 core |
| **Indra OCR** ✅ | 8.8 MB, CPU-first, 2,5× lebih cepat dari PP-OCRv6 di mesin ini, plus layout & markdown |
| **OvisOCR3** ✅ | 0,8 B, Apache 2.0, akurasi OmniDocBench 96,7 — tapi 2,5–3,5 menit/halaman di CPU 2 core |

Catatan: varian `small` (default upstream) ternyata **6–7× lebih lambat** di mesin ini (18 s vs 2.8 s) dengan hasil yang sama pada uji coba. Karena itu `tiny` jadi default — bisa diganti lewat dropdown di pojok kanan atas.

---

## Format yang didukung

**Gambar** — 45 format (semua diuji end-to-end lewat API):

| Kategori | Format |
|---|---|
| Umum | PNG, JPEG (`.jpg` `.jpeg` `.jfif`), WebP, BMP, TIFF, GIF |
| Modern | **AVIF**, **JPEG XL** (`.jxl`), **HEIC/HEIF** (foto iPhone), JPEG 2000 (`.jp2`) |
| Langka | QOI, PSD, TGA, PCX, DDS, ICO, PNM/PPM/PGM/PBM, XBM, XPM |
| Dokumen | **PDF** (multi-halaman, dirender lewat PDFium) |

HEIC dan JPEG XL butuh plugin tambahan (`pillow-heif`, `pillow-jxl-plugin`) yang sudah ikut di `requirements.txt` dan di dalam exe. Kalau plugin tidak ada, aplikasi tetap jalan dengan 43 format bawaan Pillow.

Catatan:
- Gambar beranimasi (GIF/WebP/AVIF) hanya **frame pertama** yang diproses.
- Orientasi EXIF (foto HP yang miring) otomatis diperbaiki.
- SVG tidak didukung — perlu rasterisasi dulu.
- Ukuran dipotong ke maksimal 2000 px sisi terpanjang sebelum OCR, demi kecepatan.

---

## Fitur

- **Drag & drop**, klik pilih file, atau **Ctrl+V** tempel dari clipboard (screenshot langsung)
- **Gambar & PDF** (multi-halaman, dengan navigasi halaman)
- **Overlay kotak deteksi** berwarna sesuai confidence — arahkan kursor untuk lihat teks + skor, klik untuk lompat ke baris
- **Zoom canvas** sampai 800% — scroll untuk zoom di titik kursor, drag untuk menggeser, tombol `− / % / +` di header, atau `+` `-` `0` di keyboard
- Panel hasil: **Teks** (bisa diedit), **Baris** (per baris + skor), dan **Markdown** (muncul otomatis saat memakai engine Indra)
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
│  └─ OCR-Studio.exe        # build onefile 116 MB
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
| Exe terasa lama terbuka | normal 6–10 s (ekstrak 279 MB). Pakai `start.bat` kalau ingin start instan |
| Jendela tidak muncul | WebView2 butuh Windows 10/11 terbaru; kalau gagal, aplikasi otomatis membuka browser. Log: `%LOCALAPPDATA%\OCRStudio\app.log` |
| Exe tidak mau jalan / langsung hilang | cek `%LOCALAPPDATA%\OCRStudio\app.log` |
| Windows Defender memblokir exe | umum untuk PyInstaller tanpa code signing — pilih "More info → Run anyway", atau jalankan dari source |
| Hasil lambat | pastikan model `Tiny`; tutup aplikasi berat lain (mesin ini hanya 2 core) |
| Model medium terasa hang | normal — varian medium 3–5× lebih berat; pakai `Tiny` |
| Teks miring tidak terbaca | aktifkan **Auto-rotate** |
| Ingin ganti bahasa | tidak perlu — model PP-OCRv6 multilingual sudah mencakup 100+ bahasa |
