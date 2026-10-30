"""
OCR Studio - local OCR engine (RapidOCR / PP-OCRv6 on ONNX Runtime).

Runs fully offline on CPU. Serves a small web UI on 127.0.0.1 and exposes a
JSON API for OCR of images and PDFs.
"""

from __future__ import annotations

import atexit
import base64
import io
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
import zipfile
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pypdfium2 as pdfium
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps
from starlette.concurrency import run_in_threadpool

FROZEN = getattr(sys, "frozen", False)
# onefile: assets live in the temporary _MEIPASS dir
BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
WEB = BASE / "web"
SAMPLES = BASE / "samples"
MAX_SIDE = 2000  # downscale anything larger before OCR (CPU friendly)


def _register_optional_formats() -> None:
    """Enable formats that Pillow does not ship by default.

    HEIC/HEIF is the default format on iPhones, JPEG XL is the newer
    lossless codec. Both are optional: if the plugin is missing the rest of
    the app keeps working with the 43 formats Pillow supports natively.
    """
    try:
        import pillow_heif

        pillow_heif.register_heif_opener()
    except Exception:  # noqa: BLE001
        pass
    try:
        import pillow_jxl  # noqa: F401  (importing it registers the plugin)
    except Exception:  # noqa: BLE001
        pass


_register_optional_formats()

# Indra OCR ships its own ONNX bundle; point the package at the copy shipped
# with the app instead of the HuggingFace cache, so it works offline.
_INDRA_DIR = BASE / "assets" / "indra"
if _INDRA_DIR.is_dir():
    os.environ.setdefault("INDRA_OCR_MODEL_DIR", str(_INDRA_DIR))


def _model_dir() -> Path:
    """Writable model cache, pre-filled from the bundled models on first run."""
    root = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "OCRStudio" / "models"
    bundled = BASE / "models"
    if bundled.is_dir():
        root.mkdir(parents=True, exist_ok=True)
        for src in bundled.glob("*.onnx"):
            dst = root / src.name
            if not dst.exists() or dst.stat().st_size != src.stat().st_size:
                try:
                    shutil.copy2(src, dst)
                except OSError:
                    pass
    return root

VARIANTS = {
    "tiny": {"label": "Tiny", "note": "PP-OCRv6 · ~7 MB · cepat"},
    "small": {"label": "Small", "note": "PP-OCRv6 · ~31 MB · default upstream"},
    "medium": {"label": "Medium", "note": "PP-OCRv6 · paling akurat, paling lambat"},
    "indra": {"label": "Indra", "note": "Datalab · 8.8 MB · tercepat + layout/markdown"},
    "ovis": {"label": "OvisOCR3", "note": "0.8B VLM via llama.cpp · tabel & layout terbaik · lambat di CPU"},
}


# --------------------------------------------------------------------------- #
# OvisOCR3 via llama.cpp (optional heavy engine)
# --------------------------------------------------------------------------- #
OVIS_HOME = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "OCRStudio"
OVIS_DIR = OVIS_HOME / "ovis"
LLAMA_DIR = OVIS_HOME / "llama"
OVIS_MODEL = OVIS_DIR / "OvisOCR3.Q4_K_M.gguf"
OVIS_MMPROJ = OVIS_DIR / "OvisOCR3.mmproj-Q8_0.gguf"

OVIS_PROMPT = (
    "Analyze the document structure and extract text content. Return a single JSON "
    "array in natural reading order.\n\n"
    "Each element follows this schema:\n"
    '`{"bbox": [x_min, y_min, x_max, y_max], "category": "string", "content": "string"}`\n\n'
    "Rules:\n"
    "1. The bbox coordinates are integers scaled to [0, 1000).\n"
    "2. The category is exactly one of:\n"
    '["abstract", "algorithm", "aside_text", "chart", "content", "display_formula", '
    '"doc_title", "figure_title", "footer", "footer_image", "footnote", "formula_number", '
    '"header", "header_image", "image", "inline_formula", "number", "paragraph_title", '
    '"reference_content", "seal", "table", "text", "vertical_text", "vision_footnote"].\n'
    "3. The content formatting depends on category:\n"
    '- For "footer_image", "header_image", "image", or "chart": write as an HTML image tag '
    '<img src="images/bbox_{x_min}_{y_min}_{x_max}_{y_max}.jpg" />.\n'
    '- For "display_formula" or "inline_formula": write in LaTeX.\n'
    '- For "table": write as a standard HTML `<table>...</table>`.\n'
    "- Otherwise: write in Markdown.\n"
    "4. Output must be strictly valid JSON. Properly escape quotes and special characters "
    "inside content."
)


