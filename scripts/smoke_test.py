"""Smoke test: build a synthetic image and run RapidOCR on it."""
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "samples"
OUT.mkdir(exist_ok=True)


def make_image() -> Path:
    img = Image.new("RGB", (900, 380), "white")
    d = ImageDraw.Draw(img)

    def font(size: int):
        for name in ("arial.ttf", "segoeui.ttf", "calibri.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                continue
        return ImageFont.load_default()

    d.text((40, 30), "OCR Studio - Smoke Test", fill="black", font=font(44))
    d.text((40, 100), "Halo, ini teks bahasa Indonesia.", fill=(20, 20, 20), font=font(30))
    d.text((40, 150), "Invoice #2026-0042  Total: Rp 1.250.000", fill=(20, 20, 20), font=font(28))
    d.text((40, 200), "The quick brown fox jumps over 13 lazy dogs.", fill=(20, 20, 20), font=font(28))
    d.text((40, 250), "Email: support@example.com  Telp: +62 812-3456-7890", fill=(20, 20, 20), font=font(26))
    d.rectangle([40, 300, 860, 340], outline="gray", width=2)
    d.text((55, 308), "Baris terakhir untuk menguji deteksi kotak teks.", fill=(20, 20, 20), font=font(24))

    p = OUT / "smoke_test.png"
    img.save(p)
    return p


def main() -> int:
    img_path = make_image()
    print(f"image: {img_path}")

    t0 = time.perf_counter()
    from rapidocr import RapidOCR

    engine = RapidOCR()
    print(f"engine loaded in {time.perf_counter() - t0:.2f}s")

    t1 = time.perf_counter()
    res = engine(str(img_path))
    dt = time.perf_counter() - t1

    txts = getattr(res, "txts", None)
    boxes = getattr(res, "boxes", None)
    scores = getattr(res, "scores", None)
    txts = () if txts is None else tuple(txts)
    scores = () if scores is None else tuple(scores)
    print(f"inference: {dt * 1000:.0f} ms | {len(txts)} lines")
    for i, (t, s) in enumerate(zip(txts, scores), 1):
        print(f"  {i:02d}. [{float(s):.3f}] {t}")
    if boxes is not None and len(boxes):
        print(f"  box[0] = {boxes[0]}")
    return 0 if len(txts) >= 4 else 1


if __name__ == "__main__":
    sys.exit(main())
