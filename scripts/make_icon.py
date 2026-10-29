"""Generate assets/icon.ico for the packaged app."""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "icon.ico"
S = 256
ACCENT = (124, 156, 255, 255)
BG = (16, 20, 28, 255)


def draw(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(size * 0.22)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=BG)

    # scan-frame corners
    m = int(size * 0.22)
    arm = int(size * 0.14)
    w = max(2, int(size * 0.045))
    for (x, y, dx, dy) in ((m, m, 1, 1), (size - m, m, -1, 1),
                           (m, size - m, 1, -1), (size - m, size - m, -1, -1)):
        d.line([(x, y), (x + dx * arm, y)], fill=ACCENT, width=w)
        d.line([(x, y), (x, y + dy * arm)], fill=ACCENT, width=w)

    # text lines
    lw = max(3, int(size * 0.055))
    lx0 = int(size * 0.30)
    for i, frac in enumerate((0.62, 0.48, 0.56)):
        y = int(size * (0.36 + i * 0.14))
        d.line([(lx0, y), (lx0 + int(size * frac * 0.55), y)],
               fill=(230, 236, 248, 255), width=lw)
    return img


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    base = draw(S)
    base.save(OUT, format="ICO",
              sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    base.save(OUT.with_suffix(".png"))
    print(f"wrote {OUT}")