def _ovis_parse(raw: str, w: int, h: int) -> dict[str, Any]:
    """Turn the model's JSON block list into our line/markdown structure."""
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    try:
        blocks = json.loads(s)
    except Exception:  # noqa: BLE001
        blocks = None

    if not isinstance(blocks, list):
        text = raw.strip()
        return {"lines": [], "text": text, "markdown": text, "stages_ms": {}}

    lines: list[dict[str, Any]] = []
    md: list[str] = []
    for b in blocks:
        if not isinstance(b, dict):
            continue
        content = str(b.get("content") or "").strip()
        bb = b.get("bbox") or []
        if content:
            md.append(content)
        if len(bb) == 4:
            try:
                x0 = float(bb[0]) / 1000 * w
                y0 = float(bb[1]) / 1000 * h
                x1 = float(bb[2]) / 1000 * w
                y1 = float(bb[3]) / 1000 * h
            except (TypeError, ValueError):
                continue
            lines.append({
                "text": content,
                "score": None,  # a VLM gives no per-line confidence
                "box": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
                "category": b.get("category"),
            })
    return {
        "lines": lines,
        "text": flow_text([ln for ln in lines if ln["text"]]),
        "markdown": "\n\n".join(md),
        "stages_ms": {},
    }


class OvisInstaller:
    """Downloads llama.cpp + the OvisOCR3 weights, with progress for the UI."""

    LLAMA_TAG = "b12001"
    ZIP = OVIS_HOME / "llama.zip"
    URL_LLAMA = (
        f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}"
        f"/llama-{LLAMA_TAG}-bin-win-cpu-x64.zip"
    )
    URL_MODEL = "https://huggingface.co/mradermacher/OvisOCR3-GGUF/resolve/main/OvisOCR3.Q4_K_M.gguf"
    URL_MMPROJ = "https://huggingface.co/mradermacher/OvisOCR3-GGUF/resolve/main/OvisOCR3.mmproj-Q8_0.gguf"

    def __init__(self) -> None:
        self.state = "idle"          # idle | running | done | error
        self.message = ""
        self.done = 0
        self.total = 0
        self._lock = threading.Lock()

    # -- public ------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        pct = 0 if not self.total else min(100, round(self.done / self.total * 100))
        return {
            "state": self.state,
            "message": self.message,
            "done": self.done,
            "total": self.total,
            "percent": pct,
        }

    def start(self) -> dict[str, Any]:
        with self._lock:
            if self.state == "running":
                return self.status()
            self.state = "running"
            self.message = "menyiapkan…"
            self.done = 0
            self.total = 0
        threading.Thread(target=self._run, daemon=True, name="ovis-setup").start()
        return self.status()

    # -- internals ---------------------------------------------------------
    @staticmethod
    def _remote_size(url: str) -> int:
        """Authoritative file size, so a resumed download knows when to stop."""
        try:
            req = urllib.request.Request(
                url, method="HEAD", headers={"User-Agent": "ocr-studio"}
            )
            with urllib.request.urlopen(req, timeout=30) as r:
                return int(r.headers.get("Content-Length") or 0)
        except Exception:  # noqa: BLE001
            return 0

    def _targets(self) -> list[tuple[str, Path, str, int]]:
        out = []
        for url, dest, label in (
            (self.URL_LLAMA, self.ZIP, "llama.cpp"),
            (self.URL_MODEL, OVIS_MODEL, "model Q4_K_M"),
            (self.URL_MMPROJ, OVIS_MMPROJ, "vision projector"),
        ):
            out.append((url, dest, label, self._remote_size(url)))
        return out

    def _run(self) -> None:
        try:
            targets = self._targets()
            self.total = sum(t[3] for t in targets)
            if not self.total:
                self.state = "error"
                self.message = "tidak bisa membaca ukuran file (offline?)"
                return

            for url, dest, label, size in targets:
                dest.parent.mkdir(parents=True, exist_ok=True)
                # llama.cpp counts as done once the binary is extracted
                already = (
                    (LLAMA_DIR / "llama-server.exe").exists()
                    if dest is self.ZIP
                    else dest.exists() and dest.stat().st_size >= size - 4096
                )
                if already:
                    self._add(size, f"{label} sudah ada")
                    continue
                if not self._fetch(url, dest, label, size):
                    self.state = "error"
                    self.message = f"gagal mengunduh {label} — coba lagi"
                    return

            if self.ZIP.exists() and not (LLAMA_DIR / "llama-server.exe").exists():
                self.message = "mengekstrak llama.cpp…"
                LLAMA_DIR.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(self.ZIP) as z:
                    z.extractall(LLAMA_DIR)

            gaps = OvisBackend().missing()
            if gaps:
                self.state = "error"
                self.message = "belum lengkap: " + ", ".join(gaps)
                return
            self.state = "done"
            self.message = "model OvisOCR3 siap"
            self.done = self.total
        except Exception as exc:  # noqa: BLE001
            self.state = "error"
            self.message = f"{type(exc).__name__}: {exc}"

    def _add(self, n: int, msg: str) -> None:
        self.done = min(self.total, self.done + n) if self.total else self.done + n
        self.message = msg

    def _fetch(self, url: str, dest: Path, label: str, size: int, attempts: int = 60) -> bool:
        for _ in range(attempts):
            have = dest.stat().st_size if dest.exists() else 0
            if have >= size - 4096:
                return True
            req = urllib.request.Request(
                url, headers={"User-Agent": "ocr-studio", "Range": f"bytes={have}-"}
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    mode = "ab" if r.status == 206 else "wb"
                    base = have if mode == "ab" else 0
                    if mode == "wb":
                        self.done = max(0, self.done - have)
                    with open(dest, mode) as f:
                        while True:
                            chunk = r.read(1 << 20)
                            if not chunk:
                                break
                            f.write(chunk)
                            base += len(chunk)
                            self.done += len(chunk)
                            self.message = f"{label}: {base / 1e6:.0f}/{size / 1e6:.0f} MB"
            except urllib.error.HTTPError as exc:
                if exc.code == 416:      # already complete
                    return True
                time.sleep(2)
                continue
            except Exception:  # noqa: BLE001
                time.sleep(2)
                continue
            if dest.exists() and dest.stat().st_size >= size - 4096:
                return True
        return dest.exists() and dest.stat().st_size >= size - 4096


class OvisBackend:
    """OvisOCR3 through a local llama.cpp server (CPU only)."""

    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.port: int | None = None
        self._lock = threading.Lock()
        self._threads = max(1, min(4, os.cpu_count() or 2))

    def missing(self) -> list[str]:
        gaps = []
        if not (LLAMA_DIR / "llama-server.exe").exists():
            gaps.append("llama-server.exe")
        if not OVIS_MODEL.exists():
            gaps.append(OVIS_MODEL.name)
        if not OVIS_MMPROJ.exists():
            gaps.append(OVIS_MMPROJ.name)
        return gaps

    def _healthy(self) -> bool:
        if not self.port:
            return False
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/health", timeout=2
            ) as r:
                return r.status == 200
        except Exception:  # noqa: BLE001
            return False

    def ensure(self) -> None:
        with self._lock:
            if self.proc and self.proc.poll() is None and self._healthy():
                return
            gaps = self.missing()
            if gaps:
                raise RuntimeError(
                    "OvisOCR3 belum terpasang (kurang: " + ", ".join(gaps) + ")"
                )
            self.stop()
            port = _free_port(18499)
            cmd = [
                str(LLAMA_DIR / "llama-server.exe"),
                "--model", str(OVIS_MODEL),
                "--mmproj", str(OVIS_MMPROJ),
                "--host", "127.0.0.1",
                "--port", str(port),
                "--ctx-size", "8192",
                "--threads", str(self._threads),
                "--n-gpu-layers", "0",
                "--jinja",
            ]
            self.proc = subprocess.Popen(
                cmd, cwd=str(LLAMA_DIR),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            self.port = port
            deadline = time.time() + 240
            while time.time() < deadline:
                if self.proc.poll() is not None:
                    raise RuntimeError("llama-server berhenti saat start (cek memori/CPU)")
                if self._healthy():
                    return
                time.sleep(0.5)
            raise RuntimeError("llama-server tidak siap dalam 240 detik")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        self.port = None

    def run(self, bgr: np.ndarray) -> dict[str, Any]:
        self.ensure()
        h, w = bgr.shape[:2]
        ok, buf = cv2.imencode(".png", bgr)
        if not ok:
            raise RuntimeError("gagal meng-encode gambar")
        b64 = base64.b64encode(buf.tobytes()).decode()
        payload = {
            "model": "ovis",
            "messages": [{
                "role": "user",
                "content": [
                    {"type": "text", "text": OVIS_PROMPT},
                    {"type": "image_url",
                     "image_url": {"url": "data:image/png;base64," + b64}},
                ],
            }],
            "temperature": 0,
            "max_tokens": 4096,
        }
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=1800) as r:
            data = json.loads(r.read())
        raw = data["choices"][0]["message"]["content"]
        return _ovis_parse(raw, w, h)


