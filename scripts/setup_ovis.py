"""Download llama.cpp + the OvisOCR3 GGUF bundle (one-time, ~670 MB).

Usage:  .venv\\Scripts\\python.exe scripts\\setup_ovis.py

Everything lands in %LOCALAPPDATA%\\OCRStudio\\ so the exe itself stays small.
"""

from __future__ import annotations

import os
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "OCRStudio"
LLAMA_DIR = ROOT / "llama"
OVIS_DIR = ROOT / "ovis"

LLAMA_TAG = "b12001"
LLAMA_URL = (
    f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}"
    f"/llama-{LLAMA_TAG}-bin-win-cpu-x64.zip"
)
HF = "https://huggingface.co/mradermacher/OvisOCR3-GGUF/resolve/main/"
TARGETS = [
    (LLAMA_URL, ROOT / "llama.zip", "llama.cpp"),
    (HF + "OvisOCR3.Q4_K_M.gguf", OVIS_DIR / "OvisOCR3.Q4_K_M.gguf", "model Q4_K_M"),
    (HF + "OvisOCR3.mmproj-Q8_0.gguf", OVIS_DIR / "OvisOCR3.mmproj-Q8_0.gguf", "vision projector"),
]


def fetch(url: str, dest: Path, label: str, attempts: int = 40) -> bool:
    """Download with HTTP-range resume; the link here drops often."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    for i in range(1, attempts + 1):
        have = dest.stat().st_size if dest.exists() else 0
        if total and have >= total:
            break
        req = urllib.request.Request(
            url, headers={"User-Agent": "ocr-studio", "Range": f"bytes={have}-"}
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                cr = r.headers.get("Content-Range")
                if cr:
                    total = int(cr.split("/")[-1])
                mode = "ab" if r.status == 206 else "wb"
                if mode == "wb":
                    have = 0
                t0 = time.time()
                with open(dest, mode) as f:
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        have += len(chunk)
                        if time.time() - t0 > 10:
                            pct = f"{have / total * 100:.0f}%" if total else "?"
                            print(f"  {label}: {have / 1e6:.0f} MB {pct}", flush=True)
                            t0 = time.time()
        except Exception as exc:  # noqa: BLE001
            print(f"  {label}: putus ({type(exc).__name__}), lanjut percobaan {i}", flush=True)
            time.sleep(2)
            continue
        have = dest.stat().st_size
        if not total or have >= total:
            break
    have = dest.stat().st_size if dest.exists() else 0
    ok = bool(total) and have >= total - 1024
    print(f"[{'ok' if ok else 'GAGAL'}] {label}: {have / 1e6:.0f} MB", flush=True)
    return ok


def main() -> int:
    print(f"tujuan: {ROOT}\n", flush=True)
    for url, dest, label in TARGETS:
        if dest.exists() and dest.stat().st_size > 1024:
            print(f"[skip] {label} sudah ada ({dest.stat().st_size / 1e6:.0f} MB)", flush=True)
            continue
        if not fetch(url, dest, label):
            return 1

    zip_path = ROOT / "llama.zip"
    if zip_path.exists() and not (LLAMA_DIR / "llama-server.exe").exists():
        print("ekstrak llama.cpp...", flush=True)
        LLAMA_DIR.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(LLAMA_DIR)

    missing = [
        p.name
        for p in (LLAMA_DIR / "llama-server.exe", OVIS_DIR / "OvisOCR3.Q4_K_M.gguf",
                  OVIS_DIR / "OvisOCR3.mmproj-Q8_0.gguf")
        if not p.exists()
    ]
    if missing:
        print("\nBELUM LENGKAP:", ", ".join(missing))
        return 1
    print("\nSiap. Pilih model OvisOCR3 di dropdown aplikasi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
