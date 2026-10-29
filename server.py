"""
OCR Studio - local OCR engine (RapidOCR / PP-OCRv6 on ONNX Runtime).

Runs fully offline on CPU. Serves a small web UI on 127.0.0.1 and exposes a
JSON API for OCR of images and PDFs.
"""

from __future__ import annotations

import base64
import io
import os
import platform
import shutil
import socket
import sys
import threading
import time
import webbrowser
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
}


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
                if self.variant != "indra":
                    engine(np.full((64, 256, 3), 255, dtype=np.uint8))  # warm-up
            except Exception as exc:  # noqa: BLE001
                self.state = "error"
                self.error = f"{type(exc).__name__}: {exc}"
                raise
            self._engine = engine
            self._kind = "indra" if self.variant == "indra" else "rapid"
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
            if self._kind == "indra":
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