# --------------------------------------------------------------------------- #
# Engine manager
# --------------------------------------------------------------------------- #
class OcrEngine:
    """Lazily builds and caches one engine instance per configuration."""

    def __init__(self) -> None:
        self._lock = threading.Lock()          # serialises inference (2-core box)
        self._build_lock = threading.Lock()
        self._engine = None
        self._kind = "rapid"                   # rapid | indra
        self._key: tuple[str, bool] | None = None
        self.variant = "indra"
        self.use_cls = True                    # +50 ms, fixes upside-down scans
        self.state = "idle"                    # idle | loading | ready | error
        self.error: str | None = None
        self.last_ms: float | None = None
        self.loaded_ms: float | None = None

    # -- lifecycle ---------------------------------------------------------
    def _build(self, variant: str, use_cls: bool):
        if variant == "ovis":
            return OvisBackend()
        if variant == "indra":
            import indra_ocr

            threads = max(1, min(4, os.cpu_count() or 2))
            return indra_ocr.load(threads=threads)

        from rapidocr import RapidOCR
        from rapidocr.utils.typings import ModelType, OCRVersion

        mt = getattr(ModelType, variant.upper())
        params: dict[str, Any] = {
            "Global.log_level": "error",
            "Global.use_cls": use_cls,
            "Global.max_side_len": MAX_SIDE,
            "Global.text_score": 0.4,
            "Global.model_root_dir": str(_model_dir()),
            "Det.ocr_version": OCRVersion.PPOCRV6,
            "Det.model_type": mt,
            "Det.limit_side_len": 736,
            "Rec.ocr_version": OCRVersion.PPOCRV6,
            "Rec.model_type": mt,
            "Rec.rec_batch_num": 8,
            # arena ON avoids huge latency spikes on low-core CPUs
            "EngineConfig.onnxruntime.enable_cpu_mem_arena": True,
            "EngineConfig.onnxruntime.inter_op_num_threads": 1,
        }
        return RapidOCR(params=params)

    def ensure(self) -> None:
        """Make sure an engine matching the current settings is loaded."""
        key = (self.variant, self.use_cls)
        if self._engine is not None and self._key == key:
            return
        with self._build_lock:
            if self._engine is not None and self._key == key:
                return
            self.state = "loading"
            self.error = None
            t0 = time.perf_counter()
            try:
                engine = self._build(self.variant, self.use_cls)
                if self.variant == "ovis":
                    engine.ensure()  # boots llama-server, loads the GGUF
                elif self.variant != "indra":
                    engine(np.full((64, 256, 3), 255, dtype=np.uint8))  # warm-up
            except Exception as exc:  # noqa: BLE001
                self.state = "error"
                self.error = f"{type(exc).__name__}: {exc}"
                raise
            self._engine = engine
            self._kind = self.variant if self.variant in ("indra", "ovis") else "rapid"
            self._key = key
            self.loaded_ms = (time.perf_counter() - t0) * 1000
            self.state = "ready"

    def configure(self, variant: str | None, use_cls: bool | None) -> None:
        if variant is not None:
            if variant not in VARIANTS:
                raise HTTPException(400, f"varian tidak dikenal: {variant}")
            self.variant = variant
        if use_cls is not None:
            self.use_cls = use_cls

    # -- inference ---------------------------------------------------------
    def run(self, bgr: np.ndarray) -> dict[str, Any]:
        self.ensure()
        with self._lock:
            t0 = time.perf_counter()
            if self._kind == "ovis":
                out = self._engine.run(bgr)
            elif self._kind == "indra":
                out = self._run_indra(bgr)
            else:
                out = self._run_rapid(bgr)
            elapsed = (time.perf_counter() - t0) * 1000
        self.last_ms = elapsed
        out["elapsed_ms"] = round(elapsed)
        return out

    def _run_indra(self, bgr: np.ndarray) -> dict[str, Any]:
        """Indra reads from a path, so hand it a short-lived temp file."""
        import tempfile

        fd, path = tempfile.mkstemp(suffix=".png", prefix="ocrstudio_")
        try:
            os.close(fd)
            cv2.imwrite(path, bgr)
            pages = list(self._engine.convert(path))
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

        if not pages:
            return {"lines": [], "text": "", "markdown": "", "stages_ms": {}}

        _, page = pages[0]
        lines = []
        for ln in page.lines:
            x0, y0, x1, y1 = (float(v) for v in ln.box)
            lines.append({
                "text": ln.text,
                "score": round(float(ln.conf), 4),
                "box": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]],
            })

        timings = page.timings or {}
        stages = {
            k: round(float(v))  # indra already reports milliseconds (*_ms keys)
            for k, v in timings.items()
            if isinstance(v, (int, float))
        }
        return {
            "lines": lines,
            "text": flow_text(lines),
            "markdown": page.markdown or "",
            "stages_ms": stages,
        }

    def _run_rapid(self, bgr: np.ndarray) -> dict[str, Any]:
        res = self._engine(bgr)

        txts = () if res.txts is None else tuple(res.txts)
        scores = res.scores if res.scores is not None else [0.0] * len(txts)
        boxes = res.boxes
        lines = []
        for i, (text, score) in enumerate(zip(txts, scores)):
            box = boxes[i].tolist() if boxes is not None and i < len(boxes) else None
            lines.append({"text": text, "score": round(float(score), 4), "box": box})

        elapse = getattr(res, "elapse_list", None)
        stages = {}
        if elapse is not None:
            try:
                names = ("det", "cls", "rec")
                stages = {n: round(float(v) * 1000) for n, v in zip(names, elapse) if v}
            except Exception:  # noqa: BLE001
                stages = {}
        return {
            "lines": lines,
            "text": flow_text(lines),
            "markdown": "",
            "stages_ms": stages,
        }


def flow_text(lines: list[dict[str, Any]]) -> str:
    """Join lines into readable text, inserting a blank line on big vertical gaps."""
    out: list[str] = []
    prev_bottom: float | None = None
    for ln in lines:
        box = ln.get("box")
        if box:
            top = min(p[1] for p in box)
            bottom = max(p[1] for p in box)
            height = max(bottom - top, 1.0)
            if prev_bottom is not None and (top - prev_bottom) > height * 0.75:
                out.append("")
            prev_bottom = bottom
        out.append(ln["text"])
    return "\n".join(out).strip()


ENGINE = OcrEngine()
OVIS_SETUP = OvisInstaller()
atexit.register(lambda: ENGINE._engine.stop() if isinstance(ENGINE._engine, OvisBackend) else None)


# --------------------------------------------------------------------------- #
# Image helpers
# --------------------------------------------------------------------------- #
def _decode_image(data: bytes) -> np.ndarray:
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            400,
            f"Format gambar tidak dikenali ({exc}). Yang didukung: PNG, JPEG, WebP, "
            "AVIF, JXL, HEIC, TIFF, BMP, GIF, JPEG 2000, QOI, PSD, TGA, PCX, DDS, ICO.",
        ) from exc
    im = ImageOps.exif_transpose(im).convert("RGB")
    if max(im.size) > MAX_SIDE:
        im.thumbnail((MAX_SIDE, MAX_SIDE), Image.LANCZOS)
    return cv2.cvtColor(np.array(im), cv2.COLOR_RGB2BGR)


def _preview_data_url(bgr: np.ndarray, max_w: int = MAX_SIDE) -> str:
    """Encode the page for the viewer.

    Kept at the OCR working resolution so that zooming in the canvas shows real
    detail instead of an upscaled thumbnail.
    """
    im = Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def _pdf_pages(data: bytes):
    """Yield (index, PIL image) for every page of a PDF."""
    try:
        doc = pdfium.PdfDocument(data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"PDF tidak bisa dibaca: {exc}") from exc
    try:
        for i in range(len(doc)):
            page = doc[i]
            w = page.get_width() or 1000
            scale = min(2.0, 1600 / float(w)) if w else 1.5
            yield i, page.render(scale=scale).to_pil().convert("RGB")
    finally:
        doc.close()


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
app = FastAPI(title="OCR Studio", version="1.0.0")
app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(WEB / "index.html")


@app.get("/api/status")
def status() -> dict[str, Any]:
    import onnxruntime
    from importlib.metadata import PackageNotFoundError, version

    try:
        rapidocr_version = version("rapidocr")
    except PackageNotFoundError:
        rapidocr_version = "?"

    return {
        "state": ENGINE.state,
        "error": ENGINE.error,
        "variant": ENGINE.variant,
        "use_cls": ENGINE.use_cls,
        "variants": VARIANTS,
        "last_ms": ENGINE.last_ms,
        "loaded_ms": ENGINE.loaded_ms,
        "engine": {
            "rapidocr": rapidocr_version,
            "onnxruntime": onnxruntime.__version__,
            "models": "PP-OCRv6 (det + rec)",
        },
        "host": {
            "cpu": os.cpu_count(),
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
    }


@app.post("/api/ovis/install")
async def ovis_install() -> JSONResponse:
    """Start (or resume) the one-time download of llama.cpp + OvisOCR3 weights."""
    return JSONResponse(OVIS_SETUP.start())


@app.get("/api/ovis/status")
async def ovis_status() -> JSONResponse:
    st = OVIS_SETUP.status()
    st["ready"] = not OvisBackend().missing()
    return JSONResponse(st)


@app.post("/api/config")
async def config(payload: dict[str, Any]) -> dict[str, Any]:
    ENGINE.configure(payload.get("variant"), payload.get("use_cls"))
    try:
        await run_in_threadpool(ENGINE.ensure)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": ENGINE.error or str(exc)}, status_code=500)
    return {"ok": True, "variant": ENGINE.variant, "use_cls": ENGINE.use_cls,
            "loaded_ms": ENGINE.loaded_ms}


@app.get("/api/sample")
def sample() -> FileResponse:
    path = SAMPLES / "smoke_test.png"
    if not path.exists():
        raise HTTPException(404, "contoh tidak tersedia")
    return FileResponse(path, media_type="image/png")


@app.post("/api/ocr")
async def ocr(file: UploadFile = File(...), pages: str = Form(default="")) -> dict[str, Any]:
    """OCR one image or PDF. `pages` limits PDF pages, e.g. "1-3,5"."""
    data = await file.read()
    if not data:
        raise HTTPException(400, "file kosong")
    name = file.filename or "upload"
    is_pdf = data[:5] == b"%PDF-" or name.lower().endswith(".pdf")

    if is_pdf:
        wanted = _parse_pages(pages)
        out_pages = []
        for idx, pil in _pdf_pages(data):
            if wanted and (idx + 1) not in wanted:
                continue
            bgr = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
            if max(bgr.shape[:2]) > MAX_SIDE:
                h, w = bgr.shape[:2]
                s = MAX_SIDE / max(h, w)
                bgr = cv2.resize(bgr, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
            res = await run_in_threadpool(ENGINE.run, bgr)
            res.update({"index": idx + 1, "width": bgr.shape[1], "height": bgr.shape[0],
                        "image": _preview_data_url(bgr)})
            out_pages.append(res)
        if not out_pages:
            raise HTTPException(400, "tidak ada halaman yang cocok dengan pilihan")
        return {"name": name, "kind": "pdf", "pages": out_pages}

    bgr = _decode_image(data)
    res = await run_in_threadpool(ENGINE.run, bgr)
    res.update({"index": 1, "width": bgr.shape[1], "height": bgr.shape[0],
                "image": _preview_data_url(bgr)})
    return {"name": name, "kind": "image", "pages": [res]}


def _parse_pages(spec: str) -> set[int]:
    spec = (spec or "").strip()
    if not spec:
        return set()
    out: set[int] = set()
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk:
            a, _, b = chunk.partition("-")
            try:
                lo, hi = int(a), int(b or a)
            except ValueError:
                continue
            out.update(range(min(lo, hi), max(lo, hi) + 1))
        else:
            try:
                out.add(int(chunk))
            except ValueError:
                continue
    return out


def _free_port(preferred: int) -> int:
    for port in (preferred, 8849, 8850, 8851, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return s.getsockname()[1]
            except OSError:
                continue
    return preferred


def _is_ours(port: int) -> bool:
    """True if something that looks like OCR Studio already answers on this port."""
    import urllib.request

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/status", timeout=1.2) as r:
            return b'"variants"' in r.read()
    except Exception:  # noqa: BLE001
        return False


def _open_when_ready(port: int, timeout: float = 90.0) -> None:
    """Open the browser only once the socket accepts connections."""
    if os.environ.get("OCR_STUDIO_NO_BROWSER"):
        return
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                webbrowser.open(f"http://127.0.0.1:{port}")
                return
        except OSError:
            time.sleep(0.2)


def _fatal(msg: str) -> None:
    """Show a blocking error dialog (no console available in packaged builds)."""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, msg, "OCR Studio", 0x10)
    except Exception:  # noqa: BLE001
        pass


def main() -> None:
    import uvicorn

    # second double-click: reuse the instance that is already serving
    if _is_ours(8848):
        if not os.environ.get("OCR_STUDIO_NO_BROWSER"):
            webbrowser.open("http://127.0.0.1:8848")
        print("OCR Studio sudah berjalan di http://127.0.0.1:8848")
        return

    if FROZEN:
        log = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "OCRStudio" / "app.log"
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            fh = open(log, "a", encoding="utf-8", buffering=1)  # noqa: SIM115
            if sys.stdout is None:
                sys.stdout = fh
            if sys.stderr is None:
                sys.stderr = fh
        except OSError:
            pass

    port = _free_port(8848)
    url = f"http://127.0.0.1:{port}"
    print(f"\n  OCR Studio siap di {url}\n  Tutup jendela ini untuk berhenti.\n", flush=True)
    threading.Thread(target=_open_when_ready, args=(port,), daemon=True).start()
    try:
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    except Exception as exc:  # noqa: BLE001
        _fatal(f"Gagal menjalankan OCR Studio:\n\n{type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
